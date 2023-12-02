"""
Module for testing Twitch video downloads.
"""


import os
import shutil
from pathlib import Path
from unittest import TestCase

from twitcharchiver.downloaders.video import Video
from twitcharchiver.utils import build_output_dir_name
from twitcharchiver.vod import Vod


class TestVideo(TestCase):
    """
    Class containing functions for integration testing of video download and other related functions.
    """
    def setUp(self) -> None:
        """
        Performs setup required for testing.
        """
        # reckful is used as VODs are unlikely to change
        self.video_a = Video(Vod(552662968))

    def test_download(self):
        """
        Tests downloading and verification methods.
        """
        # download VOD
        self.video_a.start()

        # verify VOD downloaded
        self.assertTrue(self.video_a.verify_length())

    def tearDown(self) -> None:
        """
        Deletes downloaded video files.
        """
        vod = self.video_a.vod
        vod_dir = Path(os.getcwd(), build_output_dir_name(vod.title, vod.created_at, vod.v_id))
        if vod_dir.exists():
            shutil.rmtree(vod_dir)
