import os
import shutil
from pathlib import Path
from unittest import TestCase

from twitcharchiver import Vod
from twitcharchiver.downloaders.chat import Chat
from twitcharchiver.utils import build_output_dir_name


class TestChat(TestCase):
    """
    Class containing functions for integration testing of chat log downloading other related functions.
    """

    def setUp(self) -> None:
        """
        Performs setup required for testing.
        """
        # reckful is used as VODs are unlikely to change
        self.chat_a = Chat(Vod(553141160))

    def test_download(self):
        """
        Tests downloading of chat log.
        """
        # download chat log
        self.chat_a.start()

        # compare against known message count (may change due to user bans / account deletions)
        self.assertAlmostEqual(981, self.chat_a.get_message_count(), delta=10)

    def test_exporting_and_loading(self):
        """
        Tests the exporting of chat messages along with importing downloaded chat logs.
        """
        # download and export chat messages
        self.chat_a.start()
        self.chat_a.export_chat_logs()

        # import previously exported messages
        chat_b = Chat(Vod(553141160))
        chat_b.load_from_file()

        # check messages were grabbed and message count matches
        if self.chat_a.get_message_count() != 0:
            self.assertEqual(
                self.chat_a.get_message_count(), chat_b.get_message_count()
            )
        else:
            self.fail("Failed to retrieve messages from Twitch.")

    def tearDown(self) -> None:
        """
        Deletes downloaded chat logs if they were exported to disk.
        """
        vod = self.chat_a.vod
        vod_dir = Path(
            os.getcwd(), build_output_dir_name(vod.title, vod.created_at, vod.v_id)
        )
        if vod_dir.exists():
            shutil.rmtree(vod_dir)
