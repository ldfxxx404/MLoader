from PySide6 import QtCore, QtGui, QtWidgets

from mloader.downloader.service import DownloadSource


class TrackCard(QtWidgets.QWidget):
    play_clicked = QtCore.Signal()

    def __init__(self, source: DownloadSource, artwork: bytes, index: int, parent=None):
        super().__init__(parent)

        self.source = source
        self.index = index

        self.setObjectName("downloadCard")

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        self.checkbox = QtWidgets.QCheckBox()
        self.checkbox.setChecked(True)

        self.play_button = QtWidgets.QPushButton("Play")
        self.play_button.setObjectName("playButton")
        self.play_button.setFixedSize(58, 34)
        self.play_button.setToolTip("Preview track")
        self.play_button.clicked.connect(self.play_clicked.emit)

        self.artwork_label = QtWidgets.QLabel("♪")
        self.artwork_label.setObjectName("artworkLabel")
        self.artwork_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.artwork_label.setFixedSize(68, 68)

        self._set_artwork(artwork)

        title = source.title

        self.title_label = QtWidgets.QLabel(title)
        self.title_label.setObjectName("trackTitle")

        self._detail_label = QtWidgets.QLabel(source.page_url)
        self._detail_label.setObjectName("trackUrl")
        self._detail_label.setWordWrap(True)

        self.status_label = QtWidgets.QLabel("Ready")
        self.status_label.setObjectName("trackStatus")
        self.status_label.setMinimumWidth(86)

        text_layout = QtWidgets.QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(6)
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self._detail_label)
        text_layout.addStretch(1)

        layout.addWidget(self.checkbox)
        layout.addWidget(self.play_button)
        layout.addWidget(self.artwork_label)
        layout.addLayout(text_layout, stretch=1)
        layout.addWidget(self.status_label)

    def _set_artwork(self, artwork: bytes) -> None:
        if not artwork:
            return

        pixmap = QtGui.QPixmap()
        if not pixmap.loadFromData(artwork):
            return

        pixmap = pixmap.scaled(
            68,
            68,
            QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )

        self.artwork_label.setPixmap(pixmap)

    def set_status(self, text: str):
        self.status_label.setText(text)

    def set_detail(self, text: str) -> None:
        self._detail_label.setText(text)

    def set_playing(self, is_playing: bool):
        self.play_button.setText("Pause" if is_playing else "Play")

    def set_enabled_controls(self, enabled: bool):
        self.checkbox.setEnabled(enabled)
        self.play_button.setEnabled(enabled)

    def is_selected(self) -> bool:
        return self.checkbox.isChecked()
