import tracemalloc
import unittest

from twitcharchiver import Arguments


class TestArguments(unittest.TestCase):
    def setUp(self) -> None:
        tracemalloc.start()

    def test_extract_vods_and_channels(self):
        args = Arguments()
        args.set("from_file", False)
        vod_id = (
            "https://twitch.tv/videos/637408411,639404719,twitch.tv/videos/623893787"
        )
        args.set("vod_id", vod_id)
        args.extract_vods_and_channels("vod_id")
        self.assertEqual(["637408411", "639404719", "623893787"], args.get("vod_id"))


if __name__ == "__main__":
    unittest.main()
