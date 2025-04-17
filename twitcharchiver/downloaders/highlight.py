import os
import re
from pathlib import Path

from twitcharchiver.vod import Vod, ArchivedVod
from twitcharchiver.downloaders.video import Video, Merger


class Highlight(Video):
    def __init__(
        self,
        vod: Vod,
        parent_dir: Path = os.getcwd(),
        quality: str = "best",
        threads: int = 20,
        quiet: bool = False,
    ):
        super().__init__(vod, parent_dir, quality, threads, quiet)

    @staticmethod
    def _extract_base_url(index_url: str):
        """
        Extracts a URL from which TS segment IDs are appended to generate the URL which segments are stored.

        :param index_url: index url used to create base url
        :return: base url for TS segments
        """
        if "highlight" in index_url:
            _m = re.findall(r"(?<=\/)(highlight.*)", index_url)[0]
        else:
            _m = re.findall(r"(?<=\/)(index.*)", index_url)[0]
        return index_url.replace(_m, "")
