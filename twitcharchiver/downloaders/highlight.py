import os
import re
from pathlib import Path

from twitcharchiver.exceptions import VideoMergeError
from twitcharchiver.vod import ArchivedVod
from twitcharchiver.downloaders.video import Merger
import m3u8

from twitcharchiver.vod import Vod
from twitcharchiver.downloaders.video import Video


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

    def merge(self):
        """
        Attempt to merge downloaded VOD parts and verify them.
        """
        merger = Merger(
            self.vod,
            self.output_dir,
            self._completed_segments,
            self._muted_segments,
            self._quiet,
            ignore_discontinuity=True,
            ignore_corrupt_parts=True,
        )

        # attempt to merge
        try:
            merger.merge()

        except Exception as exc:
            raise VideoMergeError("Exception raised while merging Highlight.") from exc

        # verify VOD based on its length
        if merger.verify_length():
            merger.cleanup_temp_files()

        else:
            raise VideoMergeError(
                "VOD verification failed as Highlight length is outside the acceptable range."
            )

        # set archival flag if ArchivedVod provided
        if isinstance(self.vod, ArchivedVod):
            self.vod.video_archived = True

        self._log.info("Finished archiving Highlight video.")

    def refresh_playlist(self):
        """
        Fetch new segments for video (if any).
        """
        self._prev_index_playlist = self._index_playlist
        _raw_playlist = self.vod.get_index_playlist(self._index_url)
        self._index_playlist = m3u8.loads(_raw_playlist)

        # some highlights have issues with the final segment not containing all the vod information which can be
        # recovered by grabbing the segment by its id rather than the URL twitch provides (e.g 2269206784).
        # See https://github.com/Brisppy/twitch-archiver/issues/44
        if str(self.vod.v_id) in self._index_playlist.segments[-1].uri:
            # we need to check the part is available as some highlights end with a segment named like this but do not
            # have one without the VOD ID available (367046564).
            new_segment_id = self._index_playlist.segments[-1].uri.split("-")[1]
            _r = self._s.get(self._base_url + new_segment_id)

            if _r.status_code == 200:
                self._index_playlist.segments[-1].uri = new_segment_id

        # we can't rely on the duration contained within the index playlist for all Highlights as VOD 4807348
        # is only 27 seconds long, but has a playlist duration of 35233.3
