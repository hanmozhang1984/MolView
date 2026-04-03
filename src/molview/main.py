"""MolView application entry point."""

import sys


def main():
    # Suppress RDKit warnings cluttering stderr
    from rdkit import RDLogger
    RDLogger.logger().setLevel(RDLogger.ERROR)

    from pathlib import Path
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont, QFontDatabase, QIcon

    app = QApplication(sys.argv)
    app.setApplicationName("MolView")
    app.setOrganizationName("MolView")
    app.setStyle("Fusion")

    # App icon (shown in dock, window title bar, task switcher)
    icon_path = Path(__file__).parent / "gui" / "molview_icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Global font: Aptos if available, else Helvetica Neue (macOS), else system default
    available = set(QFontDatabase.families())
    for family in ("Aptos", "Helvetica Neue", "Helvetica", "Segoe UI"):
        if family in available:
            font = QFont(family, 13)
            app.setFont(font)
            break

    from molview.gui.main_window import MainWindow
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
