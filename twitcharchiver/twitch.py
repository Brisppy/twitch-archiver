"""
Class for storing various basic objects used for information handling.
"""
import re
from pathlib import Path

import m3u8


class Category:
    def __init__(self, game=None):
        """
        A category is used to describe what a Twitch stream is currently streaming. This class stores information
        relating to categories.

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

    def get_category_info(self):
        return {'id': self.id, 'slug': self.slug, 'thumbnail_url': self.thumbnail_url, 'name': self.name,
                'display_name': self.display_name, 'type': self.type}


class Chapters:
    def __init__(self, moments: list[dict] = None):
        """
        Chapters split up an individual VOD into separate 'moments', describing what game or stream category each
        section of the VOD contains. This class stores moments related to a given Twitch VOD.

        :param moments: moments list retrieved from Twitch API
        :type moments: list[dict]
        """
        self.moments = []

        if moments:
            self.moments = [self.Moment(m) for m in moments]

    def __repr__(self):
        return str([m for m in self.moments])

    def insert_moment(self, moment):
        self.moments.append(self.Moment(moment))

    def create_chapter_from_category(self, category: Category, duration):
        # convert category into moment spanning whole duration of VOD
        _segment = Segment(0, duration)
        _moment = self.Moment()
        # todo check if 'GAME CHANGE' is the same name used by TWITCH
        _moment.type = 'GAME CHANGE'
        _moment.description = category.display_name
        _moment.category = category
        _moment.segment = _segment
        self.moments = [_moment]

        return self

    class Moment:
        def __init__(self, moment: dict = None):
            """
            A moment is a segment of a Twitch VOD containing a game or category and the section of the VOD it belongs
            to. This class stores that information.
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
    def __init__(self, position: float, duration: float):
        """
        A segment of a VOD is a section of it which can be described by its starting position and duration.
        """
        self.position: float = position
        self.duration: float = duration

    def __repr__(self):
        return str({'position': self.position, 'duration': self.duration})


class MpegSegment(Segment):
    def __init__(self, segment_id: int() = 0, duration: int = 0, url: str = "", muted: bool = False):
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
