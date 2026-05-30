import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from mloader.gui.main_window import MainWindow

def main() -> int:
    app = QApplication(sys.argv)
    
    qss_file_path = Path(__file__).parent / "gui" / "styles" / "dark.qss"
    app.setStyleSheet(qss_file_path.read_text(encoding="utf-8"))
    
    window = MainWindow()
    window.show()

    return app.exec()
