import logging

from PySide6 import QtCore, QtMultimedia

log = logging.getLogger(__name__)


class PlayerService(QtCore.QObject):
    playing_index_changed = QtCore.Signal(int)
    playback_state_changed = QtCore.Signal(int)
    player_error = QtCore.Signal(str)
    position_changed = QtCore.Signal(int, int)
    volume_changed = QtCore.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.playing_index: int = -1
        self._starting = False
        self._audio_output = QtMultimedia.QAudioOutput(self)
        self._player = QtMultimedia.QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_output)
        self._audio_output.setVolume(0.8)

        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.errorOccurred.connect(
            lambda *_: self.player_error.emit(self._player.errorString())
        )
        self._player.durationChanged.connect(
            lambda d: self.position_changed.emit(self._player.position(), d)
        )
        self._player.positionChanged.connect(
            lambda p: self.position_changed.emit(p, self._player.duration())
        )

    def play(self, url: str, index: int) -> None:
        self.playing_index = index
        self.playing_index_changed.emit(index)
        self._starting = True
        self._player.setSource(QtCore.QUrl(url))
        self._player.play()
        self.playback_state_changed.emit(1)

    def toggle(self, url: str, index: int) -> None:
        if self.playing_index == index:
            if self._player.playbackState() == QtMultimedia.QMediaPlayer.PlaybackState.PlayingState:
                self._player.pause()
                self.playback_state_changed.emit(2)
            else:
                self._player.play()
                self.playback_state_changed.emit(1)
        else:
            self.play(url, index)

    def stop(self) -> None:
        self._player.stop()
        self._player.setSource(QtCore.QUrl())
        self.playing_index = -1
        self.playing_index_changed.emit(-1)
        self.playback_state_changed.emit(0)

    def set_volume(self, vol: int) -> None:
        vol = max(0, min(100, vol))
        self._audio_output.setVolume(vol / 100.0)
        self.volume_changed.emit(vol)

    def volume(self) -> int:
        return round(self._audio_output.volume() * 100)

    def seek_relative(self, delta_ms: int) -> None:
        pos = self._player.position() + delta_ms
        pos = max(0, min(pos, self._player.duration()))
        self._player.setPosition(pos)

    def seek(self, position: int) -> None:
        position = max(0, min(position, self._player.duration()))
        self._player.setPosition(position)

    def _on_state_changed(self, state: QtMultimedia.QMediaPlayer.PlaybackState) -> None:
        if self._starting:
            self._starting = False
            if state == QtMultimedia.QMediaPlayer.PlaybackState.StoppedState:
                return
        self.playback_state_changed.emit(int(state.value))
