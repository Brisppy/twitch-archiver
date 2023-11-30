"""
Module for downloading currently live Twitch broadcasts.
"""
import os
import shutil
import tempfile

from datetime import datetime, timezone
from math import floor
from operator import attrgetter
from pathlib import Path
from time import sleep

import m3u8
import requests

from twitcharchiver.vod import Vod, ArchivedVod
from twitcharchiver.channel import Channel
from twitcharchiver.downloader import Downloader
from twitcharchiver.downloaders.video import MpegSegment, Merger, Video
from twitcharchiver.exceptions import TwitchAPIErrorNotFound, UnsupportedStreamPartDuration, StreamDownloadError, \
    StreamSegmentDownloadError, StreamFetchError, StreamOfflineError, VodMergeError, RequestError
from twitcharchiver.utils import time_since_date, safe_move, build_output_dir_name


TEMP_BUFFER_LEN = 120
CHECK_INTERVAL = 4


class StreamSegmentList:
    """
    Parses and stores segments of a Twitch livestream and the parts they are derived from.
    """
    def __init__(self, stream_created_at: float, align_segments: bool = True, start_id: int = 0):
        self.segments: dict[int: StreamSegment] = {}
        self.current_id = start_id + 1
        self._align_segments = align_segments
        self.stream_created_at = stream_created_at

    def add_part(self, part):
        """
        Adds a given part to the appropriate StreamSegment.

        :param part: part to add
        :type part: StreamSegment.Part
        """
        # generate part id from timestamp if we are aligning segments
        if self._align_segments:
            _parent_segment_id = self._get_id_for_part(part)

        # otherwise use our current id
        else:
            _parent_segment_id = self.current_id

        # create parent segment if one doesn't yet exist
        if _parent_segment_id not in self.segments.keys():
            self.current_id = _parent_segment_id
            self.segments[_parent_segment_id] = StreamSegment(_parent_segment_id)

        # create new segment and increment ID if current segment complete
        if len(self.get_segment_by_id(_parent_segment_id).parts) == 5:
            _parent_segment_id += 1
            self.current_id = _parent_segment_id
            self.segments[_parent_segment_id] = StreamSegment(_parent_segment_id)

        # append part to parent segment
        self.segments[_parent_segment_id].add_part(part)

    def _get_id_for_part(self, part):
        """
        Retrieves the ID for a given part based on it's and the stream's timestamps.

        :param part: Part to retrieve ID for.
        :type part: StreamSegment.Part
        :return: ID of part
        :rtype: int
        """
        # maths for determining the id of a given part based on its timestamp and the stream creation time
        return floor((4 + (part.timestamp - self.stream_created_at)) / 10)

    def is_segment_present(self, segment_id: int):
        """
        Checks if a stream segment ID exists in the StreamSegmentList.

        :param segment_id: ID of segment to look for
        :return: True if segment ID present
        """
        return segment_id in self.segments.keys()

    def get_segment_by_id(self, segment_id: int):
        """
        Fetches the segment with the provided ID.

        :param segment_id: segment id to fetch
        :return: Segment which matches provided ID
        :rtype: StreamSegment
        """
        return self.segments[segment_id]

    def get_completed_segment_ids(self):
        """
        Gathers and returns the ids of all segments with 5 parts.

        :return: set[int]
        """
        _segment_ids: set[int] = set()
        for _segment in self.segments:
            if len(self.segments[_segment].parts) == 5:
                _segment_ids.add(self.segments[_segment].id)

        return _segment_ids

    def pop_segment(self, seg_id):
        """
        Pops the provided segment ID off of the list of segments.

        :param seg_id: id of segment to remove and return
        :return: segment which matches the id
        :rtype: StreamSegment
        """
        return self.segments.pop(seg_id)


