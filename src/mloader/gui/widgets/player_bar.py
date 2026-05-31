from PySide6 import QtCore, QtWidgets

from mloader.player.service import PlayerService


class PlayerBar(QtWidgets.QWidget):
    def __init__(self, player_service: PlayerService, parent=None) -> None:
        super().__init__(parent)
        self._player_service = player_service
        self._is_seeking = False
        self._cached_duration = 0

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.title_label = QtWidgets.QLabel("No preview playing")
        self.title_label.setObjectName("playerTitle")

        self.time_label = QtWidgets.QLabel("0:00 / 0:00")
        self.time_label.setObjectName("playerTime")
        self.time_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.time_label.setMinimumWidth(92)

        self.seek_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setEnabled(False)

        layout.addWidget(self.title_label)
        layout.addWidget(self.seek_slider, stretch=1)
        layout.addWidget(self.time_label)

        self.seek_slider.sliderPressed.connect(self._seek_started)
        self.seek_slider.sliderReleased.connect(self._seek_finished)
        self.seek_slider.sliderMoved.connect(self._seek_moved)

        self._player_service.position_changed.connect(self._on_position_changed)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def _on_position_changed(self, position: int, duration: int) -> None:
        self._cached_duration = duration
        if not self._is_seeking:
            self.seek_slider.setValue(position)
        self.seek_slider.setRange(0, duration)
        self.seek_slider.setEnabled(duration > 0)
        self._update_time_label(position, duration)

    def _seek_started(self) -> None:
        self._is_seeking = True

    def _seek_finished(self) -> None:
        self._is_seeking = False
        self._player_service.seek(self.seek_slider.value())

    def _seek_moved(self, position: int) -> None:
        self._update_time_label(position, self._cached_duration)

    def _update_time_label(self, position: int, duration: int) -> None:
        self.time_label.setText(f"{self._format_time(position)} / {self._format_time(duration)}")

    @staticmethod
    def _format_time(value: int) -> str:
        total_seconds = max(value, 0) // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:02d}"
