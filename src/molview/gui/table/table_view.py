from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal, QItemSelection, QTimer, QSize
from PySide6.QtGui import QUndoStack, QKeySequence
from PySide6.QtWidgets import (
    QTableView, QMenu, QInputDialog, QHeaderView, QMessageBox, QAbstractItemView,
    QApplication, QWidget, QHBoxLayout, QLineEdit, QVBoxLayout, QFrame, QStyleOptionHeader,
    QStyle,
)

from molview.models.dataset import DataSet
from molview.models.column_schema import ColumnType, ColumnSchema
from molview.models.undo_commands import (
    AddRowCommand, DeleteRowsCommand, AddColumnCommand, DeleteColumnCommand,
    RenameColumnCommand, SetColumnFormatCommand,
)
from molview.gui.table.table_model import DataFrameTableModel, COLUMN_TYPE_ROLE
from molview.gui.table.filter_proxy import FilterProxyModel
from molview.gui.table.delegates import StructureDelegate


class ColumnFilterBar(QFrame):
    """Row of QLineEdit widgets for per-column text filtering."""

    filter_changed = Signal(int, str)  # col_index, text

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._filters: list[QLineEdit] = []
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(200)
        self._pending_col = -1
        self._pending_text = ""
        self._debounce_timer.timeout.connect(self._emit_pending)
        self.setFixedHeight(26)

    def rebuild(self, col_count: int):
        """Rebuild filter inputs for the given column count."""
        # Clear existing
        for f in self._filters:
            f.deleteLater()
        self._filters.clear()

        for i in range(col_count):
            le = QLineEdit()
            le.setPlaceholderText("Filter...")
            le.setFixedHeight(22)
            le.setStyleSheet("QLineEdit { border: 1px solid #ccc; padding: 1px 3px; font-size: 11px; }")
            col = i  # capture
            le.textChanged.connect(lambda text, c=col: self._on_text_changed(c, text))
            self._layout.addWidget(le)
            self._filters.append(le)

    def _on_text_changed(self, col: int, text: str):
        self._pending_col = col
        self._pending_text = text
        self._debounce_timer.start()

    def _emit_pending(self):
        self.filter_changed.emit(self._pending_col, self._pending_text)

    def sync_widths(self, header: QHeaderView):
        """Sync filter input widths with header section widths."""
        for i, f in enumerate(self._filters):
            if i < header.count():
                w = header.sectionSize(header.logicalIndex(i))
                f.setFixedWidth(w)

    def clear_all(self):
        for f in self._filters:
            f.blockSignals(True)
            f.clear()
            f.blockSignals(False)


