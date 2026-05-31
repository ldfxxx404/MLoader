from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtWidgets, QtGui

from mloader.downloader.service import DownloaderService, DownloadSource
from mloader.gui.services.download_service import DownloadService
from mloader.gui.services.scan_service import ScanService
from mloader.gui.widgets.player_bar import PlayerBar
from mloader.gui.widgets.track_card import TrackCard
from mloader.player.service import PlayerService


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._downloader = DownloaderService()
        self._download_dir = self._downloader.download_dir
        self._sources: list[DownloadSource] = []
        self._track_cards: list[dict[str, Any]] = []
        self._player_service = PlayerService(self)
        self._scan_service = ScanService(self._downloader, self)
        self._download_service = DownloadService(self._downloader, self)

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

        self.player_bar = PlayerBar(self._player_service)

        main_layout.addLayout(heading_layout)
        main_layout.addLayout(input_layout)
        main_layout.addLayout(destination_layout)
        main_layout.addWidget(self.status_label)
        main_layout.addWidget(self.queue_list, stretch=1)
        main_layout.addWidget(self.player_bar)
        main_layout.addWidget(self.progress_bar)

        self._player_service.playing_index_changed.connect(self._on_playing_index_changed)
        self._player_service.playback_state_changed.connect(self._on_card_state_changed)
        self._player_service.player_error.connect(self._on_player_error)

        self._scan_service.scan_finished.connect(self._scan_finished)
        self._scan_service.scan_failed.connect(self._scan_failed)
        self._scan_service.status_changed.connect(self._set_status)

        self._download_service.track_started.connect(
            lambda index: self._set_selected_card_status(index, "Downloading")
        )
        self._download_service.track_progress_changed.connect(self._track_progress_changed)
        self._download_service.total_progress_changed.connect(self.progress_bar.setValue)
        self._download_service.status_changed.connect(self._set_status)
        self._download_service.track_finished.connect(self._track_finished)
        self._download_service.track_failed.connect(self._track_failed)
        self._download_service.downloads_finished.connect(self._downloads_finished)

        self.scan_button.clicked.connect(self._scan_link)
        self.download_button.clicked.connect(self._download_selected)
        self.browse_button.clicked.connect(self._choose_download_dir)
        self.link_input.returnPressed.connect(self._scan_link)

    def _scan_link(self) -> None:
        url = self.link_input.text().strip()
        if not url:
            self._set_status("Paste a link first.")
            self.link_input.setFocus()
            return

        if self._scan_service.is_busy or self._download_service.is_busy:
            self._set_status("Please wait for the current action to finish.")
            return

        self._player_service.stop()
        self._clear_tracks()
        self.progress_bar.setValue(0)
        self._set_status("Scanning...")
        self._set_busy(True, scanning=True)
        self._scan_service.scan(url)

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

        if self._download_service.is_busy or self._scan_service.is_busy:
            self._set_status("Please wait for the current action to finish.")
            return

        self._player_service.stop()
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
        self._download_service.download(selected_sources, self._download_dir)

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

        card.play_clicked.connect(
            lambda idx=index: self._player_service.toggle(self._sources[idx].file_url, idx)
        )

        self._track_cards.append({"item": item, "card": card})

    def _clear_tracks(self) -> None:
        self._player_service.stop()
        self.queue_list.clear()
        self._sources = []
        self._track_cards = []
        self._empty_item = QtWidgets.QListWidgetItem("Scan a link to show tracks here")
        self.queue_list.addItem(self._empty_item)
        self.download_button.setEnabled(False)

    def _selected_indexes(self) -> list[int]:
        return [i for i, entry in enumerate(self._track_cards) if entry["card"].is_selected()]

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

    def _set_status(self, status: str) -> None:
        self.status_label.setText(status)

    def _on_playing_index_changed(self, index: int | None) -> None:
        for entry in self._track_cards:
            entry["card"].set_playing(False)
            entry["card"].set_status("Ready")

        if index is not None and index < len(self._sources):
            self.player_bar.set_title(self._sources[index].title)
        else:
            self.player_bar.set_title("No preview playing")

    def _on_card_state_changed(self, state: int) -> None:
        if self._player_service.playing_index is None:
            for entry in self._track_cards:
                entry["card"].set_playing(False)
                entry["card"].set_status("Ready")
            return
        idx = self._player_service.playing_index
        if idx >= len(self._track_cards):
            return
        card = self._track_cards[idx]["card"]
        is_playing = state == 1
        card.set_playing(is_playing)
        status_map = {0: "Ready", 1: "Playing", 2: "Paused"}
        card.set_status(status_map.get(state, "Ready"))

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        self._scan_service.stop()
        self._download_service.stop()
        self._player_service.stop()
        super().closeEvent(event)

    def _on_player_error(self, _error: str) -> None:
        if self._player_service.playing_index is not None:
            idx = self._player_service.playing_index
            if idx < len(self._track_cards):
                card = self._track_cards[idx]["card"]
                card.set_status("Preview failed")
                card.set_playing(False)
        self.player_bar.set_title("Preview failed")
