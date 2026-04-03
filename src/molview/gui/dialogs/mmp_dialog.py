"""Dialog for Matched Molecular Pair (MMP) analysis with structure visualization."""
from __future__ import annotations

import io
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QDialogButtonBox, QProgressBar, QGroupBox, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QSpinBox,
    QSplitter, QFrame, QWidget, QListWidget, QAbstractItemView,
)

from molview.models.dataset import DataSet
from molview.models.column_schema import ColumnType
from molview.chem.mmp import find_matched_pairs


def _smiles_to_pixmap(smiles: str, width: int = 250, height: int = 180) -> QPixmap | None:
    """Render a SMILES string to a QPixmap."""
    try:
        from rdkit import Chem
        from rdkit.Chem import Draw
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        img = Draw.MolToImage(mol, size=(width, height))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        qimg = QImage()
        qimg.loadFromData(buf.getvalue())
        return QPixmap.fromImage(qimg)
    except Exception:
        return None


class _StructureLabel(QLabel):
    """A QLabel that displays a molecular structure with a caption."""

    def __init__(self, caption: str = "", parent=None):
        super().__init__(parent)
        self._caption = caption
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(200, 140)
        self.setStyleSheet(
            "QLabel { background: white; border: 1px solid #ccc; border-radius: 4px; padding: 4px; }"
        )
        self._set_text_only(caption)

    def _set_text_only(self, text: str):
        self.setText(f"<center><b>{self._caption}</b><br><i style='color:#888'>{text}</i></center>")

    def set_structure(self, smiles: str):
        """Render and display a molecule from SMILES."""
        if not smiles or not smiles.strip():
            self._set_text_only("(empty)")
            return
        pixmap = _smiles_to_pixmap(smiles, 250, 160)
        if pixmap:
            self.setPixmap(pixmap)
        else:
            self._set_text_only(smiles[:40])