class DataTableView(QTableView):
    """Configured QTableView with context menus, structure rendering, column filters."""

    def __init__(self, dataset: DataSet, undo_stack: QUndoStack | None = None, parent=None):
        super().__init__(parent)
        self._dataset = dataset
        self._undo_stack = undo_stack

        # Models
        self._source_model = DataFrameTableModel(dataset, undo_stack=undo_stack)
        self._proxy_model = FilterProxyModel(dataset)
        self._proxy_model.setSourceModel(self._source_model)
        self.setModel(self._proxy_model)

        # Structure delegate for all columns (checks SMILES_ROLE internally)
        self._structure_delegate = StructureDelegate(self)
        self.setItemDelegate(self._structure_delegate)

        # Table configuration
        self.setSortingEnabled(True)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Headers
        h_header = self.horizontalHeader()
        h_header.setStretchLastSection(True)
        h_header.setSectionsMovable(True)
        h_header.setMinimumSectionSize(40)
        h_header.setDefaultSectionSize(120)
        h_header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        h_header.customContextMenuRequested.connect(self._show_column_context_menu)
        # Intercept header clicks for multi-column sort (Shift+click)
        h_header.sectionClicked.connect(self._on_header_clicked)
        # Enable word-wrap in header labels
        h_header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)

        self.verticalHeader().setDefaultSectionSize(40)

        # Column filter bar
        self._filter_bar = ColumnFilterBar()
        self._filter_bar.filter_changed.connect(self._on_column_filter_changed)
        self._filter_bar.setVisible(False)
        self._filters_visible = False

        # Sync filter widths when header sections resize
        h_header.sectionResized.connect(lambda *_: self._sync_filter_widths())

        # Update row heights for SMILES columns when data changes
        dataset.data_changed.connect(self._adjust_row_heights)
        dataset.columns_changed.connect(self._on_columns_changed)

        # Frozen column view
        self._frozen_view: QTableView | None = None
        self._frozen_cols: list[int] = []

    def get_filter_bar(self) -> ColumnFilterBar:
        """Return the column filter bar widget (for embedding in a parent layout)."""
        return self._filter_bar

    @property
    def source_model(self) -> DataFrameTableModel:
        return self._source_model

    @property
    def proxy_model(self) -> FilterProxyModel:
        return self._proxy_model

    def reset_column_widths(self):
        """Reset all columns to default width."""
        default = self.horizontalHeader().defaultSectionSize()
        for i in range(self._proxy_model.columnCount()):
            self.setColumnWidth(i, default)
        self._sync_filter_widths()

    # ── Column filters ──

    def toggle_column_filters(self):
        """Show or hide the column filter bar."""
        self._filters_visible = not self._filters_visible
        if self._filters_visible:
            self._filter_bar.rebuild(self._dataset.column_count)
            self._sync_filter_widths()
            self._filter_bar.setVisible(True)
        else:
            self._filter_bar.setVisible(False)
            self._filter_bar.clear_all()
            self._proxy_model.clear_all_column_filters()

    def _on_column_filter_changed(self, col: int, text: str):
        self._proxy_model.set_column_filter(col, text)

    def _sync_filter_widths(self):
        if self._filters_visible:
            self._filter_bar.sync_widths(self.horizontalHeader())

    def _on_columns_changed(self):
        self._adjust_row_heights()
        if self._filters_visible:
            self._filter_bar.rebuild(self._dataset.column_count)
            self._sync_filter_widths()

    # ── Multi-column sorting ──

    def _on_header_clicked(self, logical_index: int):
        modifiers = QApplication.keyboardModifiers()
        order = Qt.SortOrder.AscendingOrder

        # Determine sort order — toggle if already sorting by this column
        current_keys = self._proxy_model.sort_keys
        for col, ord_ in current_keys:
            if col == logical_index:
                order = (Qt.SortOrder.DescendingOrder
                         if ord_ == Qt.SortOrder.AscendingOrder
                         else Qt.SortOrder.AscendingOrder)
                break

        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            self._proxy_model.add_sort_key(logical_index, order)
        else:
            self._proxy_model.set_sort_key(logical_index, order)

        # Trigger the actual sort
        self.sortByColumn(logical_index, order)

    # ── Frozen columns ──

    def freeze_column(self, col: int):
        """Freeze a column so it stays visible on the left while scrolling."""
        if col in self._frozen_cols:
            return
        self._frozen_cols.append(col)
        self._rebuild_frozen_view()

    def unfreeze_column(self, col: int):
        """Unfreeze a previously frozen column."""
        if col in self._frozen_cols:
            self._frozen_cols.remove(col)
            self._rebuild_frozen_view()

    def _rebuild_frozen_view(self):
        """Create or update the frozen column overlay."""
        # Disconnect old signals and remove old view
        if self._frozen_view:
            try:
                self.verticalScrollBar().valueChanged.disconnect(self._sync_frozen_scroll)
            except RuntimeError:
                pass
            self._frozen_view.deleteLater()
            self._frozen_view = None

        if not self._frozen_cols:
            return

        frozen = QTableView(self)
        frozen.setModel(self._proxy_model)
        frozen.setItemDelegate(StructureDelegate(frozen))
        frozen.setSelectionModel(self.selectionModel())

        frozen.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        frozen.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        frozen.verticalHeader().hide()
        frozen.horizontalHeader().hide()
        frozen.setAlternatingRowColors(True)
        frozen.setSortingEnabled(False)

        # Hide ALL columns, then show only frozen ones
        col_count = self._proxy_model.columnCount()
        for i in range(col_count):
            frozen.setColumnHidden(i, True)
        for c in self._frozen_cols:
            if c < col_count:
                frozen.setColumnHidden(c, False)
                frozen.setColumnWidth(c, self.columnWidth(c))

        # Sync vertical scrolling
        self._sync_frozen_scroll = frozen.verticalScrollBar().setValue
        self.verticalScrollBar().valueChanged.connect(self._sync_frozen_scroll)

        # Sync row heights
        frozen.verticalHeader().setDefaultSectionSize(
            self.verticalHeader().defaultSectionSize()
        )

        # Enable context menu on frozen view for unfreezing
        frozen.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        frozen.customContextMenuRequested.connect(self._show_frozen_context_menu)

        self._frozen_view = frozen
        self._update_frozen_geometry()
        frozen.show()
        frozen.raise_()

    def _show_frozen_context_menu(self, pos):
        """Context menu on the frozen column overlay — allows unfreezing."""
        menu = QMenu(self)
        for c in self._frozen_cols:
            col_name = self._dataset.column_name(c) if c < self._dataset.column_count else f"Col {c}"
            action = menu.addAction(f"Unfreeze Column '{col_name}'")
            action.triggered.connect(lambda checked, col=c: self.unfreeze_column(col))
        menu.exec(self._frozen_view.viewport().mapToGlobal(pos))

    def _update_frozen_geometry(self):
        """Position and size the frozen column overlay."""
        if not self._frozen_view or not self._frozen_cols:
            return
        total_width = sum(
            self.columnWidth(c) for c in self._frozen_cols
            if c < self._proxy_model.columnCount()
        )
        header_height = self.horizontalHeader().height()
        self._frozen_view.setFixedWidth(total_width + self._frozen_view.frameWidth() * 2)
        self._frozen_view.setFixedHeight(self.viewport().height())
        self._frozen_view.move(
            self.verticalHeader().width() + self.frameWidth(),
            self.frameWidth() + header_height
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_frozen_geometry()

    # ── Row heights ──

    def _adjust_row_heights(self):
        has_smiles = False
        for col in range(self._dataset.column_count):
            col_name = self._dataset.column_name(col)
            schema = self._dataset.get_schema(col_name)
            if schema.col_type == ColumnType.SMILES:
                has_smiles = True
                break
        if has_smiles:
            self.verticalHeader().setDefaultSectionSize(100)
        else:
            self.verticalHeader().setDefaultSectionSize(30)

    # ── Selection ──

    def get_selected_source_rows(self) -> list[int]:
        """Get selected source-model row indices (sorted)."""
        rows = set()
        for idx in self.selectionModel().selectedRows():
            source_idx = self._proxy_model.mapToSource(idx)
            rows.add(source_idx.row())
        return sorted(rows)

    def invert_selection(self):
        """Invert the current row selection."""
        sel_model = self.selectionModel()
        proxy = self._proxy_model
        total_rows = proxy.rowCount()
        total_cols = proxy.columnCount()
        if total_rows == 0:
            return

        new_selection = QItemSelection()
        currently_selected = set()
        for idx in sel_model.selectedRows():
            currently_selected.add(idx.row())

        for row in range(total_rows):
            if row not in currently_selected:
                top_left = proxy.index(row, 0)
                bottom_right = proxy.index(row, total_cols - 1)
                new_selection.select(top_left, bottom_right)

        sel_model.clearSelection()
        sel_model.select(new_selection, sel_model.SelectionFlag.Select)

    # ── Keyboard ──

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            self._copy_selection()
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            self._paste_clipboard()
            return
        super().keyPressEvent(event)

    def _copy_selection(self):
        """Copy selected cells as tab-separated text to clipboard."""
        indexes = self.selectionModel().selectedIndexes()
        if not indexes:
            return

        cells: dict[tuple[int, int], str] = {}
        for idx in indexes:
            source_idx = self._proxy_model.mapToSource(idx)
            row, col = source_idx.row(), source_idx.column()
            value = self._dataset.get_value(row, col)
            if value is None or (isinstance(value, float) and math.isnan(value)):
                cells[(row, col)] = ""
            else:
                cells[(row, col)] = str(value)

        if not cells:
            return

        rows = sorted(set(r for r, c in cells))
        cols = sorted(set(c for r, c in cells))

        lines = []
        for row in rows:
            line = "\t".join(cells.get((row, col), "") for col in cols)
            lines.append(line)

        QApplication.clipboard().setText("\n".join(lines))

    def _paste_clipboard(self):
        """Paste tab-separated text from clipboard into cells starting at current selection."""
        text = QApplication.clipboard().text()
        if not text:
            return

        indexes = self.selectionModel().selectedIndexes()
        if not indexes:
            return

        source_indexes = [self._proxy_model.mapToSource(idx) for idx in indexes]
        start_row = min(idx.row() for idx in source_indexes)
        start_col = min(idx.column() for idx in source_indexes)

        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines = lines[:-1]

        if self._undo_stack:
            self._undo_stack.beginMacro("Paste")

        from molview.models.undo_commands import CellEditCommand
        for r, line in enumerate(lines):
            values = line.split("\t")
            for c, val in enumerate(values):
                target_row = start_row + r
                target_col = start_col + c
                if target_row >= self._dataset.row_count or target_col >= self._dataset.column_count:
                    continue
                if self._undo_stack:
                    old_val = self._dataset.get_value(target_row, target_col)
                    if old_val != val:
                        self._undo_stack.push(
                            CellEditCommand(self._dataset, target_row, target_col, old_val, val)
                        )
                else:
                    self._dataset.set_value(target_row, target_col, val)

        if self._undo_stack:
            self._undo_stack.endMacro()

    # ── Context menus ──

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        selected_rows = self.get_selected_source_rows()

        # SMILES cell actions
        idx = self.indexAt(pos)
        if idx.isValid():
            source_idx = self._proxy_model.mapToSource(idx)
            col_name = self._dataset.column_name(source_idx.column())
            schema = self._dataset.get_schema(col_name)
            if schema.col_type == ColumnType.SMILES:
                smiles_val = self._dataset.get_value(source_idx.row(), source_idx.column())
                if smiles_val and str(smiles_val).strip():
                    copy_smiles = menu.addAction("Copy SMILES")
                    copy_smiles.triggered.connect(
                        lambda: QApplication.clipboard().setText(str(smiles_val))
                    )
                    edit_ketcher = menu.addAction("Edit in Ketcher...")
                    edit_ketcher.triggered.connect(
                        lambda: self._edit_in_ketcher(source_idx.row(), source_idx.column())
                    )
                    menu.addSeparator()

        if selected_rows:
            n = len(selected_rows)

            hide_action = menu.addAction(f"Hide {n} Selected Row(s)")
            hide_action.triggered.connect(lambda: self._hide_selected(selected_rows))

            hide_unsel_action = menu.addAction("Hide Unselected Rows")
            hide_unsel_action.triggered.connect(
                lambda: self._hide_unselected(selected_rows)
            )

            menu.addSeparator()

            export_action = menu.addAction(f"Export {n} Selected Row(s)...")
            export_action.triggered.connect(self._export_selected_from_context)

            menu.addSeparator()

            delete_action = menu.addAction(f"Delete {n} Selected Row(s)")
            delete_action.triggered.connect(lambda: self._delete_rows(selected_rows))

            menu.addSeparator()

        # Copy/Paste
        copy_action = menu.addAction("Copy")
        copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        copy_action.triggered.connect(self._copy_selection)

        paste_action = menu.addAction("Paste")
        paste_action.setShortcut(QKeySequence.StandardKey.Paste)
        paste_action.triggered.connect(self._paste_clipboard)

        menu.addSeparator()

        if self._dataset.hidden_rows:
            show_all = menu.addAction(
                f"Show All Hidden Rows ({len(self._dataset.hidden_rows)})"
            )
            show_all.triggered.connect(self._dataset.show_all_rows)
            menu.addSeparator()

        add_row = menu.addAction("Add Row")
        add_row.triggered.connect(self._add_row)

        add_col = menu.addAction("Add Column...")
        add_col.triggered.connect(self._add_column_dialog)

        menu.exec(self.viewport().mapToGlobal(pos))

    def _show_column_context_menu(self, pos):
        col = self.horizontalHeader().logicalIndexAt(pos)
        if col < 0:
            return

        menu = QMenu(self)
        col_name = self._dataset.column_name(col)
        schema = self._dataset.get_schema(col_name)

        # Format submenu
        format_menu = menu.addMenu("Set Column Format")
        for ct in [ColumnType.TEXT, ColumnType.NUMERIC, ColumnType.SMILES]:
            action = format_menu.addAction(ct.name)
            current = schema.col_type == ct
            action.setCheckable(True)
            action.setChecked(current)
            action.triggered.connect(
                lambda checked, c=col_name, t=ct: self._set_column_type(c, t)
            )

        # Decimal places (for numeric)
        if schema.col_type == ColumnType.NUMERIC:
            dec_menu = menu.addMenu("Decimal Places")
            for d in range(0, 7):
                act = dec_menu.addAction(str(d))
                act.setCheckable(True)
                act.setChecked(schema.decimal_places == d)
                act.triggered.connect(
                    lambda checked, c=col_name, dp=d: self._set_decimal_places(c, dp)
                )

        menu.addSeparator()

        # Sort
        sort_asc = menu.addAction(f"Sort '{col_name}' Ascending")
        sort_asc.triggered.connect(lambda: self.sortByColumn(col, Qt.SortOrder.AscendingOrder))
        sort_desc = menu.addAction(f"Sort '{col_name}' Descending")
        sort_desc.triggered.connect(lambda: self.sortByColumn(col, Qt.SortOrder.DescendingOrder))

        menu.addSeparator()

        # Freeze/unfreeze
        if col in self._frozen_cols:
            unfreeze = menu.addAction(f"Unfreeze Column '{col_name}'")
            unfreeze.triggered.connect(lambda: self.unfreeze_column(col))
        else:
            freeze = menu.addAction(f"Freeze Column '{col_name}'")
            freeze.triggered.connect(lambda: self.freeze_column(col))

        menu.addSeparator()

        rename_action = menu.addAction(f"Rename Column '{col_name}'...")
        rename_action.triggered.connect(lambda: self._rename_column(col))

        delete_action = menu.addAction(f"Delete Column '{col_name}'")
        delete_action.triggered.connect(lambda: self._delete_column(col))

        menu.addSeparator()

        reset_widths = menu.addAction("Reset All Column Widths")
        reset_widths.triggered.connect(self.reset_column_widths)

        menu.exec(self.horizontalHeader().mapToGlobal(pos))

    # ── SMILES cell actions ──

    def _edit_in_ketcher(self, row: int, col: int):
        """Open the SMILES value in Ketcher, write back on accept."""
        try:
            from molview.gui.structure_editor.editor_dialog import StructureEditorDialog
        except ImportError:
            return

        smiles = str(self._dataset.get_value(row, col))

        # Try to get pre-loaded Ketcher from main window
        preloaded = None
        main_win = self.window()
        if main_win and hasattr(main_win, '_take_preloaded_ketcher'):
            preloaded = main_win._take_preloaded_ketcher()

        self._ketcher_edit_row = row
        self._ketcher_edit_col = col
        self._editor_dlg = StructureEditorDialog(
            self, initial_smiles=smiles, preloaded_view=preloaded
        )
        self._editor_dlg.finished.connect(self._on_ketcher_edit_finished)
        self._editor_dlg.open()

    def _on_ketcher_edit_finished(self, result: int):
        from PySide6.QtWidgets import QDialog
        dlg = self._editor_dlg
        self._editor_dlg = None
        if dlg and result == QDialog.DialogCode.Accepted:
            new_smiles = dlg.get_smiles()
            if new_smiles:
                row = self._ketcher_edit_row
                col = self._ketcher_edit_col
                if self._undo_stack:
                    from molview.models.undo_commands import CellEditCommand
                    old_val = self._dataset.get_value(row, col)
                    if old_val != new_smiles:
                        self._undo_stack.push(
                            CellEditCommand(self._dataset, row, col, old_val, new_smiles)
                        )
                else:
                    self._dataset.set_value(row, col, new_smiles)
        if dlg:
            dlg.deleteLater()

    # ── Row operations ──

    def _hide_selected(self, rows: list[int]):
        self._dataset.hide_rows(set(rows))
        self.clearSelection()

    def _hide_unselected(self, selected_rows: list[int]):
        selected_set = set(selected_rows)
        all_rows = set(range(self._dataset.row_count))
        to_hide = all_rows - selected_set - self._dataset.hidden_rows
        self._dataset.hide_rows(to_hide)

    def _add_row(self):
        if self._undo_stack:
            self._undo_stack.push(AddRowCommand(self._dataset))
        else:
            self._dataset.add_row()

    def _delete_rows(self, rows: list[int]):
        reply = QMessageBox.question(
            self, "Delete Rows",
            f"Delete {len(rows)} row(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self._undo_stack:
                self._undo_stack.push(DeleteRowsCommand(self._dataset, rows))
            else:
                self._dataset.delete_rows(rows)

    def _export_selected_from_context(self):
        """Trigger export-selected from the main window."""
        window = self.window()
        if hasattr(window, "_export_selected"):
            window._export_selected()

    # ── Column operations ──

    def _add_column_dialog(self):
        name, ok = QInputDialog.getText(self, "Add Column", "Column name:")
        if ok and name.strip():
            name = name.strip()
            if name in self._dataset.df.columns:
                QMessageBox.warning(self, "Error", f"Column '{name}' already exists.")
                return
            if self._undo_stack:
                self._undo_stack.push(AddColumnCommand(self._dataset, name))
            else:
                self._dataset.add_column(name)

    def _rename_column(self, col: int):
        old_name = self._dataset.column_name(col)
        new_name, ok = QInputDialog.getText(
            self, "Rename Column", f"New name for '{old_name}':", text=old_name
        )
        if ok and new_name.strip() and new_name.strip() != old_name:
            new_name = new_name.strip()
            if new_name in self._dataset.df.columns:
                QMessageBox.warning(self, "Error", f"Column '{new_name}' already exists.")
                return
            if self._undo_stack:
                self._undo_stack.push(RenameColumnCommand(self._dataset, old_name, new_name))
            else:
                self._dataset.df.rename(columns={old_name: new_name}, inplace=True)
                if old_name in self._dataset.schemas:
                    schema = self._dataset.schemas.pop(old_name)
                    schema.name = new_name
                    self._dataset.schemas[new_name] = schema
                self._dataset.modified = True
                self._dataset.columns_changed.emit()

    def _delete_column(self, col: int):
        col_name = self._dataset.column_name(col)
        reply = QMessageBox.question(
            self, "Delete Column",
            f"Delete column '{col_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self._undo_stack:
                self._undo_stack.push(DeleteColumnCommand(self._dataset, col))
            else:
                self._dataset.delete_column(col)

    def _set_column_type(self, col_name: str, col_type: ColumnType):
        old_schema = self._dataset.get_schema(col_name)
        new_schema = ColumnSchema(col_name, col_type, old_schema.decimal_places)
        if self._undo_stack:
            self._undo_stack.push(SetColumnFormatCommand(self._dataset, col_name, old_schema, new_schema))
        else:
            self._dataset.set_schema(col_name, new_schema)
        self._adjust_row_heights()

    def _set_decimal_places(self, col_name: str, places: int):
        old_schema = self._dataset.get_schema(col_name)
        new_schema = ColumnSchema(col_name, old_schema.col_type, places)
        if self._undo_stack:
            self._undo_stack.push(SetColumnFormatCommand(self._dataset, col_name, old_schema, new_schema))
        else:
            self._dataset.set_schema(col_name, new_schema)
