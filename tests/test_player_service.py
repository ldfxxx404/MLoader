from unittest.mock import Mock

from mloader.player.service import PlayerService


class TestRun:
    def test_play(self, monkeypatch):
        mock_player = Mock()
        mock_multimedia = Mock()

        mock_multimedia.QMediaPlayer.return_value = mock_player
        mock_multimedia.QAudioOutput = Mock(return_value=Mock())

        monkeypatch.setattr("mloader.player.service.QtMultimedia", mock_multimedia)

        service = PlayerService()

        playing_index_changed = Mock()
        playback_state_changed = Mock()

        service.playing_index_changed.connect(playing_index_changed)
        service.playback_state_changed.connect(playback_state_changed)

        service.play("https://example.com/audio.mp3", 10)

        assert service.playing_index == 10

        playing_index_changed.assert_called_once_with(10)

        assert service._starting is True

        mock_player.setSource.assert_called_once()

        mock_player.play.assert_called_once()

        playback_state_changed.assert_called_once_with(1)