class MMPWorker(QThread):
    progress = Signal(int)
    finished = Signal(object)  # DataFrame
    error = Signal(str)

    def __init__(self, smiles_series, property_col, data_cols, max_cuts,
                 min_context_atoms, max_rgroup_atoms):
        super().__init__()
        self._smiles = smiles_series
        self._property = property_col
        self._data_cols = data_cols
        self._max_cuts = max_cuts
        self._min_ctx = min_context_atoms
        self._max_rg = max_rgroup_atoms

    def run(self):
        try:
            result = find_matched_pairs(
                self._smiles, self._property, self._data_cols,
                self._max_cuts, self._min_ctx, self._max_rg,
                self.progress.emit
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class MMPDialog(QDialog):
    def __init__(self, dataset: DataSet, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Matched Molecular Pair Analysis")
        self.setMinimumSize(1100, 850)
        self.resize(1200, 900)
        self._dataset = dataset
        self._worker = None
        self._result_df = None

        layout = QVBoxLayout(self)

        # Input controls
        input_group = QGroupBox("Input")
        input_layout = QVBoxLayout()

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("SMILES Column:"))
        self._smiles_combo = QComboBox()
        for i in range(dataset.column_count):
            col_name = dataset.column_name(i)
            schema = dataset.get_schema(col_name)
            if schema.col_type in (ColumnType.SMILES, ColumnType.TEXT):
                self._smiles_combo.addItem(col_name)
        row1.addWidget(self._smiles_combo)
        input_layout.addLayout(row1)

        # Auto-select SMILES column
        for i in range(self._smiles_combo.count()):
            name = self._smiles_combo.itemText(i)
            if dataset.get_schema(name).col_type == ColumnType.SMILES:
                self._smiles_combo.setCurrentIndex(i)
                break

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Property Column (optional):"))
        self._prop_combo = QComboBox()
        self._prop_combo.addItem("(None)")
        for i in range(dataset.column_count):
            col_name = dataset.column_name(i)
            schema = dataset.get_schema(col_name)
            if schema.col_type == ColumnType.NUMERIC:
                self._prop_combo.addItem(col_name)
        row2.addWidget(self._prop_combo)
        input_layout.addLayout(row2)

        row_data = QHBoxLayout()
        row_data.addWidget(QLabel("Data Columns (optional):"))
        self._data_list = QListWidget()
        self._data_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self._data_list.setMaximumHeight(55)
        # Add all non-SMILES columns
        for i in range(dataset.column_count):
            col_name = dataset.column_name(i)
            schema = dataset.get_schema(col_name)
            if schema.col_type != ColumnType.SMILES:
                self._data_list.addItem(col_name)
        row_data.addWidget(self._data_list)
        input_layout.addLayout(row_data)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Max Cuts:"))
        self._cuts_spin = QSpinBox()
        self._cuts_spin.setRange(1, 2)
        self._cuts_spin.setValue(1)
        row3.addWidget(self._cuts_spin)

        row3.addWidget(QLabel("  Min scaffold atoms:"))
        self._min_ctx_spin = QSpinBox()
        self._min_ctx_spin.setRange(1, 30)
        self._min_ctx_spin.setValue(6)
        self._min_ctx_spin.setToolTip("Minimum heavy atoms in the shared scaffold. "
                                       "Increase to require larger common cores.")
        row3.addWidget(self._min_ctx_spin)

        row3.addWidget(QLabel("  Max R-group atoms:"))
        self._max_rg_spin = QSpinBox()
        self._max_rg_spin.setRange(1, 50)
        self._max_rg_spin.setValue(13)
        self._max_rg_spin.setToolTip("Maximum heavy atoms in the variable R-group. "
                                      "Decrease to restrict to smaller structural changes.")
        row3.addWidget(self._max_rg_spin)

        row3.addStretch()
        input_layout.addLayout(row3)

        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # Progress
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Splitter: results table (top) + structure detail (bottom)
        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter.setVisible(False)
        layout.addWidget(self._splitter, stretch=1)

        # Results table
        results_widget = QWidget()
        results_layout = QVBoxLayout(results_widget)
        results_layout.setContentsMargins(0, 0, 0, 0)

        self._results_label = QLabel("Results:")
        results_layout.addWidget(self._results_label)

        self._results_table = QTableWidget()
        self._results_table.setAlternatingRowColors(True)
        self._results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._results_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._results_table.horizontalHeader().setStretchLastSection(True)
        self._results_table.currentCellChanged.connect(self._on_row_selected)
        results_layout.addWidget(self._results_table)

        self._splitter.addWidget(results_widget)

        # Structure detail panel
        detail_widget = QWidget()
        detail_widget.setStyleSheet("background: #f8f8f8;")
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(8, 8, 8, 8)

        detail_label = QLabel("Click a pair above to view structures:")
        detail_label.setStyleSheet("font-weight: bold; background: transparent;")
        detail_layout.addWidget(detail_label)

        # Structure images row: Mol A | Context (Scaffold) | Mol B
        struct_row = QHBoxLayout()

        # Mol A
        mol_a_col = QVBoxLayout()
        self._mol_a_label = _StructureLabel("Molecule A")
        self._mol_a_id = QLabel("")
        self._mol_a_id.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mol_a_id.setStyleSheet("font-size: 11px; background: transparent;")
        mol_a_col.addWidget(self._mol_a_label)
        mol_a_col.addWidget(self._mol_a_id)
        struct_row.addLayout(mol_a_col)

        # Context (shared scaffold)
        ctx_col = QVBoxLayout()
        self._ctx_label = _StructureLabel("Shared Scaffold")
        ctx_col.addWidget(self._ctx_label)
        struct_row.addLayout(ctx_col)

        # Mol B
        mol_b_col = QVBoxLayout()
        self._mol_b_label = _StructureLabel("Molecule B")
        self._mol_b_id = QLabel("")
        self._mol_b_id.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mol_b_id.setStyleSheet("font-size: 11px; background: transparent;")
        mol_b_col.addWidget(self._mol_b_label)
        mol_b_col.addWidget(self._mol_b_id)
        struct_row.addLayout(mol_b_col)

        detail_layout.addLayout(struct_row)

        # R-group comparison row
        rgroup_row = QHBoxLayout()
        self._ra_label = _StructureLabel("R-group A")
        self._arrow_label = QLabel("\u2192")
        self._arrow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._arrow_label.setStyleSheet("font-size: 28px; font-weight: bold; background: transparent;")
        self._rb_label = _StructureLabel("R-group B")
        self._delta_label = QLabel("")
        self._delta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._delta_label.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #2a7ae2; background: transparent;"
        )

        rgroup_row.addWidget(self._ra_label)
        rgroup_row.addWidget(self._arrow_label)
        rgroup_row.addWidget(self._rb_label)
        rgroup_row.addWidget(self._delta_label)

        detail_layout.addLayout(rgroup_row)

        self._splitter.addWidget(detail_widget)
        self._splitter.setSizes([500, 300])

        # Buttons
        btn_layout = QHBoxLayout()
        self._run_btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        self._run_btn.button(QDialogButtonBox.StandardButton.Ok).setText("Run Analysis")
        self._run_btn.accepted.connect(self._run)

        self._close_btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self._close_btn.rejected.connect(self.reject)

        btn_layout.addWidget(self._run_btn)
        btn_layout.addWidget(self._close_btn)
        layout.addLayout(btn_layout)

    def _run(self):
        smiles_col = self._smiles_combo.currentText()
        if not smiles_col:
            return

        prop_col_name = self._prop_combo.currentText()
        property_col = None
        if prop_col_name and prop_col_name != "(None)":
            property_col = self._dataset.df[prop_col_name]

        # Gather selected data columns
        data_cols = {}
        for item in self._data_list.selectedItems():
            col_name = item.text()
            if col_name in self._dataset.df.columns:
                data_cols[col_name] = self._dataset.df[col_name]

        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._run_btn.setEnabled(False)

        self._worker = MMPWorker(
            self._dataset.df[smiles_col],
            property_col,
            data_cols if data_cols else None,
            self._cuts_spin.value(),
            self._min_ctx_spin.value(),
            self._max_rg_spin.value(),
        )
        self._worker.progress.connect(self._progress.setValue)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_finished(self, result):
        self._run_btn.setEnabled(True)
        self._progress.setVisible(False)

        if result is None or result.empty:
            QMessageBox.information(self, "MMP Analysis", "No matched molecular pairs found.")
            return

        self._result_df = result
        self._splitter.setVisible(True)

        # Detect ID column
        self._id_col = None
        for col in self._dataset.df.columns:
            if col.lower() in ('compound_id', 'id', 'name', 'compound_name', 'mol_id'):
                self._id_col = col
                break

        # Find data column pairs in the result (e.g. IC50_A, IC50_B)
        data_col_names = []
        for col in result.columns:
            if col.endswith('_A') and col not in ('Mol_A', 'R_A', 'Property_A', 'Mol_A_idx'):
                base = col[:-2]
                if f'{base}_B' in result.columns:
                    data_col_names.append(base)

        self._results_label.setText(
            f"Results: {len(result)} pair(s) found — click a row to view structures. "
            f"Click column headers to sort."
        )

        # Build table headers and a mapping to result data
        # Each entry: (header_label, extractor_func)
        self._table_columns = []

        if self._id_col:
            self._table_columns.append(('Compound A', lambda r: self._get_id(r, 'Mol_A_idx')))
            self._table_columns.append(('Compound B', lambda r: self._get_id(r, 'Mol_B_idx')))

        self._table_columns.append(('R_A', lambda r: str(r['R_A'])))
        self._table_columns.append(('R_B', lambda r: str(r['R_B'])))

        if 'Delta' in result.columns:
            prop_name = self._prop_combo.currentText()
            self._table_columns.append((
                f'{prop_name}_A',
                lambda r: self._fmt_num(r.get('Property_A'))
            ))
            self._table_columns.append((
                f'{prop_name}_B',
                lambda r: self._fmt_num(r.get('Property_B'))
            ))
            self._table_columns.append((
                f'\u0394 {prop_name}',
                lambda r: self._fmt_num(r.get('Delta'))
            ))

        for base in data_col_names:
            self._table_columns.append((
                f'{base}_A',
                lambda r, b=base: self._fmt_val(r.get(f'{b}_A'))
            ))
            self._table_columns.append((
                f'{base}_B',
                lambda r, b=base: self._fmt_val(r.get(f'{b}_B'))
            ))

        # Populate table
        headers = [h for h, _ in self._table_columns]
        n_display = min(len(result), 1000)

        # Disable sorting while populating
        self._results_table.setSortingEnabled(False)
        self._results_table.setColumnCount(len(headers))
        self._results_table.setHorizontalHeaderLabels(headers)
        self._results_table.setRowCount(n_display)

        for row_idx in range(n_display):
            pair = result.iloc[row_idx]
            for col_idx, (_, extractor) in enumerate(self._table_columns):
                text = extractor(pair)
                item = QTableWidgetItem()
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                # Store numeric value for proper sorting
                try:
                    num = float(text)
                    item.setData(Qt.ItemDataRole.DisplayRole, text)
                    item.setData(Qt.ItemDataRole.UserRole, num)
                except (ValueError, TypeError):
                    item.setData(Qt.ItemDataRole.DisplayRole, text)
                    item.setData(Qt.ItemDataRole.UserRole, text)
                self._results_table.setItem(row_idx, col_idx, item)

        # Enable sorting by clicking headers
        self._results_table.setSortingEnabled(True)
        self._results_table.resizeColumnsToContents()

    def _get_id(self, pair, idx_col):
        """Get compound ID for a pair member."""
        idx = int(pair[idx_col])
        if self._id_col and idx < len(self._dataset.df):
            return str(self._dataset.df.iloc[idx][self._id_col])
        return str(idx)

    @staticmethod
    def _fmt_num(val):
        if val is None or (isinstance(val, float) and val != val):
            return ""
        try:
            return f"{float(val):.3f}"
        except (ValueError, TypeError):
            return str(val)

    @staticmethod
    def _fmt_val(val):
        if val is None or (isinstance(val, float) and val != val):
            return ""
        return str(val)

    def _set_table_item(self, row, col, text):
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._results_table.setItem(row, col, item)

    def _on_row_selected(self, row, col, prev_row, prev_col):
        """Update structure detail panel when a pair is selected."""
        if self._result_df is None or row < 0:
            return

        # When sorting is enabled, the visual row doesn't match the data row.
        # Use the Compound A ID or Mol_A_idx to find the original result row.
        # We stored Mol_A SMILES in the result_df, so match via that.
        # Simplest: read Mol_A_idx from the id column item or find via R_A/R_B text
        # Actually, let's store the result index in each row's first item's UserRole+1
        # Better approach: read the compound IDs from the visible row and find the pair

        # Find the result row by matching R_A and R_B text from visible table cells
        r_a_col = next((i for i, (h, _) in enumerate(self._table_columns) if h == 'R_A'), None)
        r_b_col = next((i for i, (h, _) in enumerate(self._table_columns) if h == 'R_B'), None)
        if r_a_col is None or r_b_col is None:
            return
        r_a_item = self._results_table.item(row, r_a_col)
        r_b_item = self._results_table.item(row, r_b_col)
        if not r_a_item or not r_b_item:
            return

        r_a_text = r_a_item.text()
        r_b_text = r_b_item.text()

        # Find matching pair in result_df
        match = self._result_df[
            (self._result_df['R_A'] == r_a_text) & (self._result_df['R_B'] == r_b_text)
        ]
        if match.empty:
            return
        pair = match.iloc[0]
        mol_a_smi = pair['Mol_A']
        mol_b_smi = pair['Mol_B']
        context_smi = pair['Context']
        r_a_smi = pair['R_A']
        r_b_smi = pair['R_B']

        # Render structures
        self._mol_a_label.set_structure(mol_a_smi)
        self._mol_b_label.set_structure(mol_b_smi)
        self._ctx_label.set_structure(context_smi)
        self._ra_label.set_structure(r_a_smi)
        self._rb_label.set_structure(r_b_smi)

        # Show compound IDs if available
        a_idx = int(pair['Mol_A_idx'])
        b_idx = int(pair['Mol_B_idx'])
        id_col = None
        for col_name in self._dataset.df.columns:
            if col_name.lower() in ('compound_id', 'id', 'name', 'compound_name', 'mol_id'):
                id_col = col_name
                break

        if id_col:
            a_id = self._dataset.df.iloc[a_idx][id_col] if a_idx < len(self._dataset.df) else ""
            b_id = self._dataset.df.iloc[b_idx][id_col] if b_idx < len(self._dataset.df) else ""
            self._mol_a_id.setText(str(a_id))
            self._mol_b_id.setText(str(b_id))
        else:
            self._mol_a_id.setText(f"Row {a_idx + 1}")
            self._mol_b_id.setText(f"Row {b_idx + 1}")

        # Show delta if available
        if 'Delta' in pair and pair['Delta'] == pair['Delta']:  # NaN check
            prop_name = self._prop_combo.currentText()
            delta = pair['Delta']
            sign = "+" if delta > 0 else ""
            self._delta_label.setText(f"\u0394 {prop_name}\n{sign}{delta:.3f}")
        else:
            self._delta_label.setText("")

    def _on_error(self, msg: str):
        self._run_btn.setEnabled(True)
        self._progress.setVisible(False)
        QMessageBox.critical(self, "MMP Error", msg)
