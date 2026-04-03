"""Keyboard shortcut cheat sheet dialog."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QDialogButtonBox, QHeaderView, QLabel,
)


# Shortcuts organized by category
SHORTCUTS = [
    ("File", [
        ("Ctrl+O", "Open file"),
        ("Ctrl+S", "Save"),
        ("Ctrl+Shift+S", "Save As"),
        ("Ctrl+E", "Export selected rows"),
        ("Ctrl+Q", "Quit"),
    ]),
    ("Edit", [
        ("Ctrl+Z", "Undo"),
        ("Ctrl+Shift+Z", "Redo"),
        ("Ctrl+C", "Copy cells"),
        ("Ctrl+V", "Paste cells"),
        ("Ctrl+A", "Select all rows"),
        ("Ctrl+D", "Deselect all"),
        ("Ctrl+I", "Invert selection"),
        ("Ctrl+H", "Hide selected rows"),
        ("Ctrl+Shift+H", "Show all hidden rows"),
        ("Delete", "Delete selected rows"),
    ]),
    ("View", [
        ("Ctrl+1", "Switch to Data Table"),
        ("Ctrl+2", "Switch to Plot Panel"),
        ("Ctrl+L", "Toggle column filters"),
    ]),
    ("Chemistry", [
        ("Ctrl+P", "Calculate properties"),
        ("Ctrl+F", "Structure search"),
        ("Escape", "Clear search / show all"),
    ]),
    ("Table", [
        ("Click header", "Sort by column"),
        ("Shift+Click header", "Add secondary sort"),
        ("Right-click header", "Column options (format, freeze, rename, delete)"),
        ("Right-click cell", "Row options (copy SMILES, edit in Ketcher)"),
    ]),
    ("Plot", [
        ("Click point", "Select single point"),
        ("Shift+Click point", "Add/remove from selection"),
        ("Click+Drag", "Rectangle select multiple points"),
        ("Shift+Drag", "Add rectangle to selection"),
    ]),
    ("Help", [
        ("Ctrl+/", "Show this shortcut cheat sheet"),
    ]),
]


class ShortcutsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.setMinimumSize(500, 550)
        self.resize(520, 600)

        layout = QVBoxLayout(self)

        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Category", "Shortcut", "Action"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

        # Count total rows
        total = sum(len(shortcuts) for _, shortcuts in SHORTCUTS)
        table.setRowCount(total)

        row = 0
        for category, shortcuts in SHORTCUTS:
            for i, (key, desc) in enumerate(shortcuts):
                cat_item = QTableWidgetItem(category if i == 0 else "")
                cat_item.setForeground(Qt.GlobalColor.darkBlue)
                if i == 0:
                    font = cat_item.font()
                    font.setBold(True)
                    cat_item.setFont(font)

                key_item = QTableWidgetItem(key)
                key_item.setForeground(Qt.GlobalColor.darkRed)
                font = key_item.font()
                font.setBold(True)
                key_item.setFont(font)

                desc_item = QTableWidgetItem(desc)

                table.setItem(row, 0, cat_item)
                table.setItem(row, 1, key_item)
                table.setItem(row, 2, desc_item)
                row += 1

        layout.addWidget(table)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
