"""Light and dark theme stylesheets for MolView."""

LIGHT_STYLE = """
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
"""

DARK_STYLE = """
    QMainWindow, QDialog, QWidget {
        background: #2b2b2b;
        color: #e0e0e0;
    }
    QMenuBar {
        background: #333333;
        border-bottom: 1px solid #555;
        padding: 2px 0px;
        color: #e0e0e0;
    }
    QMenuBar::item {
        padding: 4px 10px;
        border-radius: 4px;
        color: #e0e0e0;
    }
    QMenuBar::item:selected {
        background: #505060;
    }
    QMenu {
        background: #3a3a3a;
        padding: 4px 0px;
        color: #e0e0e0;
        border: 1px solid #555;
    }
    QMenu::item {
        padding: 5px 28px 5px 20px;
    }
    QMenu::item:selected {
        background: #505060;
    }
    QMenu::separator {
        height: 1px;
        background: #555;
        margin: 3px 8px;
    }
    QToolBar {
        background: #333333;
        border-bottom: 1px solid #555;
        spacing: 3px;
        padding: 2px 6px;
    }
    QToolButton {
        background: transparent;
        border: 1px solid transparent;
        border-radius: 4px;
        padding: 4px 8px;
        color: #e0e0e0;
    }
    QToolButton:hover {
        background: #4a4a5a;
        border: 1px solid #666;
    }
    QToolButton:pressed {
        background: #555568;
    }
    QToolBar::separator {
        width: 1px;
        background: #555;
        margin: 3px 4px;
    }
    QStatusBar {
        background: #333333;
        border-top: 1px solid #555;
        color: #e0e0e0;
    }
    QTableView {
        background: #2b2b2b;
        alternate-background-color: #323232;
        gridline-color: #444;
        selection-background-color: #3a4a6a;
        selection-color: #e0e0e0;
        color: #e0e0e0;
    }
    QHeaderView::section {
        background: #3a3a3a;
        border: none;
        border-right: 1px solid #555;
        border-bottom: 1px solid #555;
        padding: 4px 4px;
        text-align: center;
        color: #e0e0e0;
    }
    QLabel {
        color: #e0e0e0;
    }
    QLineEdit, QTextEdit {
        background: #3a3a3a;
        border: 1px solid #555;
        color: #e0e0e0;
        border-radius: 3px;
        padding: 2px 4px;
    }
    QComboBox {
        background: #3a3a3a;
        border: 1px solid #555;
        color: #e0e0e0;
        border-radius: 3px;
        padding: 2px 4px;
    }
    QComboBox QAbstractItemView {
        background: #3a3a3a;
        color: #e0e0e0;
        selection-background-color: #505060;
    }
    QComboBox::drop-down {
        border: none;
    }
    QPushButton {
        background: #3a3a3a;
        border: 1px solid #555;
        color: #e0e0e0;
        border-radius: 4px;
        padding: 4px 12px;
    }
    QPushButton:hover {
        background: #4a4a5a;
    }
    QPushButton:pressed {
        background: #555568;
    }
    QCheckBox, QRadioButton {
        color: #e0e0e0;
    }
    QSpinBox, QDoubleSpinBox {
        background: #3a3a3a;
        border: 1px solid #555;
        color: #e0e0e0;
        border-radius: 3px;
    }
    QGroupBox {
        border: 1px solid #555;
        border-radius: 4px;
        margin-top: 8px;
        padding-top: 8px;
        color: #e0e0e0;
    }
    QGroupBox::title {
        color: #e0e0e0;
    }
    QProgressBar {
        background: #3a3a3a;
        border: 1px solid #555;
        border-radius: 3px;
        text-align: center;
        color: #e0e0e0;
    }
    QProgressBar::chunk {
        background: #4a6a9a;
    }
    QScrollBar:vertical {
        background: #2b2b2b;
        width: 12px;
    }
    QScrollBar::handle:vertical {
        background: #555;
        border-radius: 4px;
        min-height: 20px;
    }
    QScrollBar:horizontal {
        background: #2b2b2b;
        height: 12px;
    }
    QScrollBar::handle:horizontal {
        background: #555;
        border-radius: 4px;
        min-width: 20px;
    }
    QTabWidget::pane {
        border: 1px solid #555;
        background: #2b2b2b;
    }
    QTabBar::tab {
        background: #3a3a3a;
        color: #e0e0e0;
        padding: 6px 12px;
        border: 1px solid #555;
    }
    QTabBar::tab:selected {
        background: #2b2b2b;
    }
    QSplitter::handle {
        background: #555;
    }
"""
