(2021-10-01) Version 1.1

Live streams can now be archived done by downloading the VOD as it currently stands and is still being updated, and adding new chunks as they are added to the VOD on twitch's servers.

A VOD locking system is also now in place; if a VOD archive fails with an error, the VOD will NOT be downloaded again until the error is resolved by the user, and lockfile manually removed. Lock files are in the CHANNEL directory, using the format '.(VOD_ID)', for example 'Z:\\twitch-archive\\Brisppy\\.lock.1025444786'.

I've spent quite a bit of time both working on and testing this new feature, there shouldn't be any major issues but if you do encounter any problems please create an issue and I will try to resolve it ASAP.

(2021-05-23) Version 1.0

Changed how the .ts files are combined, as the previous method using ffmpeg would create files of varying (and often incorrect) lengths.
This change has FINALLY allowed the downloaded VODs to match the expected length, rather than being offset by any number of seconds with the old method.
There are also many small changes to formatting.

I'm quite satisfied with the state of the script as a whole - so this will be the initial release (1.0)

(2021-04-17)

Twitch modified (https://dev.twitch.tv/docs/change-log) their API which broke the database insertion - I've rewritten how the database is accessed / added to and added the new fields to the database. When new values are added by Twitch, the script WILL need to be updated to support them,  I'll try and keep the script up to date, but there are instructions in 'src/vod_database_connect.py' for updating this youself, although this may cause issues if your changes clash with the ones I make.

IMPORTANT (2021-03-30)

A large flaw in the code slipped past me, causing VODs downloaded with the initial Python version of the script to be a jumbled mess of various segments of the VODs. Sadly there isn't really a way of recovering the VOD, short of re-downloading it. This is an important lesson for me, and I'm sorry that I didn't catch this. I will be testing updates more thoroughly moving forward before pushing them. 

My recommendation is to basically nuke any VODs downloaded with the Python version (including the sqlite databse, or individually affected VODs contained within with an sqlite browser), and redownload them with this new version (Which I properly tested :P). You can tell if a VOD is broken by skipping to random points and watching for 20 or so seconds, if the video skips, the VOD is out of order.

I also modified how the .ts files are combined into the final .mp4 as the old method wasn't the 'proper' method (Even though it still worked). This shouldn't necessitate a redownload, but if you really want to be careful you probably should.

The VOD subdirectory variable has also been slightly modified, so now the CHANNEL variable (Used to create the folder VOD_SUBDIRECTORY/CHANNEL) now uses the provided value from Twitch, rather than what is provided as an argument. This may not cause any issues as the only modification should be to the capitalization of the VOD_SUBDIRECTORY/CHANNEL folder, but you may still want to update this manually if your filesystem differentiates between capitalized and non-capitalized directory names.

(2021-03-25)

Now rewritten in Python 3, allowing the script to work on MOST platforms.
This is the first time I've fully rewritten a script in another language, there may be small issues so please let me know if you have any problems.
Some filenames MAY have changed (Spaces are tolerated again in VOD names again). Sqlite3 is also now used to store information about downloaded VODs.

NOTE: If you used the previous shell only version, the script will re-download ALL VODs as I changed the way they are stored.
If you wish to add VODs downloaded with previous versions to the new database, use this script: https://gist.github.com/Brisppy/5365d9cf816c1c45ab985032fd6976bf
