from PySide6 import QtWidgets


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("MLoader")
        self.setGeometry(100, 100, 800, 600)
        
        # self.layout = QtWidgets.QVBoxLayout(self)
        # self.layout.addWidget(self.button)
        