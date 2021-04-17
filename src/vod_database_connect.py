# This file contains functions pertaining to the sqlite3 database used to store downloaded VOD information.
# If Twitch modifies the fields returned by their 'Get Videos' API, the database MUST be migrated prior to adding
# new vods. I will try to do this whenever a change is made, but if you with to make the modifications youreslf you can,
# but I don't recommend this as it may conflict with future updates I push:
#   1: Modify the 'create_vods_table' and 'current_column_list' variables to reflect the changed fields

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
        return
    except Error as e:
        print('ERROR: SQLite query failed:', e)
        return 1

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


# Used to compare the current database columns to what we expect them to be.
def CompareDatabase(connection):
    cursor = connection.cursor()
    # Create a list of columns
    try:
        # Retrieve columns
        columns = cursor.execute('select * from vods')
        column_list = [column[0] for column in columns.description]
    except Error as e:
        print('ERROR: SQLite read query failed:', e)
    # Compare the list of columns present to what is expected
    if column_list == current_column_list.keys():
        print('DEBUG: Database columns match current version.')
    else:
        print('INFO: Database columns do not match current version, performing migration.')
        MigrateDatabase(connection, column_list)


# This function allows us to migrate the database when Twitch decides to modify data they return (grr)
def MigrateDatabase(connection, column_list):
    cursor = connection.cursor()
    # Compare columns and extarct any uniques
    missing_columns = [column for column in current_column_list.keys() if column not in column_list]
    print('DEBUG: Missing columns: ', missing_columns)
    # Add any columns which are NOT present
    try:
        for column in missing_columns:
            cursor.execute('ALTER TABLE vods ADD COLUMN {col} {datatype};'.format(col=column, 
                                                                                 datatype=current_column_list[column]))
    except Error as e:
        print('ERROR: Error adding column to sqlite table:', e)
    # Rename the 'vods' database
    try:
        cursor.execute('DROP TABLE IF EXISTS vods_old;')
        cursor.execute('ALTER TABLE vods RENAME TO vods_old;')
    except Error as e:
            print('ERROR: Error renaming sqlite table:', e)
    # Now we recreate it using the 'create_vods_table' variable
    ExecuteQuery(connection, create_vods_table)
    # Copy the data over
    try:
        cursor.execute('INSERT INTO vods SELECT id, stream_id, user_id, user_login, user_name, title, description, \
                        created_at, published_at, url, thumbnail_url, viewable, view_count, language, type, duration, \
                        muted_segments, vod_subdirectory, vod_title FROM vods_old;')
    except Error as e:
        print('ERROR: Error copying data to from old sqlite table:', e)
    print('INFO: Database migration successful.')
    connection.commit()

# Query vods table, and create if it doesn't already exist.
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
  vod_subdirectory TEXT,
  vod_title TEXT
);
"""

current_column_list = {'id': 'INTEGER PRIMARY KEY', 'stream_id': 'INTEGER', 'user_id': 'INTEGER', 'user_login': 'TEXT',
                       'user_name': 'TEXT', 'title': 'TEXT', 'description': 'TEXT', 'created_at': 'TEXT',
                       'published_at': 'TEXT', 'url': 'TEXT', 'thumbnail_url': 'TEXT','viewable': 'TEXT',
                       'view_count': 'INTEGER', 'language': 'TEXT', 'type': 'TEXT','duration': 'TEXT',
                       'muted_segments': 'TEXT', 'vod_subdirectory': 'TEXT', 'vod_title': 'TEXT'}
