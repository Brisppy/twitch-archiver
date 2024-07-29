import tracemalloc
import unittest

from twitcharchiver.channel import Channel
from twitcharchiver.vod import Vod


class TestVod(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        """
        Sets up class for tests.
        """
        tracemalloc.start()

        # reckful is used as VODs are unlikely to change
        # tests setup from a provided ID
        self.vod_a = Vod(vod_id=635457205)

        self.channel_a = Channel("pewdiepie")

    def test_time_since_live(self):
        if self.channel_a.is_live():
            live_vod = Vod.from_stream_json(self.channel_a.get_stream_info())
            self.assertIsNotNone(live_vod.time_since_live())
        else:
            self.fail("Test not performed as channel is offline.")

    def test_get_category(self):
        self.assertEqual(
            str({"id": "743", "name": "Chess"}), str(self.vod_a.get_category())
        )

    def test_get_chapters(self):
        expected = "[{'description': 'Chess', 'type': 'GAME_CHANGE', 'segment': {'position': 0.0, 'duration': 28534.0}}, {'description': 'Just Chatting', 'type': 'GAME_CHANGE', 'segment': {'position': 28534.0, 'duration': 1546.0}}, {'description': 'Chess', 'type': 'GAME_CHANGE', 'segment': {'position': 30080.0, 'duration': 2005.0}}]"
        self.assertEqual(expected, str(self.vod_a.chapters))

    def test_get_muted_segments(self):
        expected = "[{'id': 0, 'duration': 360, 'muted': True}, {'id': 15840, 'duration': 360, 'muted': True}, {'id': 16560, 'duration': 360, 'muted': True}, {'id': 26280, 'duration': 360, 'muted': True}]"
        self.assertEqual(expected, str(self.vod_a.get_muted_segments()))

    def test_get_vod_owner(self):
        self.assertDictEqual(
            {
                "id": 9072112,
                "name": "reckful",
                "display_name": "Reckful",
                "stream": None,
            },
            self.vod_a.channel.get_info(),
        )

    def test_get_stream_id(self):
        self.assertEqual(38359115104, int(self.vod_a.s_id))

    def test_get_index_url(self):
        self.assertIsNotNone(
            "https://d2nvs31859zcd8.cloudfront.net/919d6843e967a2a6efa1_reckful_38359115104_1466332961/chunked/index-muted-O46PQF03L2.m3u8",
            self.vod_a.get_index_url(),
        )

    def test_from_stream_json(self):
        self.assertIsNotNone(self.channel_a.get_stream_info())


if __name__ == "__main__":
    unittest.main()
