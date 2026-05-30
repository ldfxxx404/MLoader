from pathlib import Path
from typing import Any

import requests
from PySide6 import QtCore, QtGui, QtMultimedia, QtWidgets

from mloader.downloader.service import DownloadError, DownloadSource, DownloaderService


class ResolveWorker(QtCore.QObject):
    resolved = QtCore.Signal(object)
    status_changed = QtCore.Signal(str)
    failed = QtCore.Signal(str)

    def __init__(self, service: DownloaderService, url: str) -> None:
        super().__init__()
        self._service = service
        self._url = url

    @QtCore.Slot()
    def run(self) -> None:
        try:
            sources = self._service.resolve(self._url, self.status_changed.emit)
            previews = [(source, self._load_artwork(source.artwork_url)) for source in sources]
        except DownloadError as error:
            self.failed.emit(str(error))
            return
        except Exception as error:
            self.failed.emit(f"Unexpected error: {error}")
            return

        self.resolved.emit(previews)

    def _load_artwork(self, artwork_url: str | None) -> bytes:
        if not artwork_url:
            return b""

        try:
            response = requests.get(artwork_url, timeout=20)
            response.raise_for_status()
        except requests.RequestException:
            return b""

        return response.content


class DownloadWorker(QtCore.QObject):
    track_started = QtCore.Signal(int)
    track_progress_changed = QtCore.Signal(int, int)
    total_progress_changed = QtCore.Signal(int)
    status_changed = QtCore.Signal(str)
    track_finished = QtCore.Signal(int, str)
    track_failed = QtCore.Signal(int, str)
    finished = QtCore.Signal()

    def __init__(
        self,
        service: DownloaderService,
        sources: list[DownloadSource],
        download_dir: Path,
    ) -> None:
        super().__init__()
        self._service = service
        self._sources = sources
        self._download_dir = download_dir

    @QtCore.Slot()
    def run(self) -> None:
        total = len(self._sources)
        target_dir = self._service.download_dir_for_sources(self._download_dir, self._sources)
        for index, source in enumerate(self._sources):
            self.track_started.emit(index)

            try:
                result = self._service.download_source(
                    source,
                    progress_callback=lambda progress, i=index: self._emit_track_progress(
                        i,
                        progress,
                        total,
                    ),
                    status_callback=self.status_changed.emit,
                    target_dir=target_dir,
                )
            except DownloadError as error:
                self.track_failed.emit(index, str(error))
                continue
            except Exception as error:
                self.track_failed.emit(index, f"Unexpected error: {error}")
                continue

            self.track_finished.emit(index, str(result.file_path))

        self.total_progress_changed.emit(100)
        self.finished.emit()

    def _emit_track_progress(self, index: int, progress: int, total: int) -> None:
        self.track_progress_changed.emit(index, progress)
        self.total_progress_changed.emit(min(int((index + progress / 100) / total * 100), 100))


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
        self.destination_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)

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

        self.setStyleSheet(
            """
            QMainWindow {
                background: #000000;
            }

            QLabel {
                color: #98a296;
            }

            QLabel#title {
                color: #66E413;
                font-size: 28px;
                font-weight: 700;
            }

            QLabel#subtitle,
            QLabel#statusLabel,
            QLabel#destinationLabel {
                color: #98a296;
                font-size: 13px;
            }

            QLineEdit {
                background: #101510;
                border: 1px solid #263226;
                border-radius: 6px;
                color: #eff7ec;
                font-size: 14px;
                padding: 8px 10px;
                selection-background-color: #66E413;
                selection-color: #000000;
            }

            QLineEdit:focus {
                border-color: #66E413;
            }

            QLineEdit:disabled {
                background: #0b100b;
                border-color: #1c271c;
                color: #687468;
            }

            QPushButton {
                background: #66E413;
                border: 1px solid #66E413;
                border-radius: 6px;
                color: #000000;
                font-size: 14px;
                font-weight: 600;
                padding: 8px 18px;
            }

            QPushButton:hover {
                background: #7cff24;
                border-color: #7cff24;
            }

            QPushButton:pressed {
                background: #55c90d;
                border-color: #55c90d;
            }

            QPushButton:disabled {
                background: #263226;
                border-color: #263226;
                color: #7f8c7f;
            }

            QCheckBox {
                color: #eff7ec;
                spacing: 8px;
            }

            QCheckBox::indicator {
                background: #101510;
                border: 1px solid #334133;
                border-radius: 4px;
                height: 18px;
                width: 18px;
            }

            QCheckBox::indicator:checked {
                background: #66E413;
                border-color: #66E413;
            }

            QPushButton#playButton {
                background: #101510;
                border: 1px solid #334133;
                border-radius: 6px;
                color: #66E413;
                font-size: 12px;
                font-weight: 700;
                padding: 0 10px;
            }

            QPushButton#playButton:hover {
                background: #162016;
                border-color: #66E413;
            }

            QPushButton#playButton:disabled {
                background: #101510;
                border-color: #1c271c;
                color: #4f5a4f;
            }

            QListWidget {
                background: #080c08;
                border: 1px solid #263226;
                border-radius: 8px;
                color: #eff7ec;
                font-size: 14px;
                padding: 8px;
            }

            QListWidget::item {
                background: transparent;
                border-radius: 4px;
            }

            QWidget#downloadCard {
                background: #0f160f;
                border: 1px solid #223022;
                border-radius: 8px;
            }

            QLabel#artworkLabel {
                background: #162016;
                border: 1px solid #2d3a2d;
                border-radius: 6px;
                color: #66E413;
                font-size: 22px;
                font-weight: 700;
            }

            QLabel#trackTitle {
                color: #eff7ec;
                font-size: 15px;
                font-weight: 700;
            }

            QLabel#trackUrl {
                color: #8d9a8d;
                font-size: 12px;
            }

            QLabel#trackStatus {
                color: #66E413;
                font-size: 12px;
                font-weight: 700;
            }

            QLabel#playerTitle,
            QLabel#playerTime {
                color: #98a296;
                font-size: 12px;
            }

            QSlider::groove:horizontal {
                background: #172017;
                border-radius: 3px;
                height: 6px;
            }

            QSlider::sub-page:horizontal {
                background: #66E413;
                border-radius: 3px;
            }

            QSlider::handle:horizontal {
                background: #66E413;
                border: 1px solid #66E413;
                border-radius: 6px;
                height: 12px;
                margin: -4px 0;
                width: 12px;
            }

            QSlider::handle:horizontal:hover {
                background: #7cff24;
                border-color: #7cff24;
            }

            QSlider::groove:horizontal:disabled {
                background: #101510;
            }

            QSlider::handle:horizontal:disabled {
                background: #263226;
                border-color: #263226;
            }

            QProgressBar {
                background: #172017;
                border: none;
                border-radius: 4px;
                height: 8px;
            }

            QProgressBar::chunk {
                background: #66E413;
                border-radius: 4px;
            }
            """
        )

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

        self._stop_playback()
        selected_sources = [self._sources[index] for index in selected_indexes]
        for card_index, card in enumerate(self._track_cards):
            card["checkbox"].setEnabled(False)
            card["play"].setEnabled(False)
            card["status"].setText("Waiting" if card_index in selected_indexes else "Skipped")

        self.progress_bar.setValue(0)
        self._set_status("Downloading selected tracks...")
        self._set_busy(True, scanning=False)

        thread = QtCore.QThread(self)
        worker = DownloadWorker(self._downloader, selected_sources, self._download_dir)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.status_changed.connect(self._set_status)
        worker.track_started.connect(lambda index: self._set_selected_card_status(index, "Downloading"))
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
        for card in self._track_cards:
            card["checkbox"].setEnabled(True)
            card["play"].setEnabled(True)
        self.download_button.setEnabled(bool(self._sources))

    def _track_progress_changed(self, selected_index: int, progress: int) -> None:
        card_index = self._selected_indexes()[selected_index]
        self._track_cards[card_index]["status"].setText(f"{progress}%")

    def _track_finished(self, selected_index: int, file_path: str) -> None:
        card_index = self._selected_indexes()[selected_index]
        self._track_cards[card_index]["status"].setText("Saved")
        self._track_cards[card_index]["detail"].setText(file_path)

    def _track_failed(self, selected_index: int, message: str) -> None:
        card_index = self._selected_indexes()[selected_index]
        self._track_cards[card_index]["status"].setText("Failed")
        self._track_cards[card_index]["detail"].setText(message)

    def _set_selected_card_status(self, selected_index: int, status: str) -> None:
        card_index = self._selected_indexes()[selected_index]
        self._track_cards[card_index]["status"].setText(status)

    def _add_download_card(self, source: DownloadSource, artwork: bytes) -> None:
        if self.queue_list.count() == 1 and self.queue_list.item(0) is self._empty_item:
            self.queue_list.takeItem(0)

        item = QtWidgets.QListWidgetItem()
        card = QtWidgets.QWidget()
        card.setObjectName("downloadCard")

        card_layout = QtWidgets.QHBoxLayout(card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(12)

        checkbox = QtWidgets.QCheckBox()
        checkbox.setChecked(True)

        play_button = QtWidgets.QPushButton("Play")
        play_button.setObjectName("playButton")
        play_button.setFixedSize(58, 34)
        play_button.setToolTip("Preview track")

        artwork_label = QtWidgets.QLabel("♪")
        artwork_label.setObjectName("artworkLabel")
        artwork_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        artwork_label.setFixedSize(68, 68)
        self._set_artwork(artwork_label, artwork)

        title = source.title
        if source.track_number is not None:
            title = f"{source.track_number:02d}. {title}"

        title_label = QtWidgets.QLabel(title)
        title_label.setObjectName("trackTitle")
        title_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)

        detail_label = QtWidgets.QLabel(source.page_url)
        detail_label.setObjectName("trackUrl")
        detail_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        detail_label.setWordWrap(True)

        status_label = QtWidgets.QLabel("Ready")
        status_label.setObjectName("trackStatus")
        status_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        status_label.setMinimumWidth(86)

        text_layout = QtWidgets.QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(6)
        text_layout.addWidget(title_label)
        text_layout.addWidget(detail_label)
        text_layout.addStretch(1)

        card_layout.addWidget(checkbox)
        card_layout.addWidget(play_button)
        card_layout.addWidget(artwork_label)
        card_layout.addLayout(text_layout, stretch=1)
        card_layout.addWidget(status_label)

        item.setSizeHint(QtCore.QSize(0, 96))
        self.queue_list.addItem(item)
        self.queue_list.setItemWidget(item, card)
        self.queue_list.scrollToBottom()

        card_index = len(self._track_cards)
        play_button.clicked.connect(lambda _checked=False, index=card_index: self._toggle_playback(index))

        self._track_cards.append(
            {
                "item": item,
                "checkbox": checkbox,
                "play": play_button,
                "status": status_label,
                "detail": detail_label,
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
        return [
            index
            for index, card in enumerate(self._track_cards)
            if card["checkbox"].isChecked()
        ]

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

        self._reset_play_buttons()
        self._playing_index = index
        self._track_cards[index]["play"].setText("Pause")
        self._track_cards[index]["status"].setText("Playing")
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
        self._reset_play_buttons()

    def _playback_state_changed(
        self,
        state: QtMultimedia.QMediaPlayer.PlaybackState,
    ) -> None:
        if self._playing_index is None or self._playing_index >= len(self._track_cards):
            return

        button = self._track_cards[self._playing_index]["play"]
        status_label = self._track_cards[self._playing_index]["status"]
        if state == QtMultimedia.QMediaPlayer.PlaybackState.PlayingState:
            button.setText("Pause")
            status_label.setText("Playing")
        elif state == QtMultimedia.QMediaPlayer.PlaybackState.PausedState:
            button.setText("Play")
            status_label.setText("Paused")
        else:
            button.setText("Play")
            if status_label.text() in {"Playing", "Paused"}:
                status_label.setText("Ready")

    def _playback_error(self, *_args: object) -> None:
        if self._playing_index is not None and self._playing_index < len(self._track_cards):
            self._track_cards[self._playing_index]["status"].setText("Preview failed")
        self._playing_index = None
        self.player_title_label.setText("Preview failed")
        self._reset_play_buttons()

    def _reset_play_buttons(self) -> None:
        for card in self._track_cards:
            card["play"].setText("Play")

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