class StreamSegment:
    """
    Defines a video segment made up of 5 'Parts', these parts are retrieved from the Twitch API during a livestream.
    In *most* circumstances, each part is 2 seconds long, and can be combined into a 10s 'Segment'. These segments can
    then be matched directly with Segments which make up a Twitch VOD.
    """
    def __init__(self, segment_id: int):
        """
        Defines a video segment made up of 5 StreamSegment parts.

        :param segment_id: ID of segment
        """
        self.parts: list[StreamSegment.Part] = []
        self.id: int = segment_id
        self.duration: float = 0

    class Part:
        """
        A Part advertised by Twitch and later combined into a segment.
        """
        def __init__(self, part):
            """
            Defines a part of a segment.
            """
            self.url: str = part.uri
            self.timestamp: float = part.program_date_time.replace(tzinfo=timezone.utc).timestamp()
            self.duration: float = part.duration
            self.title = part.title

        def __repr__(self):
            return str({'url': self.url, 'timestamp': self.timestamp, 'duration': self.duration})

        def __eq__(self, other):
            if isinstance(other, StreamSegment.Part):
                return self.url == other.url
            raise TypeError

        def __hash__(self):
            return hash(self.url)

    def add_part(self, part: Part):
        """
        Adds a part to the segment and updates the duration.

        :param part: part to add to segment
        """
        self.parts.append(part)
        self.duration += part.duration

    def is_full(self):
        """
        Checks if the segment had five parts.

        :return: True if segment is complete (contains 5 parts)
        :rtype: bool
        """
        if len(self.parts) == 5:
            return True

        return False

    def __repr__(self):
        return str({'id': self.id, 'duration': self.duration, 'parts': self.parts})

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.parts == other.parts
        raise TypeError

    def __hash__(self):
        return hash(str(self.parts))


