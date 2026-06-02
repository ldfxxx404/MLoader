from PySide6 import QtCore, QtWidgets

from mloader.player.service import PlayerService


class PlayerBar(QtWidgets.QWidget):
    def __init__(self, player_service: PlayerService, parent=None) -> None:
        super().__init__(parent)
        self._player_service = player_service
        self._is_seeking = False
        self._cached_duration = 0
        self._cached_volume = self._player_service.volume()

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.title_label = QtWidgets.QLabel("No preview playing")
        self.title_label.setObjectName("playerTitle")

        self.seek_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setEnabled(False)

        self.time_label = QtWidgets.QLabel("0:00 / 0:00")
        self.time_label.setObjectName("playerTime")
        self.time_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.time_label.setMinimumWidth(92)

        self.volume_button = QtWidgets.QPushButton("♪")
        self.volume_button.setObjectName("volumeButton")
        self.volume_button.setFixedSize(30, 26)
        self.volume_button.setToolTip("Toggle mute")
        self.volume_button.setCheckable(True)

        self.volume_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self._player_service.volume())
        self.volume_slider.setFixedWidth(80)
        self.volume_slider.setToolTip("Volume")

        layout.addWidget(self.title_label)
        layout.addWidget(self.seek_slider, stretch=1)
        layout.addWidget(self.time_label)
        layout.addWidget(self.volume_button)
        layout.addWidget(self.volume_slider)

        self.seek_slider.sliderPressed.connect(self._seek_started)
        self.seek_slider.sliderReleased.connect(self._seek_finished)
        self.seek_slider.sliderMoved.connect(self._seek_moved)

        self.volume_slider.valueChanged.connect(self._player_service.set_volume)
        self.volume_button.toggled.connect(self._on_mute_toggled)

        self._player_service.position_changed.connect(self._on_position_changed)
        self._player_service.volume_changed.connect(self._on_volume_changed)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_volume(self, vol: int) -> None:
        self.volume_slider.setValue(vol)

    def _on_volume_changed(self, vol: int) -> None:
        self.volume_slider.setValue(vol)
        self.volume_button.blockSignals(True)
        self.volume_button.setChecked(vol == 0)
        self.volume_button.blockSignals(False)
        self.volume_button.setText("♪" if vol > 0 else "✕")

    def _on_mute_toggled(self, muted: bool) -> None:
        if muted:
            self._cached_volume = self.volume_slider.value()
            self._player_service.set_volume(0)
        else:
            self._player_service.set_volume(self._cached_volume)

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
