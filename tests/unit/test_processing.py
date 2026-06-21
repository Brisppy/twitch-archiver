import unittest
from unittest.mock import patch

from twitcharchiver.channel import Channel
from twitcharchiver.processing import Processing
from twitcharchiver.vod import ArchivedVod


class TestProcessing(unittest.TestCase):
    def _minimal_conf(self, directory: str = "/tmp/test") -> dict:
        return {
            "quiet": True,
            "chat": True,
            "video": True,
            "archive_only": False,
            "highlights": False,
            "live_only": False,
            "real_time_archiver": False,
            "unsorted": True,
            "config_dir": "/tmp",
            "directory": directory,
            "discord_webhook": "",
            "pushbullet_key": "",
            "quality": "best",
            "threads": 1,
            "force_no_archive": False,
        }

    @staticmethod
    def _fake_channel(name: str) -> Channel:
        channel = Channel.__new__(Channel)
        channel.id = 123
        channel.name = name
        channel.display_name = name
        channel.stream = None
        channel._broadcast_v_id = 0
        channel._last_update = 0
        channel._api = None
        channel._log = None
        return channel

    def _fake_vod(self, v_id: int, channel_name: str) -> ArchivedVod:
        vod = ArchivedVod()
        vod.v_id = v_id
        vod._s_id = 0
        vod.title = "Test"
        vod.created_at = 0
        vod.duration = 100
        vod.type = "ARCHIVE"
        vod.video_archived = False
        vod.chat_archived = False
        vod.channel = self._fake_channel(channel_name)
        return vod

    @patch("twitcharchiver.processing.Database")
    def test_vod_downloader_uses_channel_specific_directories(self, mock_db):
        """
        Verify that when vod_downloader() receives VODs from multiple channels,
        each downloader is passed its own channel-specific output directory.
        """
        conf = self._minimal_conf(directory="/data/parent")
        process = Processing(conf)

        queue = [
            self._fake_vod(1, "channelA"),
            self._fake_vod(2, "channelB"),
            self._fake_vod(3, "channelA"),
        ]

        with patch("twitcharchiver.processing.Video") as mock_video, \
             patch("twitcharchiver.processing.Chat") as mock_chat, \
             patch.object(process, "_start_download"), \
             patch.object(ArchivedVod, "is_live", return_value=False), \
             patch.object(Channel, "is_live", return_value=False):
            process.vod_downloader(queue)

        video_calls = [call.args for call in mock_video.call_args_list]
        chat_calls = [call.args for call in mock_chat.call_args_list]

        # Video / Chat constructors receive (vod, parent_dir, ...)
        video_dirs = [str(args[1]) for args in video_calls]
        chat_dirs = [str(args[1]) for args in chat_calls]

        self.assertEqual(
            video_dirs,
            ["/data/parent/channelA", "/data/parent/channelB", "/data/parent/channelA"],
        )
        self.assertEqual(
            chat_dirs,
            ["/data/parent/channelA", "/data/parent/channelB", "/data/parent/channelA"],
        )


if __name__ == "__main__":
    unittest.main()
