from mloader.downloader.service import DownloadSource, DownloaderService
from PySide6 import QtCore, QtGui, QtMultimedia, QtWidgets
from pathlib import Path
from typing import Any
from mloader.downloader.download_worker import DownloadWorker
from mloader.downloader.resolve_worker import ResolveWorker
from mloader.gui.widgets.track_card import TrackCard


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._thread: QtCore.QThread | None = None
        self._worker: QtCore.QObject | None = None
        self._downloader = DownloaderService()
        self._download_dir = self._downloader.download_dir
        self._sources: list[DownloadSource] = []
        self._track_cards: list[dict[str, Any]] = []
        self._playing_index: int | None = None
        self._is_seeking = False
        self._audio_output = QtMultimedia.QAudioOutput(self)
        self._player = QtMultimedia.QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_output)
        self._audio_output.setVolume(0.8)

        self.setWindowTitle("MLoader")
        self.resize(920, 620)
        self.setMinimumSize(720, 500)

        central_widget = QtWidgets.QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QtWidgets.QVBoxLayout(central_widget)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(18)

        title = QtWidgets.QLabel("MLoader")
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        title.setObjectName("title")

        subtitle = QtWidgets.QLabel("Scan a Bandcamp track or album, choose tracks, then download.")
        subtitle.setObjectName("subtitle")

        heading_layout = QtWidgets.QVBoxLayout()
        heading_layout.setSpacing(4)
        heading_layout.addWidget(title)
        heading_layout.addWidget(subtitle)

        self.link_input = QtWidgets.QLineEdit()
        self.link_input.setPlaceholderText("Paste a Bandcamp track or album link...")
        self.link_input.setMinimumHeight(38)
        self.link_input.setClearButtonEnabled(True)

        self.scan_button = QtWidgets.QPushButton("Scan")
        self.scan_button.setMinimumHeight(38)
        self.scan_button.setDefault(True)

        self.download_button = QtWidgets.QPushButton("Download selected")
        self.download_button.setMinimumHeight(38)
        self.download_button.setEnabled(False)

        input_layout = QtWidgets.QHBoxLayout()
        input_layout.setSpacing(10)
        input_layout.addWidget(self.link_input, stretch=1)
        input_layout.addWidget(self.scan_button)
        input_layout.addWidget(self.download_button)

        self.destination_label = QtWidgets.QLabel(str(self._download_dir))
        self.destination_label.setObjectName("destinationLabel")
        self.destination_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.browse_button = QtWidgets.QPushButton("Choose folder")
        self.browse_button.setMinimumHeight(34)

        destination_layout = QtWidgets.QHBoxLayout()
        destination_layout.setSpacing(10)
        destination_layout.addWidget(QtWidgets.QLabel("Save to:"))
        destination_layout.addWidget(self.destination_label, stretch=1)
        destination_layout.addWidget(self.browse_button)

        self.status_label = QtWidgets.QLabel("Ready")
        self.status_label.setObjectName("statusLabel")

        self.queue_list = QtWidgets.QListWidget()
        self.queue_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.queue_list.setSpacing(10)
        self._empty_item = QtWidgets.QListWidgetItem("Scan a link to show tracks here")
        self.queue_list.addItem(self._empty_item)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)

        self.player_title_label = QtWidgets.QLabel("No preview playing")
        self.player_title_label.setObjectName("playerTitle")

        self.player_time_label = QtWidgets.QLabel("0:00 / 0:00")
        self.player_time_label.setObjectName("playerTime")
        self.player_time_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.player_time_label.setMinimumWidth(92)

        self.seek_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setEnabled(False)

        player_layout = QtWidgets.QHBoxLayout()
        player_layout.setSpacing(12)
        player_layout.addWidget(self.player_title_label)
        player_layout.addWidget(self.seek_slider, stretch=1)
        player_layout.addWidget(self.player_time_label)

        main_layout.addLayout(heading_layout)
        main_layout.addLayout(input_layout)
        main_layout.addLayout(destination_layout)
        main_layout.addWidget(self.status_label)
        main_layout.addWidget(self.queue_list, stretch=1)
        main_layout.addLayout(player_layout)
        main_layout.addWidget(self.progress_bar)

        self.scan_button.clicked.connect(self._scan_link)
        self.download_button.clicked.connect(self._download_selected)
        self.browse_button.clicked.connect(self._choose_download_dir)
        self.link_input.returnPressed.connect(self._scan_link)
        self._player.playbackStateChanged.connect(self._playback_state_changed)
        self._player.errorOccurred.connect(self._playback_error)
        self._player.durationChanged.connect(self._duration_changed)
        self._player.positionChanged.connect(self._position_changed)
        self.seek_slider.sliderPressed.connect(self._seek_started)
        self.seek_slider.sliderReleased.connect(self._seek_finished)
        self.seek_slider.sliderMoved.connect(self._seek_moved)

    def _scan_link(self) -> None:
        url = self.link_input.text().strip()
        if not url:
            self._set_status("Paste a link first.")
            self.link_input.setFocus()
            return

        if self._thread is not None:
            self._set_status("Please wait for the current action to finish.")
            return

        self._stop_playback()
        self._clear_tracks()
        self.progress_bar.setValue(0)
        self._set_status("Scanning...")
        self._set_busy(True, scanning=True)

        thread = QtCore.QThread(self)
        worker = ResolveWorker(self._downloader, url)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.status_changed.connect(self._set_status)
        worker.resolved.connect(self._scan_finished)
        worker.failed.connect(self._scan_failed)
        worker.resolved.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_worker)

        self._thread = thread
        self._worker = worker
        thread.start()

    def _scan_finished(self, previews: list[tuple[DownloadSource, bytes]]) -> None:
        self._sources = [source for source, _artwork in previews]
        for source, artwork in previews:
            self._add_download_card(source, artwork)

        count = len(self._sources)
        self._set_status(f"Found {count} track{'s' if count != 1 else ''}.")
        self.download_button.setEnabled(count > 0)
        self._set_busy(False)

    def _scan_failed(self, message: str) -> None:
        self._set_status(f"Error: {message}")
        self._set_busy(False)
        self.download_button.setEnabled(False)

    def _download_selected(self) -> None:
        selected_indexes = self._selected_indexes()
        if not selected_indexes:
            self._set_status("Select at least one track.")
            return

        if self._thread is not None:
            self._set_status("Please wait for the current action to finish.")
            return

        self._stop_playback
        selected_sources = [self._sources[index] for index in selected_indexes]
        for card_index, entry in enumerate(self._track_cards):
            entry["card"].set_enabled_controls(False)

            if card_index in selected_indexes:
                entry["card"].set_status("Waiting")
            else:
                entry["card"].set_status("Skipped")

        self.progress_bar.setValue(0)
        self._set_status("Downloading selected tracks...")
        self._set_busy(True, scanning=False)

        thread = QtCore.QThread(self)
        worker = DownloadWorker(self._downloader, selected_sources, self._download_dir)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.status_changed.connect(self._set_status)
        worker.track_started.connect(
            lambda index: self._set_selected_card_status(index, "Downloading")
        )
        worker.track_progress_changed.connect(self._track_progress_changed)
        worker.total_progress_changed.connect(self.progress_bar.setValue)
        worker.track_finished.connect(self._track_finished)
        worker.track_failed.connect(self._track_failed)
        worker.finished.connect(self._downloads_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_worker)

        self._thread = thread
        self._worker = worker
        thread.start()

    def _choose_download_dir(self) -> None:
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Choose download folder",
            str(self._download_dir),
        )
        if not directory:
            return

        self._download_dir = Path(directory)
        self.destination_label.setText(str(self._download_dir))

    def _downloads_finished(self) -> None:
        self._set_status("Done")
        self.progress_bar.setValue(100)
        self._set_busy(False)
        for entry in self._track_cards:
            entry["card"].set_enabled_controls(True)
        self.download_button.setEnabled(bool(self._sources))

    def _track_progress_changed(self, selected_index: int, progress: int) -> None:
        card_index = self._selected_indexes()[selected_index]
        self._track_cards[card_index]["card"].set_status(f"{progress}%")

    def _track_finished(self, selected_index: int, file_path: str) -> None:
        card_index = self._selected_indexes()[selected_index]
        card = self._track_cards[card_index]["card"]
        card.set_status("Saved")
        card.detail_label.setText(file_path)

    def _track_failed(self, selected_index: int, message: str) -> None:
        card_index = self._selected_indexes()[selected_index]
        card = self._track_cards[card_index]["card"]
        card.set_status("Failed")
        card.detail_label.setText(message)

    def _set_selected_card_status(self, selected_index: int, status: str) -> None:
        card_index = self._selected_indexes()[selected_index]
        self._track_cards[card_index]["card"].set_status(status)

    def _add_download_card(self, source: DownloadSource, artwork: bytes) -> None:
        if self.queue_list.count() == 1 and self.queue_list.item(0) is self._empty_item:
            self.queue_list.takeItem(0)

        item = QtWidgets.QListWidgetItem()

        index = len(self._track_cards)
        card = TrackCard(source, artwork, index)

        item.setSizeHint(QtCore.QSize(0, 96))
        self.queue_list.addItem(item)
        self.queue_list.setItemWidget(item, card)
        self.queue_list.scrollToBottom()

        card.play_clicked.connect(lambda: self._toggle_playback(index))

        self._track_cards.append(
            {
                "item": item,
                "card": card,
            }
        )

    def _clear_tracks(self) -> None:
        self._stop_playback()
        self.queue_list.clear()
        self._sources = []
        self._track_cards = []
        self._empty_item = QtWidgets.QListWidgetItem("Scan a link to show tracks here")
        self.queue_list.addItem(self._empty_item)
        self.download_button.setEnabled(False)

    def _selected_indexes(self) -> list[int]:
        return [i for i, entry in enumerate(self._track_cards) if entry["card"].is_selected()]

    def _set_artwork(self, label: QtWidgets.QLabel, artwork: bytes) -> None:
        if not artwork:
            return

        pixmap = QtGui.QPixmap()
        if not pixmap.loadFromData(artwork):
            return

        scaled_pixmap = pixmap.scaled(
            68,
            68,
            QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        label.setPixmap(scaled_pixmap)

    def _toggle_playback(self, index: int) -> None:
        if index < 0 or index >= len(self._sources):
            return

        if self._playing_index == index:
            if self._player.playbackState() == QtMultimedia.QMediaPlayer.PlaybackState.PlayingState:
                self._player.pause()
            else:
                self._player.play()
            return

        self._reset_play_buttons

        self._playing_index = index
        card = self._track_cards[index]["card"]

        card.set_playing(True)
        card.set_status("Playing")

        self.player_title_label.setText(self._sources[index].title)
        self._player.setSource(QtCore.QUrl(self._sources[index].file_url))
        self._player.play()

    def _stop_playback(self) -> None:
        self._player.stop()
        self._player.setSource(QtCore.QUrl())
        self._playing_index = None
        self.player_title_label.setText("No preview playing")
        self.seek_slider.setEnabled(False)
        self.seek_slider.setRange(0, 0)
        self.player_time_label.setText("0:00 / 0:00")
        self._reset_play_buttons

    def _playback_state_changed(
        self,
        state: QtMultimedia.QMediaPlayer.PlaybackState,
    ) -> None:
        if self._playing_index is None or self._playing_index >= len(self._track_cards):
            return
        card = self._track_cards[self._playing_index]["card"]
        if state == QtMultimedia.QMediaPlayer.PlaybackState.PlayingState:
            card.set_playing(True)
            card.set_status("Playing")
        elif state == QtMultimedia.QMediaPlayer.PlaybackState.PausedState:
            card.set_playing(False)
            card.set_status("Paused")
        else:
            card.set_playing(False)
            card.set_status("Ready")

    def _playback_error(self, *_args: object) -> None:
        if self._playing_index is not None and self._playing_index < len(self._track_cards):
            card = self._track_cards[self._playing_index]["card"]
            card.set_status("Preview failed")
            card.set_playing(False)

            self._playing_index = None
            self.player_title_label.setText("Preview failed")
            self._reset_play_buttons()

    def _reset_play_buttons(self) -> None:
        for entry in self._track_cards:
            entry["card"].set_text(False)
            entry["card"].set_status("Ready")

    def _duration_changed(self, duration: int) -> None:
        self.seek_slider.setEnabled(duration > 0)
        self.seek_slider.setRange(0, duration)
        self._update_time_label(self._player.position(), duration)

    def _position_changed(self, position: int) -> None:
        if not self._is_seeking:
            self.seek_slider.setValue(position)
        self._update_time_label(position, self._player.duration())

    def _seek_started(self) -> None:
        self._is_seeking = True

    def _seek_finished(self) -> None:
        self._is_seeking = False
        self._player.setPosition(self.seek_slider.value())

    def _seek_moved(self, position: int) -> None:
        self._update_time_label(position, self._player.duration())

    def _update_time_label(self, position: int, duration: int) -> None:
        self.player_time_label.setText(
            f"{self._format_time(position)} / {self._format_time(duration)}"
        )

    def _format_time(self, value: int) -> str:
        total_seconds = max(value, 0) // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:02d}"

    def _set_busy(self, is_busy: bool, scanning: bool = False) -> None:
        self.link_input.setEnabled(not is_busy)
        self.scan_button.setEnabled(not is_busy)
        self.browse_button.setEnabled(not is_busy)
        if is_busy:
            self.download_button.setEnabled(False)
            self.scan_button.setText("Scanning..." if scanning else "Scan")
            self.download_button.setText("Downloading..." if not scanning else "Download selected")
        else:
            self.scan_button.setText("Scan")
            self.download_button.setText("Download selected")

    def _clear_worker(self) -> None:
        self._thread = None
        self._worker = None

    def _set_status(self, status: str) -> None:
        self.status_label.setText(status)
