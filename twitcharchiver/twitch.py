"""
Class for storing various basic objects used for information handling.
"""
import re
from pathlib import Path

import m3u8


class Category:
    """
    A category is used to describe what a Twitch stream is currently streaming. This class stores information
    relating to 'categories'.
    """
    def __init__(self, game: dict = None):
        """
        Class constructor.

        :param game: dictionary of game information retrieved from Twitch
        """
        if game is None:
            game = {'id': 0, 'name': ""}

        self.id: int = game['id']
        self.name: str = game['name']

        self.slug: str = ""
        self.thumbnail_url: str = ""
        self.display_name: str = ""
        self.type: str = ""

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
        """
        Create str from Category.

        :return: Category as a string
        :rtype: str
        """
        return str({'id': self.id, 'name': self.name})

    def __eq__(self, other):
        """
        Compares two Category instances.

        :param other: Category to compare against
        :type other: Category
        :return: True if they match
        :rtype: bool
        """
        if isinstance(other, self.__class__):
            return bool(self.id == other.id)
        raise TypeError

    def to_dict(self):
        """
        Generates and returns a dictionary of relevant category information.

        :return: dict of values which make up a category.
        :rtype: dict
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
        """
        self._moments: list[Chapters.Moment] = []

        if moments:
            self._moments = [self.Moment(m) for m in moments]

    def __bool__(self):
        """
        Check if Chapter initialized.

        :return: True if Chapter initialized
        :rtype: bool
        """
        return bool(self._moments)

    def __repr__(self):
        """
        Convert Chapter to string.

        :return: string of Chapter moments
        :rtype: str
        """
        return str(self._moments)

    def __iter__(self):
        """
        Iterate through Chapter Moments.

        :return: Moments as iterable:
        :rtype: collections.Iterable[Moment]
        """
        for _m in self._moments:
            yield _m

    def insert_moment(self, moment):
        """
        Inserts a moment into the chapter.

        :param moment: A moment retrieved from the Twitch API
        :type moment: Moment
        """
        self._moments.append(moment)

    @staticmethod
    def create_chapter_from_category(category: Category, duration: int):
        """
        Converts a Category into a single chapter which spans an entire VOD. This is useful when no chapters
        are included with a VOD - this happens when only one category spans its entire length.

        :param category: A VOD category retrieved from the Twitch API.
        :param duration: length in seconds of the VOD
        :return: A Chapter containing a moment of the category spanning the entire VOD length
        :rtype: Chapters
        """
        # convert category into moment spanning whole duration of VOD
        _moment = Chapters.Moment()
        # 'GAME_CHANGE' is type assigned to chapters by Twitch
        _moment.type = 'GAME_CHANGE'
        _moment.description = category.display_name or category.name
        _moment.category = category
        _moment.segment = Segment(0, duration)

        _chapter = Chapters()
        _chapter.insert_moment(_moment)
        return _chapter

    class Moment:
        """
        A moment is a portion of a Twitch VOD containing a game or category and the section of the VOD it belongs
        to. This class stores that information.
        """
        def __init__(self, moment: dict = None):
            """
            Class constructor.

            :param moment: dict of values retrieved from Twitch
            """

            self.id: int = int()
            self.segment: Segment = Segment()
            self.type: str = ""
            self.description: str = ""
            self.category: Category = Category()

            if moment:
                self.id = moment['id']
                self.segment = Segment(moment['positionMilliseconds'] / 1000,
                                       moment['durationMilliseconds'] / 1000)
                self.type = moment['type']
                self.description = moment['description']

                if 'game' in moment.keys():
                    self.category = Category(moment['game'])

        def __repr__(self):
            """
            Returns Moment as a string.

            :return: str of Moment attributes.
            :rtype: str
            """
            return str({'description': self.description, 'type': self.type, 'segment': self.segment})

        def __bool__(self):
            return bool(self.id)


class Segment:
    """
    A segment of a video is a portion of it described with a position from the start, and a duration.
    """
    def __init__(self, position: float = 0.0, duration: float = 0.0):
        """
        Class constructor.

        :param position: start position of segment in seconds
        :param duration: length of segment in seconds
        """
        self.position: float = position
        self.duration: float = duration

    def __repr__(self):
        """
        Returns Segment as a string.

        :return: Segment attributes as string.
        :rtype: str
        """
        return str({'position': self.position, 'duration': self.duration})


class MpegSegment(Segment):
    """
    MpegSegments are the individual pieces which comprise a Twitch VOD. This class defines the storage and
    provides useful methods for handling them.
    """
    def __init__(self, segment_id: int() = 0, duration: int = 0, url: str = "", muted: bool = False):
        """
        Class constructor.

        :param segment_id:
        :param duration:
        :param url:
        :param muted:
        """
        self.muted: bool = muted
        self.id: int = segment_id
        self.url: str = url
        super().__init__(self.id * 10, duration)

    def __repr__(self):
        return str({'id': self.id, 'duration': self.duration, 'muted': self.muted})

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.id == other.id
        raise TypeError

    def __ne__(self, other):
        if isinstance(other, self.__class__):
            return self.id != other.id
        raise TypeError

    def __lt__(self, other):
        if isinstance(other, self.__class__):
            return self.id < other.id
        raise TypeError

    @staticmethod
    def convert_m3u8_segment(segment: m3u8.Segment, base_url: str):
        """
        Derives an MpegSegment from a provided m3u8.Segment instance

        :param segment: m3u8.Segment
        :type segment:
        :param base_url: url directory where segments (00000.ts, 000001.ts, ...) are located online
        :type base_url: str
        :return: segment generated from the provided m3u8 segment
        :rtype: MpegSegment
        """
        return MpegSegment(int(re.sub(r'.ts|-[a-zA-Z]*.ts', '', segment.uri)), segment.duration,
                           f'{base_url}{segment.uri}', 'muted' in segment.uri)

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
