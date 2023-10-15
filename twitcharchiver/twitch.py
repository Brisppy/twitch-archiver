"""
Class for storing various basic objects used for information handling.
"""
import re
from pathlib import Path

import m3u8


class Category:
    """
    A category is used to describe what a Twitch stream is currently streaming. This class stores information
    relating to categories.
    """
    def __init__(self, game=None):
        """
        Class constructor.

        :param game: dictionary of game information retrieved from Twitch
        :type game: dict
        """
        if game is None:
            game = {'id': 0, 'name': ""}

        self.id = game['id']
        self.name = game['name']

        self.slug = None
        self.thumbnail_url = None
        self.display_name = None
        self.type = None

        for _k in game.keys():
            if _k == 'slug':
                self.slug = game[_k]
            if _k == 'boxArtURL':
                self.thumbnail_url = game[_k]
            if _k == 'displayName':
                self.display_name = game[_k]
            if _k == 'type':
                self.type = game[_k]

    def __repr__(self):
        return str({'id': self.id, 'name': self.name})

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return bool(self.id == other.id)

    def get_category_info(self):
        """
        Generates and returns a dictionary of relevant category information.

        :return: dict of values which make up a category.
        """
        return {'id': self.id, 'slug': self.slug, 'thumbnail_url': self.thumbnail_url, 'name': self.name,
                'display_name': self.display_name, 'type': self.type}


class Chapters:
    """
    Chapters split up an individual VOD into separate 'moments', describing what game or stream category each
    section of the VOD contains. This class stores moments related to a given Twitch VOD.
    """
    def __init__(self, moments: list[dict] = None):
        """
        Class constructor.

        :param moments: moments list retrieved from Twitch API
        :type moments: list[dict]
        """
        self.moments = []

        if moments:
            self.moments = [self.Moment(m) for m in moments]

    def __repr__(self):
        return str([m for m in self.moments])

    def insert_moment(self, moment):
        """
        Inserts a moment into the chapter.

        :param moment: A moment retrieved from the Twitch API
        :type moment: Moment
        """
        self.moments.append(self.Moment(moment))

        return self

    @staticmethod
    def create_chapter_from_category(category: Category, duration: int):
        """
        Converts a Category into a single chapter which spans an entire VOD. This is useful when no chapters
        are included with a VOD - this happens when only one category spans its entire length.

        :param category: A VOD category retrieved from the Twitch API.
        :type category: Category
        :param duration: length in seconds of the VOD
        :type duration: int
        :return: A Chapter containing a moment of the category spanning the entire VOD length
        :rtype: Chapters
        """
        # convert category into moment spanning whole duration of VOD
        _segment = Segment(0, duration)
        _moment = Chapters.Moment()
        # todo check if 'GAME CHANGE' is the same name used by TWITCH
        _moment.type = 'GAME CHANGE'
        _moment.description = category.display_name
        _moment.category = category
        _moment.segment = _segment

        return Chapters().insert_moment(_moment)

    class Moment:
        """
        A moment is a portion of a Twitch VOD containing a game or category and the section of the VOD it belongs
        to. This class stores that information.
        """
        def __init__(self, moment: dict = None):
            """
            Class constructor.

            :param moment:
            """

            self.id = None
            self.segment = None
            self.type = None
            self.description = None

            if moment:
                self.id = moment['id']
                self.segment = Segment(moment['positionMilliseconds'] / 1000,
                                       moment['durationMilliseconds'] / 1000)
                self.type = moment['type']
                self.description = moment['description']

            if 'game' in moment:
                self.category = Category(moment['game'])
            else:
                self.category = None

        def __repr__(self):
            return str({'description': self.description, 'type': self.type, 'segment': self.segment})


class Segment:
    """
    A segment of a video is a portion of it described with a position from the start, and a duration.
    """
    def __init__(self, position: float, duration: float):
        """

        :param position:
        :param duration:
        """
        self.position: float = position
        self.duration: float = duration

    def __repr__(self):
        return str({'position': self.position, 'duration': self.duration})


class MpegSegment(Segment):
    """
    MpegSegments are the individual pieces which comprise a Twitch VOD. This class defines the storage and
    provides useful methods for handling them.
    """
    def __init__(self, segment_id: int() = 0, duration: int = 0, url: str = "", muted: bool = False):
        """

        :param segment_id:
        :param duration:
        :param url:
        :param muted:
        """
        self.muted = muted
        self.id = segment_id
        self.url = url
        super().__init__(self.id * 10, duration)

    def __repr__(self):
        return str({'id': self.id, 'duration': self.duration, 'muted': self.muted})

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if type(self) == type(other):
            return self.id == other.v_id
        else:
            return False

    def __ne__(self, other):
        if type(self) == type(other):
            return self.id != other.v_id
        else:
            return True

    @staticmethod
    def convert_m3u8_segment(segment: m3u8.Segment):
        """
        Derives an MpegSegment from a provided m3u8.Segment instance

        :param segment:
        :type segment:
        :return:
        :rtype:
        """
        return MpegSegment(int(re.sub(
            r'.ts|-[a-zA-Z]*.ts', '', segment.uri)), segment.duration, segment.uri, 'muted' in segment.uri)

    def id_padded(self):
        """
        Generates a 0-padded ID for the current segment.
        """
        return f'{self.id:05d}'

    def generate_url(self, base_url: str):
        """
        Generates a URL based on the segment's id and whether it is muted or not
        """
        return ''.join([base_url, str(self.id), '-muted' if self.muted else '', '.ts'])

    def generate_path(self, base_path: Path):
        """
        Generates a path based on the segment's ID and a provided base path
        """
        return Path(base_path, self.id_padded() + '.ts')
