import logging
import sqlite3

from sqlite3 import Error

from src.exceptions import DatabaseError, DatabaseQueryError

__db_version__ = 2


class Database:
    """
    Functions for interacting with the VOD database.
    """
    def __init__(self, pushbullet_key, database_path):
        """Class constructor.

        :param pushbullet_key: token for pushbullet requests
        :param database_path: path to database file
        """
        self.log = logging.getLogger('twitch-archive')

        self.database_path = database_path        
        self.pushbullet_key = pushbullet_key

        try:
            self.log.debug('Database path: ' + str(self.database_path))
            self.connection = sqlite3.connect(self.database_path)
            self.cursor = self.connection.cursor()
            self.log.debug('Connection to SQLite DB successful.')

        except Error as e:
            raise DatabaseError(self.pushbullet_key, 'Connection to SQLite DB failed: ' + str(e))

    def setup_database(self):
        """
        Sets up VODs table.
        """
        self.log.debug("Setting up vods table if it doesn't already exist.")

        with Database(self.pushbullet_key, self.database_path) as db:
            db.execute_query(create_vods_table)

    # reference:
    #   https://codereview.stackexchange.com/questions/182700/python-class-to-manage-a-table-in-sqlite
    def __enter__(self):
        return self

    def __exit__(self, ext_type, exc_value, traceback):

        self.cursor.close()
        if isinstance(exc_value, Exception):
            self.connection.rollback()
            self.connection.close()
            raise DatabaseError(self.pushbullet_key, exc_value)

        else:
            self.connection.commit()
            self.connection.close()

    def execute_query(self, command, values=None):
        """Executes a given SQL statement.

        :param command: sql query to execute
        :param values: values to pass if inserting data - 'None' sends no other data
        :return: response from sqlite database to statement
        """
        self.log.debug('Executing SQL statement: ' + str(command))

        try:
            if not values:
                _r = self.cursor.execute(command).fetchall()
            else:
                self.log.debug('Values: ' + str(values))
                _r = self.cursor.execute(command, list(values.values())).fetchall()

        except Exception as e:
            raise DatabaseQueryError(self.pushbullet_key, str(e))

        return _r


create_vods_table = """
    CREATE TABLE IF NOT EXISTS vods (
    id INTEGER PRIMARY KEY,
    stream_id INTEGER,
    user_id INTEGER,
    user_login TEXT,
    user_name TEXT,
    title TEXT,
    description TEXT,
    created_at TEXT,
    published_at TEXT,
    url TEXT,
    thumbnail_url TEXT,
    viewable TEXT,
    view_count INTEGER,
    language TEXT,
    type TEXT,
    duration TEXT,
    muted_segments TEXT,
    store_directory TEXT,
    duration_seconds INTEGER
    );
"""

column_list = {
    'id': 'INTEGER PRIMARY KEY',
    'stream_id': 'INTEGER',
    'user_id': 'INTEGER',
    'user_login': 'TEXT',
    'user_name': 'TEXT',
    'title': 'TEXT',
    'description': 'TEXT',
    'created_at': 'TEXT',
    'published_at': 'TEXT',
    'url': 'TEXT',
    'thumbnail_url': 'TEXT',
    'viewable': 'TEXT',
    'view_count': 'INTEGER',
    'language': 'TEXT',
    'type': 'TEXT',
    'duration': 'TEXT',
    'muted_segments': 'TEXT',
    'store_directory': 'TEXT',
    'duration_seconds': 'INTEGER'
}

create_vod = """
INSERT INTO
vods (id, stream_id, user_id, user_login, user_name, title, description, created_at, published_at, url,
        thumbnail_url, viewable, view_count, language, type, duration, muted_segments, store_directory,
        duration_seconds)
VALUES
(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
"""
