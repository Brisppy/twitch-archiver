import tracemalloc
import unittest

from twitcharchiver import Arguments


class TestArguments(unittest.TestCase):
    def setUp(self) -> None:
        tracemalloc.start()

    def test_extract_vods_and_channels(self):
        args = Arguments()
        args.set('from_file', True)
        vods = 'https://twitch.tv/videos/637408411,639404719,twitch.tv/videos/623893787'
        args.set('vods', vods)
        args.extract_vods_and_channels('vods')
        self.assertEqual([637408411, 639404719, 623893787], args.get('vods'))


if __name__ == '__main__':
    unittest.main()
