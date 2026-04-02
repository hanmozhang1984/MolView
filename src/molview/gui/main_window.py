from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QSettings
from PySide6.QtGui import QAction, QKeySequence, QUndoStack
from PySide6.QtWidgets import (
    QMainWindow, QFileDialog, QMessageBox, QToolBar,
    QStackedWidget, QStatusBar, QLabel, QSplitter, QApplication,
    QProgressDialog,
)

from molview.models.dataset import DataSet
from molview.gui.table.table_view import DataTableView


FILE_FILTERS = (
    "All Supported Files (*.csv *.xlsx *.xls *.sdf *.mol);;"
    "CSV Files (*.csv);;"
    "Excel Files (*.xlsx *.xls);;"
    "SDF Files (*.sdf);;"
    "MOL Files (*.mol);;"
    "All Files (*)"
)

SAVE_FILTERS = (
    "CSV Files (*.csv);;"
    "Excel Files (*.xlsx);;"
    "SDF Files (*.sdf)"
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MolView")
        self.setMinimumSize(1200, 700)

        self._dataset = DataSet(self)
        self._dataset.data_changed.connect(self._update_status)
        self._dataset.rows_changed.connect(self._update_status)
        self._dataset.columns_changed.connect(self._update_status)

        # Undo/redo stack
        self._undo_stack = QUndoStack(self)
        self._undo_stack.cleanChanged.connect(self._on_undo_clean_changed)

        # Settings
        self._settings = QSettings("MolView", "MolView")
        self._max_recent_files = 10

        # Pre-loaded Ketcher web view (deferred until after window is shown)
        self._preloaded_ketcher = None

        self._apply_global_style()
        self._setup_ui()
        self._setup_menus()
        self._setup_toolbar()
        self._update_status()

        # Restore window geometry
        geometry = self._settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        state = self._settings.value("windowState")
        if state:
            self.restoreState(state)

        # Defer Ketcher preload to after event loop starts (avoids QWebEngineView
        # interfering with widget events during initial layout on macOS)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, self._preload_ketcher)

        # Move menus into the window instead of macOS system menu bar
        self.menuBar().setNativeMenuBar(False)

        # Accept drag-and-drop files
        self.setAcceptDrops(True)

    def _apply_global_style(self):
        self.setStyleSheet("""
            QMenuBar {
                background: #e8e8e8;
                border-bottom: 1px solid #ccc;
                padding: 2px 0px;
            }
            QMenuBar::item {
                padding: 4px 10px;
                border-radius: 4px;
            }
            QMenuBar::item:selected {
                background: #d0d8e8;
            }
            QMenu {
                padding: 4px 0px;
            }
            QMenu::item {
                padding: 5px 28px 5px 20px;
            }
            QMenu::item:selected {
                background: #d0d8e8;
            }
            QMenu::separator {
                height: 1px;
                background: #d0d0d0;
                margin: 3px 8px;
            }
            QToolBar {
                background: #f0f0f0;
                border-bottom: 1px solid #ccc;
                spacing: 3px;
                padding: 2px 6px;
            }
            QToolButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QToolButton:hover {
                background: #dde4ee;
                border: 1px solid #b0b8c8;
            }
            QToolButton:pressed {
                background: #c0cade;
            }
            QToolBar::separator {
                width: 1px;
                background: #c8c8c8;
                margin: 3px 4px;
            }
            QStatusBar {
                background: #f0f0f0;
                border-top: 1px solid #ccc;
            }
            QTableView {
                gridline-color: #ddd;
                selection-background-color: #ccdcf0;
                selection-color: #000;
            }
            QHeaderView::section {
                background: #e8e8e8;
                border: none;
                border-right: 1px solid #ccc;
                border-bottom: 1px solid #ccc;
                padding: 4px 4px;
                text-align: center;
            }
        """)

    def _setup_ui(self):
        from PySide6.QtWidgets import QVBoxLayout, QWidget

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        # Table page (table view + column filter bar)
        table_page = QWidget()
        table_layout = QVBoxLayout(table_page)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)

        self._table_view = DataTableView(self._dataset, undo_stack=self._undo_stack)
        self._filter_bar = self._table_view.get_filter_bar()
        table_layout.addWidget(self._filter_bar)
        table_layout.addWidget(self._table_view)

        self._stack.addWidget(table_page)

        # Plot panel
        from molview.gui.plotting.plot_panel import PlotPanel
        self._plot_panel = PlotPanel(self._dataset)
        self._plot_panel.points_selected.connect(self._on_plot_selection)
        self._stack.addWidget(self._plot_panel)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_label = QLabel()
        self._status_bar.addPermanentWidget(self._status_label)
        self._selection_label = QLabel()
        self._status_bar.addWidget(self._selection_label)

        # Track table selection changes for status bar
        self._table_view.selectionModel().selectionChanged.connect(
            self._update_selection_status
        )

    def _setup_menus(self):
        menubar = self.menuBar()

        # ── File ──
        file_menu = menubar.addMenu("&File")

        open_action = QAction("&Open...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._open_file)
        file_menu.addAction(open_action)

        self._recent_menu = file_menu.addMenu("Open &Recent")
        self._rebuild_recent_menu()

        file_menu.addSeparator()

        save_action = QAction("&Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self._save_file)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save &As...", self)
        save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as_action.triggered.connect(self._save_file_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        export_all_action = QAction("Export All Rows...", self)
        export_all_action.triggered.connect(self._export_all)
        file_menu.addAction(export_all_action)

        export_visible_action = QAction("Export Visible Rows...", self)
        export_visible_action.triggered.connect(self._export_visible)
        file_menu.addAction(export_visible_action)

        file_menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # ── Edit ──
        edit_menu = menubar.addMenu("&Edit")

        undo_action = self._undo_stack.createUndoAction(self, "&Undo")
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        edit_menu.addAction(undo_action)

        redo_action = self._undo_stack.createRedoAction(self, "&Redo")
        redo_action.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        add_row_action = QAction("Add Row", self)
        add_row_action.triggered.connect(self._add_row)
        edit_menu.addAction(add_row_action)

        add_col_action = QAction("Add Column...", self)
        add_col_action.triggered.connect(self._table_view._add_column_dialog)
        edit_menu.addAction(add_col_action)

        edit_menu.addSeparator()

        select_all_action = QAction("Select All Rows", self)
        select_all_action.setShortcut(QKeySequence.StandardKey.SelectAll)
        select_all_action.triggered.connect(self._select_all_rows)
        edit_menu.addAction(select_all_action)

        deselect_all_action = QAction("Deselect All", self)
        deselect_all_action.setShortcut(QKeySequence("Ctrl+D"))
        deselect_all_action.triggered.connect(self._deselect_all_rows)
        edit_menu.addAction(deselect_all_action)

        invert_sel_action = QAction("Invert Selection", self)
        invert_sel_action.setShortcut(QKeySequence("Ctrl+I"))
        invert_sel_action.triggered.connect(self._invert_selection)
        edit_menu.addAction(invert_sel_action)

        export_sel_action2 = QAction("Export Selected Rows...", self)
        export_sel_action2.setShortcut(QKeySequence("Ctrl+E"))
        export_sel_action2.triggered.connect(self._export_selected)
        edit_menu.addAction(export_sel_action2)

        edit_menu.addSeparator()

        sel_top_action = QAction("Move Selected to Top", self)
        sel_top_action.triggered.connect(self._pin_selected_top)
        edit_menu.addAction(sel_top_action)

        sel_bottom_action = QAction("Move Selected to Bottom", self)
        sel_bottom_action.triggered.connect(self._pin_selected_bottom)
        edit_menu.addAction(sel_bottom_action)

        clear_pin_action = QAction("Clear Sort by Selection", self)
        clear_pin_action.triggered.connect(self._clear_pin)
        edit_menu.addAction(clear_pin_action)

        edit_menu.addSeparator()

        hl_top_action = QAction("Sort Highlighted to Top", self)
        hl_top_action.triggered.connect(self._sort_highlighted_top)
        edit_menu.addAction(hl_top_action)

        hl_bottom_action = QAction("Sort Highlighted to Bottom", self)
        hl_bottom_action.triggered.connect(self._sort_highlighted_bottom)
        edit_menu.addAction(hl_bottom_action)

        edit_menu.addSeparator()

        hide_sel_action = QAction("Hide Selected Rows", self)
        hide_sel_action.setShortcut(QKeySequence("Ctrl+H"))
        hide_sel_action.triggered.connect(self._hide_selected_rows)
        edit_menu.addAction(hide_sel_action)

        hide_unsel_action = QAction("Hide Unselected Rows", self)
        hide_unsel_action.triggered.connect(self._hide_unselected_rows)
        edit_menu.addAction(hide_unsel_action)

        show_all_action = QAction("Show All Hidden Rows", self)
        show_all_action.setShortcut(QKeySequence("Ctrl+Shift+H"))
        show_all_action.triggered.connect(self._dataset.show_all_rows)
        edit_menu.addAction(show_all_action)

        edit_menu.addSeparator()

        delete_sel_action = QAction("Delete Selected Rows", self)
        delete_sel_action.setShortcut(QKeySequence.StandardKey.Delete)
        delete_sel_action.triggered.connect(self._delete_selected_rows)
        edit_menu.addAction(delete_sel_action)

        # ── View ──
        view_menu = menubar.addMenu("&View")

        table_action = QAction("Data Table", self)
        table_action.setShortcut(QKeySequence("Ctrl+1"))
        table_action.triggered.connect(lambda: self._stack.setCurrentIndex(0))
        view_menu.addAction(table_action)

        plot_action = QAction("Plot Panel", self)
        plot_action.setShortcut(QKeySequence("Ctrl+2"))
        plot_action.triggered.connect(lambda: self._stack.setCurrentIndex(1))
        view_menu.addAction(plot_action)

        view_menu.addSeparator()

        toggle_filters_action = QAction("Toggle Column Filters", self)
        toggle_filters_action.setShortcut(QKeySequence("Ctrl+L"))
        toggle_filters_action.triggered.connect(self._table_view.toggle_column_filters)
        view_menu.addAction(toggle_filters_action)

        reset_widths_action = QAction("Reset Column Widths", self)
        reset_widths_action.triggered.connect(self._table_view.reset_column_widths)
        view_menu.addAction(reset_widths_action)

        # ── Chemistry ──
        chem_menu = menubar.addMenu("&Chemistry")

        calc_props_action = QAction("Calculate Properties...", self)
        calc_props_action.setShortcut(QKeySequence("Ctrl+P"))
        calc_props_action.triggered.connect(self._calculate_properties)
        chem_menu.addAction(calc_props_action)

        search_action = QAction("Structure Search...", self)
        search_action.setShortcut(QKeySequence("Ctrl+F"))
        search_action.triggered.connect(self._structure_search)
        chem_menu.addAction(search_action)

        chem_menu.addSeparator()

        clear_search_action = QAction("Clear Search (Show All)", self)
        clear_search_action.setShortcut(QKeySequence("Escape"))
        clear_search_action.triggered.connect(self._clear_search)
        chem_menu.addAction(clear_search_action)

    def _setup_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)

        # Only items not already in the menu bar dropdowns
        toolbar.addAction("Calc Props", self._calculate_properties)
        toolbar.addAction("Structure Search", self._structure_search)
        toolbar.addAction("Clear Search", self._clear_search)
        toolbar.addSeparator()
        toolbar.addAction("Show All Rows", self._dataset.show_all_rows)
        toolbar.addAction("Clear Sort", self._clear_pin)
        toolbar.addSeparator()
        toolbar.addAction("Table View", lambda: self._stack.setCurrentIndex(0))
        toolbar.addAction("Plot View", lambda: self._stack.setCurrentIndex(1))

    # ── Status bar ──

    def _update_status(self):
        if self._dataset.is_empty():
            self._status_label.setText("No data loaded")
        else:
            hidden = len(self._dataset.hidden_rows)
            total = self._dataset.row_count
            visible = total - hidden
            cols = self._dataset.column_count
            text = f"{visible}/{total} rows, {cols} columns"
            if hidden > 0:
                text += f"  ({hidden} hidden)"
            if self._dataset.file_path:
                text = f"{os.path.basename(self._dataset.file_path)} — {text}"
            if self._dataset.modified:
                text += " [modified]"
            self._status_label.setText(text)

    def _update_selection_status(self):
        selected = self._table_view.get_selected_source_rows()
        if selected:
            self._selection_label.setText(f"{len(selected)} row(s) selected")
        else:
            self._selection_label.setText("")

    def _on_plot_selection(self, rows: set):
        """Handle point selection from the plot panel."""
        n = len(rows)
        if n > 0:
            self._selection_label.setText(f"{n} point(s) selected on plot")
            self._status_bar.showMessage(
                f"Selected {n} point(s) — highlighted in table. Switch to Table View (Ctrl+1) to see them.",
                5000
            )
        else:
            self._selection_label.setText("")

    # ── Selection ──

    def _select_all_rows(self):
        self._table_view.selectAll()

    def _deselect_all_rows(self):
        self._table_view.clearSelection()
        self._dataset.clear_selection()
        self._dataset.data_changed.emit()

    def _invert_selection(self):
        self._table_view.invert_selection()

    def _pin_selected_top(self):
        rows = self._table_view.get_selected_source_rows()
        if rows:
            self._dataset.select_rows(set(rows))
            self._table_view.proxy_model.pin_selected_top()
            self._table_view.sortByColumn(0, Qt.SortOrder.AscendingOrder)

    def _pin_selected_bottom(self):
        rows = self._table_view.get_selected_source_rows()
        if rows:
            self._dataset.select_rows(set(rows))
            self._table_view.proxy_model.pin_selected_bottom()
            self._table_view.sortByColumn(0, Qt.SortOrder.AscendingOrder)

    def _clear_pin(self):
        self._table_view.proxy_model.clear_pin()

    # ── Sort by highlighted (dataset.selected_rows) ──

    def _sort_highlighted_top(self):
        if self._dataset.selected_rows:
            self._table_view.proxy_model.pin_highlighted_top()
            self._table_view.sortByColumn(0, Qt.SortOrder.AscendingOrder)

    def _sort_highlighted_bottom(self):
        if self._dataset.selected_rows:
            self._table_view.proxy_model.pin_highlighted_bottom()
            self._table_view.sortByColumn(0, Qt.SortOrder.AscendingOrder)

    # ── Hide/show ──

    def _hide_selected_rows(self):
        rows = self._table_view.get_selected_source_rows()
        if rows:
            self._dataset.hide_rows(set(rows))
            self._table_view.clearSelection()

    def _hide_unselected_rows(self):
        selected = set(self._table_view.get_selected_source_rows())
        if not selected:
            return
        all_rows = set(range(self._dataset.row_count))
        to_hide = all_rows - selected - self._dataset.hidden_rows
        self._dataset.hide_rows(to_hide)

    def _add_row(self):
        from molview.models.undo_commands import AddRowCommand
        self._undo_stack.push(AddRowCommand(self._dataset))

    def _delete_selected_rows(self):
        rows = self._table_view.get_selected_source_rows()
        if not rows:
            return
        reply = QMessageBox.question(
            self, "Delete Rows",
            f"Delete {len(rows)} row(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            from molview.models.undo_commands import DeleteRowsCommand
            self._undo_stack.push(DeleteRowsCommand(self._dataset, rows))

    def _clear_search(self):
        self._dataset.show_all_rows()
        self._dataset.clear_selection()
        self._dataset.data_changed.emit()

    # ── Undo/redo ──

    def _on_undo_clean_changed(self, clean: bool):
        self._dataset.modified = not clean
        self._update_status()

    # ── Recent files ──

    def _rebuild_recent_menu(self):
        self._recent_menu.clear()
        recent = self._settings.value("recentFiles", [])
        if not recent:
            no_recent = self._recent_menu.addAction("(No recent files)")
            no_recent.setEnabled(False)
            return
        for path in recent:
            action = self._recent_menu.addAction(os.path.basename(path))
            action.setToolTip(path)
            action.triggered.connect(lambda checked, p=path: self._load_file(p))
        self._recent_menu.addSeparator()
        clear_action = self._recent_menu.addAction("Clear Recent Files")
        clear_action.triggered.connect(self._clear_recent_files)

    def _add_recent_file(self, path: str):
        recent = self._settings.value("recentFiles", [])
        if not isinstance(recent, list):
            recent = []
        # Remove if already present, then prepend
        abs_path = os.path.abspath(path)
        recent = [r for r in recent if os.path.abspath(r) != abs_path]
        recent.insert(0, abs_path)
        recent = recent[:self._max_recent_files]
        self._settings.setValue("recentFiles", recent)
        self._rebuild_recent_menu()

    def _clear_recent_files(self):
        self._settings.setValue("recentFiles", [])
        self._rebuild_recent_menu()

    # ── File I/O ──

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open File", "", FILE_FILTERS
        )
        if not path:
            return
        self._load_file(path)

    def _load_file(self, path: str):
        ext = Path(path).suffix.lower()

        # For large SDF files, load in background with progress
        if ext == ".sdf" and os.path.getsize(path) > 2_000_000:
            self._load_sdf_async(path)
            return

        try:
            if ext == ".csv":
                from molview.io.csv_handler import load_csv
                df, schemas = load_csv(path)
            elif ext in (".xlsx", ".xls"):
                from molview.io.excel_handler import load_excel
                df, schemas = load_excel(path)
            elif ext == ".sdf":
                from molview.io.sdf_handler import load_sdf
                df, schemas = load_sdf(path)
            elif ext == ".mol":
                from molview.io.mol_handler import load_mol
                df, schemas = load_mol(path)
            else:
                QMessageBox.warning(self, "Error", f"Unsupported format: {ext}")
                return

            self._finish_load(path, df, schemas)
        except Exception as e:
            QMessageBox.critical(self, "Error Loading File", str(e))

    def _load_sdf_async(self, path: str):
        """Load a large SDF file in a background thread with a progress dialog."""
        from molview.io.sdf_handler import load_sdf
        from molview.workers.io_worker import FileLoadWorker

        self._progress_dlg = QProgressDialog("Loading SDF file...", "Cancel", 0, 100, self)
        self._progress_dlg.setWindowTitle("Loading")
        self._progress_dlg.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress_dlg.setMinimumDuration(0)
        self._progress_dlg.setValue(0)

        self._load_worker = FileLoadWorker(path, load_sdf)
        self._load_worker.progress.connect(self._progress_dlg.setValue)
        self._load_worker.finished.connect(
            lambda df, schemas: self._on_sdf_loaded(path, df, schemas)
        )
        self._load_worker.error.connect(self._on_sdf_load_error)
        self._progress_dlg.canceled.connect(self._load_worker.terminate)
        self._load_worker.start()

    def _on_sdf_loaded(self, path, df, schemas):
        self._progress_dlg.close()
        if df is not None and not df.empty:
            self._finish_load(path, df, schemas)
        else:
            QMessageBox.warning(self, "Error", "No data found in file.")

    def _on_sdf_load_error(self, msg):
        self._progress_dlg.close()
        QMessageBox.critical(self, "Error Loading File", msg)

    def _finish_load(self, path, df, schemas):
        """Common post-load logic for all file types."""
        if df.empty:
            QMessageBox.warning(self, "Error", "No data found in file.")
            return

        self._dataset.load_dataframe(df, schemas)
        self._dataset.file_path = path
        self._undo_stack.clear()
        self._add_recent_file(path)

        # Auto-detect SMILES columns
        from molview.chem.structure_utils import detect_smiles_columns
        from molview.models.column_schema import ColumnSchema, ColumnType
        smiles_cols = detect_smiles_columns(df)
        for col_name in smiles_cols:
            if col_name not in (schemas or {}):
                self._dataset.set_schema(
                    col_name, ColumnSchema(col_name, ColumnType.SMILES)
                )

        self.setWindowTitle(f"MolView — {os.path.basename(path)}")
        self._update_status()

    def _save_file(self):
        if self._dataset.file_path:
            self._do_save(self._dataset.file_path)
        else:
            self._save_file_as()

    def _save_file_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save File", "", SAVE_FILTERS)
        if not path:
            return
        self._do_save(path)

    def _do_save(self, path: str, df=None):
        """Save a DataFrame to file. If df is None, saves the full dataset."""
        ext = Path(path).suffix.lower()
        if df is None:
            df = self._dataset.df
        try:
            if ext == ".csv":
                from molview.io.csv_handler import save_csv
                save_csv(path, df)
            elif ext in (".xlsx", ".xls"):
                from molview.io.excel_handler import save_excel
                save_excel(path, df)
            elif ext == ".sdf":
                from molview.io.sdf_handler import save_sdf
                save_sdf(path, df)
            else:
                QMessageBox.warning(self, "Error", f"Unsupported save format: {ext}")
                return

            # Only update file_path/modified if saving the full dataset
            if df is self._dataset.df:
                self._dataset.file_path = path
                self._dataset.modified = False
                self._undo_stack.setClean()
                self.setWindowTitle(f"MolView — {os.path.basename(path)}")
            self._update_status()
            self._status_bar.showMessage(f"Saved to {os.path.basename(path)}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Error Saving File", str(e))

    # ── Export ──

    def _export_all(self):
        if self._dataset.is_empty():
            QMessageBox.information(self, "Info", "No data to export.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export All Rows", "", SAVE_FILTERS)
        if path:
            self._do_save(path, self._dataset.df)

    def _export_selected(self):
        if self._dataset.is_empty():
            QMessageBox.information(self, "Info", "No data to export.")
            return
        rows = self._table_view.get_selected_source_rows()
        if not rows:
            QMessageBox.information(self, "Info", "No rows selected. Select rows first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export {len(rows)} Selected Rows", "", SAVE_FILTERS
        )
        if path:
            df_selected = self._dataset.df.iloc[rows].reset_index(drop=True)
            self._do_save(path, df_selected)

    def _export_visible(self):
        if self._dataset.is_empty():
            QMessageBox.information(self, "Info", "No data to export.")
            return
        hidden = self._dataset.hidden_rows
        visible_mask = ~self._dataset.df.index.isin(hidden)
        df_visible = self._dataset.df[visible_mask].reset_index(drop=True)
        if df_visible.empty:
            QMessageBox.information(self, "Info", "No visible rows to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export {len(df_visible)} Visible Rows", "", SAVE_FILTERS
        )
        if path:
            self._do_save(path, df_visible)

    # ── Ketcher pre-loading ──

    def _preload_ketcher(self):
        """Create a hidden QWebEngineView that loads Ketcher in the background."""
        try:
            from molview.gui.structure_editor.editor_dialog import create_ketcher_webview
            self._preloaded_ketcher = create_ketcher_webview(self)
            # Keep it hidden — don't add to any layout
            self._preloaded_ketcher.setVisible(False)
        except Exception:
            self._preloaded_ketcher = None

    def _take_preloaded_ketcher(self):
        """Take ownership of the pre-loaded Ketcher view (returns it and starts a new preload)."""
        view = self._preloaded_ketcher
        self._preloaded_ketcher = None
        # Start pre-loading a fresh one for next use
        self._preload_ketcher()
        return view

    # ── Chemistry ──

    def _calculate_properties(self):
        if self._dataset.is_empty():
            QMessageBox.information(self, "Info", "Load a file first.")
            return
        from molview.gui.dialogs.property_calc_dialog import PropertyCalcDialog
        dlg = PropertyCalcDialog(self._dataset, self)
        dlg.exec()

    def _structure_search(self):
        if self._dataset.is_empty():
            QMessageBox.information(self, "Info", "Load a file first.")
            return
        from molview.gui.dialogs.search_dialog import SearchDialog
        # Use show() not exec() — the search dialog may open a Ketcher editor,
        # and QWebEngineView deadlocks inside nested event loops from exec()
        self._search_dlg = SearchDialog(self._dataset, self)
        self._search_dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._search_dlg.setModal(True)
        self._search_dlg.show()

    # ── Drag and drop ──

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if Path(path).suffix.lower() in (".csv", ".xlsx", ".xls", ".sdf", ".mol"):
                    event.acceptProposedAction()
                    return

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if Path(path).suffix.lower() in (".csv", ".xlsx", ".xls", ".sdf", ".mol"):
                self._load_file(path)
                return

    # ── Close ──

    def closeEvent(self, event):
        # Save window geometry
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("windowState", self.saveState())

        if self._dataset.modified:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Save before closing?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Save:
                self._save_file()
                event.accept()
            elif reply == QMessageBox.StandardButton.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
