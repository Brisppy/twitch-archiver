# This file contains functions pertaining to the sqlite3 database used to store downloaded VOD information.
import sqlite3
from sqlite3 import Error


# This function is used for connecting to the sqlite3 database.
def CreateConnection(path):
    connection = None
    try:
        connection = sqlite3.connect(path)
        print('INFO: Connection to SQLite DB successful.')
    except Error as e:
        print('ERROR: Connection to SQLite DB failed:', e)
    return connection


# This function is used to execute commands against the database.
def ExecuteQuery(connection, query, data=False):
    cursor = connection.cursor()
    try:
        if data:
            cursor.execute(query, data)
        else:
            cursor.execute(query)
        connection.commit()
        print('INFO: SQLite query successful.')
    except Error as e:
        print('ERROR: SQLite query failed:', e)


# This function is used to read data from the database.
def ExecuteReadQuery(connection, query):
    cursor = connection.cursor()
    result = None
    try:
        cursor.execute(query)
        result = cursor.fetchall()
        return result
    except Error as e:
        print('ERROR: SQLite read query failed:', e)


# Query vods table, and create if it doesn't already exist.
create_vods_table = """
CREATE TABLE IF NOT EXISTS vods (
  id INTEGER PRIMARY KEY,
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
  vod_subdirectory TEXT,
  vod_title TEXT
);
"""
