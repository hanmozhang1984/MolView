"""MolView application entry point."""

import sys


def main():
    # Suppress RDKit warnings cluttering stderr
    from rdkit import RDLogger
    RDLogger.logger().setLevel(RDLogger.ERROR)

    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont, QFontDatabase

    app = QApplication(sys.argv)
    app.setApplicationName("MolView")
    app.setOrganizationName("MolView")
    app.setStyle("Fusion")

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
