"""
Module used for creating, accessing, updating and modifying database entries.
"""

import logging
import sqlite3

from sqlite3 import Error

from twitcharchiver.exceptions import DatabaseError, DatabaseQueryError

__db_version__ = 5


class Database:
    """
    Functions for interacting with the VOD database.
    """

    def __init__(self, database_path):
        """Class constructor.

        :param database_path: path to database file
        """
        self.log = logging.getLogger()

        self.database_path = str(database_path)

        try:
            self.log.debug('Database path: %s', self.database_path)
            self.connection = sqlite3.connect(self.database_path)
            self.cursor = self.connection.cursor()
            self.log.debug('Connection to SQLite DB successful.')

        except Error as exc:
            raise DatabaseError(f'Connection to SQLite DB failed: {exc}') from exc

    def setup(self):
        """
        Creates or updates database as needed.
        """
        # check db version
        version = self.execute_query('pragma user_version')[0][0]

        if version != __db_version__:
            # incremental database updating based on version number
            # create the latest db schema if none exists
            if version == 0:
                self.log.debug('No schema found, creating database.')
                [self.execute_query(_query) for _query in create_vods_table]

            # update version 2 schema to version 3
            if version == 2:
                self.log.debug('Performing incremental DB update. Version 2 -> Version 3.')
                self.update_database(2)
                version = 3

            # update version 3 schema to version 4
            if version == 3:
                self.log.debug('Performing incremental DB update. Version 3 -> Version 4.')
                self.update_database(3)
                version = 4

            if version == 4:
                self.log.debug('Performing incremental DB update. Version 3 -> Version 4.')
                self.update_database(4)

    def update_database(self, version):
        """
        Updates database to given version.

        :param version: desired version to upgrade to
        """
        self.log.debug("Setting up vods table if it doesn't already exist.")

        if version == 2:
            with Database(self.database_path) as _db:
                [_db.execute_query(query) for query in version_2_to_3_upgrade]

        if version == 3:
            with Database(self.database_path) as _db:
                [_db.execute_query(query) for query in version_3_to_4_upgrade]

        if version == 4:
            with Database(self.database_path) as _db:
                [_db.execute_query(query) for query in version_4_to_5_upgrade]

    # reference:
    #   https://codereview.stackexchange.com/questions/182700/python-class-to-manage-a-table-in-sqlite
    def __enter__(self):
        return self

    def __exit__(self, ext_type, exc_value, traceback):

        self.cursor.close()
        if isinstance(exc_value, Exception):
            self.connection.rollback()
            self.connection.close()
            raise DatabaseError(exc_value)

        self.connection.commit()
        self.connection.close()

    def execute_query(self, command, values=None):
        """Executes a given SQL statement.

        :param command: sql query to execute
        :param values: values to pass if inserting data - 'None' sends no other data
        :return: response from sqlite database to statement
        """
        self.log.debug('Executing SQL statement: %s', command)

        try:
            if not values:
                _r = self.cursor.execute(command).fetchall()
            else:
                self.log.debug('Values: %s', values)
                _r = self.cursor.execute(command, list(values.values())).fetchall()

        except Exception as exc:
            raise DatabaseQueryError(str(exc)) from exc

        return _r


create_vods_table = [
    """CREATE TABLE "vods" (
        "vod_id"            INTEGER,
        "stream_id"         INTEGER,
        "user_id"           INTEGER,
        "user_name"         TEXT,
        "chapters"          TEXT,
        "title"             TEXT,
        "description"       TEXT,
        "created_at"        DATETIME,
        "published_at"      DATETIME,
        "thumbnail_url"     TEXT,
        "duration"          INTEGER,
        "muted_segments"    TEXT,
        "chat_archived"     BIT,
        "video_archived"    BIT,
        PRIMARY KEY("vod_id","stream_id")
    );""",
    f"PRAGMA user_version = {__db_version__};",
    "PRAGMA journal_mode=WAL;"]

INSERT_VOD = """
REPLACE INTO
vods (vod_id, stream_id, user_id, user_name, chapters, title, description, created_at, published_at, thumbnail_url, 
      duration, muted_segments, chat_archived, video_archived)
VALUES
(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
"""

