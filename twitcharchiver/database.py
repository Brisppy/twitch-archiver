"""
Module used for creating, accessing, updating and modifying database entries.
"""

import logging
import sqlite3

from sqlite3 import Error

from twitcharchiver.exceptions import DatabaseError, DatabaseQueryError

__db_version__ = 4


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

        except Error as e:
            raise DatabaseError(f'Connection to SQLite DB failed: {e}') from e

    def setup_database(self):
        """
        Sets up VODs table.
        """
        self.log.debug("Setting up vods table if it doesn't already exist.")

        with Database(self.database_path) as db:
            [db.execute_query(query) for query in create_vods_table]

    def update_database(self, version):
        """
        Updates database to given version.

        :param version: desired version to upgrade to
        """
        self.log.debug("Setting up vods table if it doesn't already exist.")

        if version == 2:
            with Database(self.database_path) as db:
                [db.execute_query(query) for query in version_2_to_3_upgrade]

        if version == 3:
            with Database(self.database_path) as db:
                [db.execute_query(query) for query in version_3_to_4_upgrade]

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

        except Exception as e:
            raise DatabaseQueryError(str(e)) from e

        return _r


create_vods_table = [
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
    f"PRAGMA user_version = {__db_version__};"]

CREATE_VOD = """
INSERT INTO
vods (stream_id, user_id, user_login, user_name, title, description, created_at, published_at, url, thumbnail_url,
      viewable, view_count, language, type, duration, muted_segments, vod_id, store_directory, video_archived,
      chat_archived)
VALUES
(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
"""

UPDATE_VOD = """
UPDATE vods
SET stream_id=?, user_id=?, user_login=?, user_name=?, title=?, description=?, created_at=?,
    published_at=?, url=?, thumbnail_url=?, viewable=?, view_count=?, language=?, type=?,
    duration=?, muted_segments=?, vod_id=?, store_directory=?, video_archived=?, chat_archived=?
WHERE stream_id IS ?;
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
