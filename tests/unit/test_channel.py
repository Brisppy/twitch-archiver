import tracemalloc
import unittest

from twitcharchiver.channel import Channel
from twitcharchiver.exceptions import StreamOfflineError


class TestChannel(unittest.TestCase):
    def setUp(self) -> None:
        tracemalloc.start()
        # pewdiepie is used as the channel is 24/7 reruns
        self.channel_a = Channel("pewdiepie")

        if not self.channel_a.is_live():
            raise StreamOfflineError(self.channel_a)

        # reckful is used as VODs are unlikely to change
        self.channel_b = Channel("reckful")

    def test_is_live(self):
        self.assertTrue(self.channel_a.is_live())

    def test_get_stream_info(self):
        self.assertIsNotNone(self.channel_a.get_stream_info())

    def test_get_broadcast_vod_id(self):
        self.assertIsNotNone(self.channel_a.get_broadcast_v_id())

    def test_get_stream_index(self):
        self.assertIsNotNone(self.channel_a.get_stream_index())

    def test_get_stream_playlist(self):
        self.assertIsNotNone(self.channel_a.get_stream_playlist())

    def test_get_stream_playback_access_token(self):
        self.assertIsNotNone(self.channel_a.get_stream_playback_access_token())

    def test_get_latest_video(self):
        self.assertEqual(640057509, self.channel_b.get_latest_video().v_id)

    def test_get_channel_videos(self):
        self.assertEqual(745, len(self.channel_b.get_channel_archives()))


if __name__ == "__main__":
    unittest.main()