# change pk from id to user_id + created_at
# change type of created_at, published_at from TEXT to DATETIME
version_2_to_3_upgrade = [
    "ALTER TABLE vods RENAME TO vods_bak;",
    """CREATE TABLE "vods" (
        "id"                INTEGER,
        "stream_id"         INTEGER,
        "user_id"           INTEGER,
        "user_login"        TEXT,
        "user_name"         TEXT,
        "title"             TEXT,
        "description"       TEXT,
        "created_at"        DATETIME,
        "published_at"      DATETIME,
        "url"               TEXT,
        "thumbnail_url"     TEXT,
        "viewable"          TEXT,
        "view_count"        TEXT,
        "language"          TEXT,
        "type"              TEXT,
        "duration"          TEXT,
        "muted_segments"    TEXT,
        "store_directory"   TEXT,
        "duration_seconds"  INTEGER,
        PRIMARY KEY("user_id","created_at")
    );""",
    "INSERT INTO vods SELECT * FROM vods_bak;",
    "DROP TABLE vods_bak;",
    "PRAGMA user_version = 3;"]

# renamed id -> vod_id
# changed pk from user_id + created_at -> vod_id + stream_id
#   older vods do not have a stream id, so the vod_id will be copied in its place
# changed duration column type from TEXT -> INTEGER
#   duration_seconds will replace the current value
# removed duration_seconds column
# add video_archived and chat_archived columns
#   these are both set to 1 (true) for already archived streams
version_3_to_4_upgrade = [
    "ALTER TABLE vods RENAME TO vods_bak;",
    "UPDATE vods_bak SET stream_id = id WHERE stream_id IS NULL;",
    """CREATE TABLE "vods" (
        "vod_id"            INTEGER,
        "stream_id"         INTEGER,
        "user_id"           INTEGER,
        "user_login"        TEXT,
        "user_name"         TEXT,
        "title"             TEXT,
        "description"       TEXT,
        "created_at"        DATETIME,
        "published_at"      DATETIME,
        "url"               TEXT,
        "thumbnail_url"     TEXT,
        "viewable"          TEXT,
        "view_count"        TEXT,
        "language"          TEXT,
        "type"              TEXT,
        "duration"          INTEGER,
        "muted_segments"    TEXT,
        "store_directory"   TEXT,
        "video_archived"    BIT,
        "chat_archived"     BIT,
        PRIMARY KEY("vod_id","stream_id")
    );""",
    "INSERT INTO vods SELECT id, stream_id, user_id, user_login, user_name, title, description, created_at, "
    "published_at, url, thumbnail_url, viewable, view_count, language, type, duration_seconds, muted_segments, "
    "store_directory, 1, 1 FROM vods_bak;",
    "DROP TABLE vods_bak;",
    "PRAGMA user_version = 4;"]

# add field for VOD chapters
# remove user_login, url, view_count, viewable, language, type, store_directory fields
# swapped order of chat and video archive flags
# enable write-ahead logging
version_4_to_5_upgrade = [
    "ALTER TABLE vods RENAME TO vods_bak;",
    """CREATE TABLE "vods" (
        "vod_id"            INTEGER,
        "stream_id"         INTEGER,
        "user_id"           INTEGER,
        "user_name"         TEXT,
        "chapters"          TEXT,
        "title"             TEXT,
        "description"       TEXT,
        "created_at"        DATETIME,
        "published_at"      DATETIME,
        "thumbnail_url"     TEXT,
        "duration"          INTEGER,
        "muted_segments"    TEXT,
        "chat_archived"     BIT,
        "video_archived"    BIT,
        PRIMARY KEY("vod_id","stream_id")
    );""",
    "INSERT INTO vods SELECT vod_id, stream_id, user_id, user_name, NULL, title, description, "
    "created_at, published_at, thumbnail_url, duration, muted_segments, video_archived, chat_archived FROM vods_bak;",
    "DROP TABLE vods_bak;",
    "PRAGMA user_version = 5;",
    "PRAGMA journal_mode=WAL;"]