class Stream(Downloader):
    """
    Class which handles the downloading of video files for a given Twitch stream.
    """
    _quality: str = ''
    def __init__(self, channel: Channel, vod: Vod = Vod(), parent_dir: Path = Path(os.getcwd()), quality: str = 'best',
                 quiet: bool = 'False'):
        """
        Class constructor.

        :param channel: Channel to be downloaded
        :type channel: Channel
        :param vod: Optionally provided VOD if trying to sync VOD and stream segments and timestamps
        :type vod: Vod
        :param parent_dir: Parent directory in which to create VOD directory and download to
        :type parent_dir: str
        :param quality: Quality of the stream to download in the format [resolution]p[framerate]
        :type quality: str
        :param quiet: True suppresses progress reporting
        :type quiet: bool
        """
        super().__init__(parent_dir, quiet)

        self.__setattr__('_quality', quality)

        # create segments for combining with archived VOD parts. If true we will try to recreate the segment numbering
        # scheme Twitch uses, otherwise we use our own numbering scheme. Only used when archiving a live stream without
        # a VOD.
        self._align_segments: bool = True

        # buffers and progress tracking
        self._index_uri: str = ""
        self._incoming_part_buffer: list[StreamSegment.Part] = []
        self._download_queue: StreamSegmentList = None
        self._completed_segments: set[StreamSegment] = set()
        self._processed_parts: set[StreamSegment.Part] = set()
        self._last_part_announce: float = datetime.now(timezone.utc).timestamp()

        # channel-specific vars
        self.channel: Channel = channel
        self.output_dir: Path = None
        self.vod: Vod = vod

        # perform setup
        self._do_setup()

    def __repr__(self):
        return str({'channel': self.channel, 'index_uri': self._index_uri, 'stream': self.vod})

    def start(self):
        """
        Begins downloading the stream for the channel until stopped or stream ends.
        """
        # create output  dir if not already created
        Path(self.output_dir, 'parts').mkdir(parents=True, exist_ok=True)

        # loop until stream ends
        while True:
            _start_timestamp: float = datetime.now(timezone.utc).timestamp()
            self.single_download_pass()

            # assume stream has ended once >20s has passed since the last segment was advertised
            #   if parts remain in the buffer, we need to download them whether there are 5 parts or not
            if time_since_date(self._last_part_announce) > 20:
                # perform secondary check to see if stream is actually offline
                _stream_info = self.channel.get_stream_info()
                # check channel stream id matches ours
                if _stream_info['stream'] and int(_stream_info['stream']['id']) == self.vod.s_id:
                    pass

                else:
                    self._log.debug('Assuming stream has ended as 20 seconds passed since last segment announced.')
                    self._get_final_segment()
                    break

            # sleep if processing time < CHECK_INTERVAL time before checking for new segments
            _loop_time = int(datetime.now(timezone.utc).timestamp() - _start_timestamp)
            if _loop_time < CHECK_INTERVAL:
                sleep(CHECK_INTERVAL - _loop_time)

    def merge(self):
        """
        Attempt to merge downloaded segments.
        """
        # we pass all possible segments as muted segments so that corrupt parts are ignored.
        merger = Merger(self.vod, self.output_dir, self._completed_segments, [MpegSegment(i, 10) for i in range(10000)], self._quiet)

        # attempt to merge - no verification done as unsynced streams have no accurate duration to verify against
        try:
            merger.merge()
            merger.cleanup_temp_files()

        except Exception as exc:
            raise VodMergeError('Exception raised while merging VOD.') from exc

    def single_download_pass(self):
        """
        Used to fetch and download stream segments without looping. This is used for creating a stream buffer at the
        start of archiving in case a VOD never becomes available, in which case the previously broadcast segments
        would be lost.
        """
        try:
            self._fetch_advertised_parts()

            if self._incoming_part_buffer:
                self._build_download_queue()
                self._download_queued_segments()

        # stream offline
        except TwitchAPIErrorNotFound:
            self._log.info('%s is offline or stream ended.', self.channel.name)
            if self._download_queue:
                self._get_final_segment()

        # catch any other exception
        except Exception as exc:
            raise StreamDownloadError(self.channel.name, exc) from exc

    def _do_setup(self):
        """
        Performs required setup prior to starting download.
        """
        # generate VOD from channel stream information if not provided -
        # channel stream information can differ from video / VOD information making parallel archiving with the video
        # downloader impossible, so we need the option to provide our own VOD to sync with.
        if not self.vod:
            self._log.debug('Fetching required stream information.')
            stream_vod = ArchivedVod.convert_from_vod(Vod.from_stream_json(self.channel.get_stream_info()), video_archived=True)
            stream_vod.channel = self.channel
            if not stream_vod:
                self._log.info('%s is offline.', self.channel.name)
                raise StreamOfflineError(self.channel)
            self.vod = stream_vod

        # ensure enough time has passed for VOD api to update before archiving. this is important as it changes
        # the way we archive if the stream is not being archived to a VOD.
        self._log.debug('Current stream length: %s', self.vod.duration)

        # while we wait for the api to update we must build a temporary buffer of any parts advertised in the
        # meantime in case there is no vod and thus no way to retrieve them after the fact
        if not self.vod.v_id:
            if self.vod.duration < TEMP_BUFFER_LEN:
                self._buffer_stream(self.vod.duration)

            # fetch VOD ID for output directory, disable segment alignment if there is no paired VOD ID
            # todo: if a previous broadcast has a vod id, but the current one doesn't, what does the api return?
            broadcast_vod_id = self.channel.broadcast_v_id
            if not broadcast_vod_id:
                self._align_segments = False
            else:
                self.vod = Vod(broadcast_vod_id)
                # if a paired VOD exists for the stream we can discard our temporary buffer
                if self.output_dir and Path(self.output_dir).exists():
                    shutil.rmtree(Path(self.output_dir))

        # build and create actual output directory
        self.output_dir = (
            Path(self._parent_dir, build_output_dir_name(self.vod.title, self.vod.created_at, self.vod.v_id)))

        if self.output_dir.exists():
            # get existing parts to resume counting if archiving halted
            self._completed_segments = {MpegSegment(int(Path(p).name.removesuffix('.ts')), 10)
                                        for p in list(Path(self.output_dir, 'parts').glob('*.ts'))}

        # start at '-1', the first part will then be '0'
        _latest_segment = MpegSegment(-1, 0)
        if self._completed_segments:
            # set start segment for download queue
            _latest_segment = max(self._completed_segments, key=attrgetter('id'))

        # pass stream created to segment list to be used for determining part and segment ids
        self._download_queue = StreamSegmentList(self.vod.created_at, self._align_segments, _latest_segment.id)

        # fetch index
        try:
            self._index_uri = self.channel.get_stream_index(self._quality)
        except TwitchAPIErrorNotFound as exc:
            raise StreamOfflineError(self.channel) from exc

    def _buffer_stream(self, stream_length: int):
        """
        Builds a temporary buffer when a stream has just started to ensure the Twitch API has updated when we
        attempt to fetch VOD information.

        :param stream_length: time in seconds stream has been live
        """
        self._log.debug('Stream began less than 120s ago, delaying archival start until VOD API updated.')

        # create temporary download directory
        self.output_dir = Path(self._parent_dir, build_output_dir_name(self.vod.title, self.vod.created_at))
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

        # download new parts every CHECK_INTERVAL time
        for _ in range(int((TEMP_BUFFER_LEN - stream_length) / CHECK_INTERVAL)):
            _start_timestamp: float = datetime.now(timezone.utc).timestamp()
            self.single_download_pass()

            # wait if less than CHECK_INTERVAL time passed since grabbing more parts
            _loop_time = int(datetime.now(timezone.utc).timestamp() - _start_timestamp)
            if _loop_time < CHECK_INTERVAL:
                sleep(CHECK_INTERVAL - _loop_time)

        # wait any remaining time
        sleep((TEMP_BUFFER_LEN - stream_length) % CHECK_INTERVAL)

    def _fetch_advertised_parts(self):
        """
        Fetch parts being advertised by Twitch for stream.
        """
        # attempt to grab new parts from Twitch
        for _ in range(6):
            try:
                if _ >= 5:
                    raise StreamFetchError(self.channel.name, 'Request timed out while fetching new segments.')

                # fetch advertised stream parts
                announced_parts = m3u8.loads(self.channel.get_stream_playlist(self._index_uri)).segments
                self._last_part_announce = \
                    announced_parts[-1].program_date_time.replace(tzinfo=timezone.utc).timestamp()

                for _part in [StreamSegment.Part(_p) for _p in announced_parts]:
                    # add new parts to part buffer
                    if _part not in self._processed_parts:
                        self._processed_parts.add(_part)
                        self._incoming_part_buffer.append(_part)
                        self.vod.duration = int(_part.timestamp - self.vod.created_at)
                break

            # retry if request times out
            except RequestError as exc:
                self._log.debug('Error attempting to fetch new stream segments. (Attempt %s). Error: %s', _ + 1, exc)
                continue

    def _build_download_queue(self):
        """
        Creates queue of segments being downloaded using the incoming part buffer and already processed segments.
        """
        _unsupported_parts = set()
        # add parts to the associated segment
        for _part in self._incoming_part_buffer:
            if _part.title != 'live':
                self._log.debug('Ignoring advertisement part %s.', _part)
                continue

            # some streams have part lengths other than the default of 2.0. these cannot be aligned, and so we raise
            # an error if we encounter more than one if we are attempting to align the segments. we check for >2
            # instead of just 1 as the final part (or two) in the stream is often shorter than 2.0.
            if self._align_segments and _part.duration != 2.0:
                self._log.debug('Found part with unsupported duration (%s).', _part.duration)
                _unsupported_parts.add(_part)

            if len(_unsupported_parts) > 2:
                raise UnsupportedStreamPartDuration

            # add part to segment download queue
            self._log.debug('Adding part %s to download queue.', {'url': '...' + _part.url[-41:], 'timestamp': _part.timestamp, 'duration': _part.duration})
            self._download_queue.add_part(_part)

        # wipe part buffer
        self._incoming_part_buffer = []

    def _download_queued_segments(self):
        """
        Downloads all queued segments.
        """
        for _segment_id in self._download_queue.get_completed_segment_ids():
            self._download_segment(self._download_queue.pop_segment(_segment_id))

    def _download_segment(self, segment: StreamSegment):
        """
        Downloads a given segment.

        :param segment: StreamSegment to download.
        """
        # generate buffer file path
        _temp_buffer_file = Path(tempfile.gettempdir(), 'twitch-archiver',
                                 str(self.vod.s_id), str(f'{segment.id:05d}' + '.ts'))
        _temp_buffer_file.parent.mkdir(parents=True, exist_ok=True)

        # begin retry loop for download
        for _ in range(6):
            if _ >= 5:
                self._log.error('Maximum attempts reached while downloading segment %s.', segment.id)
                return

            self._log.debug('Downloading segment %s to %s.', segment.id, _temp_buffer_file)
            with open(_temp_buffer_file, 'wb') as _tmp_file:
                # iterate through each part of the segment, downloading them in order
                for _part in segment.parts:
                    try:
                        _r = requests.get(_part.url, stream=True, timeout=5)

                        if _r.status_code != 200:
                            return

                        # write part to file
                        for chunk in _r.iter_content(chunk_size=262144):
                            _tmp_file.write(chunk)

                    except RequestError as exc:
                        self._log.debug('Error downloading stream segment %s: %s', segment.id, str(exc))

            # move finished ts file to destination storage
            try:
                safe_move(Path(_temp_buffer_file), Path(self.output_dir, 'parts', str(f'{segment.id:05d}' + '.ts')))
                self._completed_segments.add(segment)
                self._log.debug('Stream segment: %s completed.', segment.id)
                break

            except Exception as exc:
                raise StreamSegmentDownloadError(segment.id, self.channel.name, exc) from exc

    def _get_final_segment(self):
        """
        Downloads the final stream segment.
        """
        # ensure final segment present
        if self._download_queue.is_segment_present(self._download_queue.current_id):
            self._log.debug('Fetching final stream segment.')
            self._download_segment(self._download_queue.get_segment_by_id(self._download_queue.current_id))

    def cleanup_temp_files(self):
        """
        Deletes all temporary files and directories.
        """
        shutil.rmtree(Path(self.output_dir, 'parts'), ignore_errors=True)
        if self.vod.v_id:
            shutil.rmtree(Path(tempfile.gettempdir(), 'twitch-archiver', str(self.vod.v_id)), ignore_errors=True)
        else:
            shutil.rmtree(Path(tempfile.gettempdir(), 'twitch-archiver', str(self.vod.s_id)), ignore_errors=True)
