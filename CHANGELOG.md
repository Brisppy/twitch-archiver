**(2023-xx-xx) Version 3.0.0**

**Important:**
  * The real-time stream archiver is no longer used by default. See the [WIKI](https://github.com/Brisppy/twitch-archiver/wiki/Wiki#real-time-archiver) for more info.
  * The `-S | --stream-only` argument has been changed to `-l | --live-only`, and paired environment variable has changed from `TWITCH_ARCHIVER_STREAM_ONLY` to `TWITCH_ARCHIVER_LIVE_ONLY`.
  * The `-N | --no-stream` argument has been changed to `-a | --archive-only`, and paired environment variable has changed from `TWITCH_ARCHIVER_NO_STREAM` to `TWITCH_ARCHIVER_ARCHIVE_ONLY`.
  * Twitch-Archiver is now available as a Python package, see [here](https://github.com/Brisppy/twitch-archiver#installation--usage) for new installation and usage instructions.

**Additions:**
  * Added argument and environment variable to enable real-time stream archiving. Read [this](https://github.com/Brisppy/twitch-archiver/wiki/Wiki#real-time-archiver) before using.
  * Added exception for unsupported stream part duration.
  * Added buffer for freshly live streams to grab stream start if not being archived to a VOD.
  * Added logging for offline channels.

**Changes and Fixes:**
  * Restructured and cleaned up project for transition to Python package.
  * Removed `Utils` class.
  * Improved update checker to support development and release candidate builds.
  * Fixed an issue if the connection timed out while fetching new stream segments.
  * Reduced non-debug logging verbosity. 

**(2023-02-28) Version 2.2.3**

**Additions:**
  * Added support for archiving subscriber-only VODs (https://github.com/Brisppy/twitch-archiver/issues/19).

**Changes and Fixes:**
  * Increased verbosity of some Twitch-related exceptions.
  * Implemented a system for verifying and ignoring part corruptions on Twitch's side (https://github.com/Brisppy/twitch-archiver/issues/20).
  * Fixed an issue with muted stream segments which are later unmuted (https://github.com/Brisppy/twitch-archiver/issues/20).
  * Fixed a halting issue on Internet disconnect when using pushbullet.
  * Fixed streams being detected as not having a corresponding VOD if archived very soon after going live.

**(2023-01-14) Version 2.2.2**

**Additions:**
  * Added grabbing of VOD thumbnail.
  * Added grabbing of VOD chapters and inclusion in VOD file.
  * Added dockerfile for container creation (https://github.com/Brisppy/twitch-archiver/pull/18 - Thanks HeliosLHC).
  * Added logging for subscriber-only VODs.

**Changes and Fixes:**
  * Fix overwriting of Twitch credentials provided as an argument (https://github.com/Brisppy/twitch-archiver/pull/13 - Thanks HeliosLHC).
  * Add .gitignore (https://github.com/Brisppy/twitch-archiver/pull/15 - Thanks HeliosLHC).
  * Increased chunk download size (https://github.com/Brisppy/twitch-archiver/pull/14 - Thanks HeliosLHC).
  * Added logging for when pushbullet rate-limit is exceeded.
  * Added limited retrying for downloaded segments which are corrupt.
  * Changed to using stream_id rather than vod_id for stream lock files and cleaned up related log messages.
  * Fixed an issue with handling of corrupt part errors.
  * Updated exception handling to follow newer standard.
  * Fixed an issue where overwriting corrupt parts would raise an exception.

**(2022-12-12) Version 2.2.1**

**Changes and Fixes:**
  * Fixed chat conversion erroring out if chat logs could not be grabbed.
  * Fixed request timeouts causing vod downloader to error out rather than retry.
  * Fixed an issue when using the '--no-stream' argument due to missing channel data (https://github.com/Brisppy/twitch-archiver/issues/5 - Thanks smeinecke).
  * Updated chat archiver to support new Twitch API.
  * Fixed an issue with GitHub version checker.
  * Added missing SQL escape and cleanup (https://github.com/Brisppy/twitch-archiver/pull/7 - Thanks koroban).
  * Fixed an issue with VODs containing muted segments not downloading, and added method for ignoring muted segments which are identified as corrupt when converting the vod file (https://github.com/Brisppy/twitch-archiver/issues/8 - Thanks koroban for finding this).
  * Added channel name to pushbullet notifications.
  * Improved logging for FFmpeg VOD conversion.
  * Moved extra README info to GitHub wiki.

**(2022-11-07) Version 2.2.0**

**Additions:**
  * Added issue templates.
  * Added ability to show the current configuration.
  * Added the ability to archive streams which aren't being saved by Twitch.
  * Added support for providing URLs as arguments for the vods or channels to grab.
  * Added an argument (--stream-only) for only grabbing currently live streams.
  * When downloading channels, missing formats (video / chat) will now be grabbed on subsequent runs of TA.
  * Added documentation for running TA as a systemd service.

**Changes and Fixes:**
  * Improved corrupt segment error logging.
  * Added and updated various docstrings.
  * Increased maximum allowed invalid segments when downloading streams.
  * Sanitized credentials in debug logs.
  * Added incremental database upgrading.
  * Updated database schema (Version 2 -> 3 -> 4).
  * Added the ability to update database vod entries.
  * Fixed rate limiter for vod part grabber.
  * Improved message for streams with unsupported part length.
  * Fixed an issue with downloading the final stream segment(s).
  * Fixed an issue if the user specified an invalid resolution.
  * Fixed an issue with incorrect timestamps being used and stored.
  * Fixed an issue with failed segments being marked as completed.
  * Fixed an  issue where incorrect timestamps were being used to measure time since vods were created, causing new vods to error out as they were not yet available.
  * Fixed an issue where TA would randomly freeze when fetching data due to lack of request timeouts.
  * Minor formatting changes.

**(2022-05-11) Version 2.1.1**

**Changes and Fixes:**
  * Fixed an issue where the same segment would increment the bad segment counter repeatedly.
  * Rewrote stream downloader to resolve rare VOD corruption issues.

**(2022-05-01) Version 2.1**

**Additions:**
  * TA can now be launched in 'watch' mode, checking for new streams/vods for a specified channel every 10 seconds.

**Changes and Fixes:**
  * Fixed stream downloader loop missing parts if the processing time and wait period exceeded the time vod parts were advertised by Twitch.
  * Streams with variable length segments will only be downloaded via the VOD downloader as the stream downloader cannot combine them reliably.
  * Added typing to some arguments.

**(2022-04-04) Version 2.0**

For the past few ~~weeks~~ months I've been working to completely refactor the code as the original v1.0 was built when I was just beginning to understand Python - this lead to various issues with code standardization, cleanliness and the foundational logic of the code which made it increasingly difficult to track down bugs and add new features.

And so I've created version 2.0, following better guidelines, formatting and vastly improving the cleanliness and readability of the code. This isn't to say it's perfect, I am still learning and open to any feedback.

With all that said, I've tried to test this code as much as possible - but with the amount of changes and additions there still may be bugs.

A quick note for anyone who used any of the beta releases, many things have changed during the course of development, and I would strongly recommend re-downloading any VODs downloaded with these beta versions as they may be incomplete or contain errors.

**What's new:**
  * New video and chat download methods:
    * Improved speed and reliability.
    * Better error handling.
    * Less reliance on external sources in case Twitch makes any breaking changes.
  * True live archiving is now implemented, with parts downloaded as they are streamed.
  * Added a configuration file for storing secrets for reuse.
  * Added progress bars to download, conversion and export of video files and chat logs.
  * Added a check on run and command-line notification if a new update is released.
  * A more verbose chat log is are now archived along with a readable version.
  * Added the ability to choose the number of download threads with an argument '--threads'.
  * Added the ability to archive individual (or multiple) VODs.
  * Added the ability to archive multiple channels in one command.
  * Added the ability to print the saved config.
  * Added the ability to choose the downloaded stream resolution and framerate.
  * Added error handling for VODs with segment discontinuities.
  * Added the '--quiet' and '--debug' arguments.
  * Added an option for logging to a file.
  * Added a license (GNU Affero Public License).


**What's changed:**
  * Variables can now be passed as arguments rather than via a file.
  * OAuth token is saved in the configuration rather than a file.
  * Implemented a new, more accurate method for determining whether a VOD is live or not.
  * Transitioned to a single database for all archived channel VODs.
  * Removed erroneous characters from VOD directory names.
  * Modified database schema. See [this gist](https://gist.github.com/522bffef7bee7eb17c1eacbf1a35aadc) if you wish to migrate your TA v1.x database(s) to the new format and location. This needs to be done to seamlessly resume archiving channels.
  * Repository renamed (twitch-vod-archiver -> twitch-archiver).
  * Improved VOD length verification.
  * Chat logs are now saved while archiving live VODs rather than after stream finishes.
  * Greatly improved logging.
  * Various minor fixes and improvements.
  * Overhauled changelog and readme.
  * Added minimum ffmpeg version (4.3.1)

**(2022-01-23) Version 1.3.1**

* Fixed an issue with vods created very recently

**(2022-01-17) Version 1.3**

* Fixed an issue with how the CHANNEL directory is created using the supplied CLI argument, which may not match with the name provided by Twitch. - Thanks to MambaBoyy for bringing this to my attention.
* If database access fails when trying to write VOD_INFO, a new file named '.vodinfo' will be created containing this information. This is very important if a VOD is deleted as the data may no longer be available.
* Fixed an issue if the script was run too soon after a channel goes live.
* Fixed an issue with the SendPushbullet function, where some calls were missing required information.
* Fixed an issue with where temporary files were stored on Windows.
* Fixed an issue with the vod duration not being properly updated for live downloads.
* Removed possible race condition with lock files.
* Fixed VOD download loop breaking at the wrong time.
* Fixed the VOD verification length which was using the original VOD length rather than currently downloaded length.
* Fixed an issue where a VOD would be processed twice if multiple instances of TVA run in parallel.
* Other minor changes and formatting adjustments.

**(2021-10-05) Version 1.2**

This is a bit of an emergency patch as Twitch changed their API slightly (Although it's mostly my fault for using an unsupported method of authenticating against their API).
* Completely redid how authentication is done as Twitch blocked the previous method using twitch account credentials. The old APP_CLIENT_ID and APP_CLIENT_SECRET are now the CLIENT_ID and CLIENT_SECRET, and no other credentials are required now.
* Added some more notifications for various errors, and would highly recommend configuring pushbullet.
* Fixed the lock file not being removed if adding the VOD information to the VOD database was unsuccessful.
* Modified the README to fit the new authentication scheme.

**(2021-10-01) Version 1.1**

Live streams can now be archived done by downloading the VOD as it currently stands and is still being updated, and adding new chunks as they are added to the VOD on twitch's servers.
A VOD locking system is also now in place; if a VOD archive fails with an error, the VOD will NOT be downloaded again until the error is resolved by the user, and lockfile manually removed. Lock files are in the CHANNEL directory, using the format '.(VOD_ID)', for example 'Z:\\twitch-archive\\Brisppy\\.lock.1025444786'.
I've spent quite a bit of time both working on and testing this new feature, there shouldn't be any major issues but if you do encounter any problems please create an issue, and I will try to resolve it ASAP.

**(2021-05-23) Version 1.0**

Changed how the .ts files are combined, as the previous method using ffmpeg would create files of varying (and often incorrect) lengths.
This change has FINALLY allowed the downloaded VODs to match the expected length, rather than being offset by any number of seconds with the old method.
There are also many small changes to formatting.

I'm quite satisfied with the state of the script as a whole - so this will be the initial release (1.0)

**(2021-04-17)**

Twitch modified (https://dev.twitch.tv/docs/change-log) their API which broke the database insertion - I've rewritten how the database is accessed / added to and added the new fields to the database. When new values are added by Twitch, the script WILL need to be updated to support them,  I'll try and keep the script up to date, but there are instructions in 'src/vod_database_connect.py' for updating this yourself, although this may cause issues if your changes clash with the ones I make.

**IMPORTANT (2021-03-30)**

A large flaw in the code slipped past me, causing VODs downloaded with the initial Python version of the script to be a jumbled mess of various segments of the VODs. Sadly there isn't really a way of recovering the VOD, short of re-downloading it. This is an important lesson for me, and I'm sorry that I didn't catch this. I will be testing updates more thoroughly moving forward before pushing them. 

My recommendation is to basically nuke any VODs downloaded with the Python version (including the sqlite database, or individually affected VODs contained within with a sqlite browser), and redownload them with this new version (Which I properly tested :P). You can tell if a VOD is broken by skipping to random points and watching for 20 or so seconds, if the video skips, the VOD is out of order.

I also modified how the .ts files are combined into the final .mp4 as the old method wasn't the 'proper' method (Even though it still worked). This shouldn't necessitate a redownload, but if you really want to be careful you probably should.

The VOD subdirectory variable has also been slightly modified, so now the CHANNEL variable (Used to create the folder VOD_SUBDIRECTORY/CHANNEL) now uses the provided value from Twitch, rather than what is provided as an argument. This may not cause any issues as the only modification should be to the capitalization of the VOD_SUBDIRECTORY/CHANNEL folder, but you may still want to update this manually if your filesystem differentiates between capitalized and non-capitalized directory names.

**(2021-03-25)**

Now rewritten in Python 3, allowing the script to work on MOST platforms.
This is the first time I've fully rewritten a script in another language, there may be small issues so please let me know if you have any problems.
Some filenames MAY have changed (Spaces are tolerated again in VOD names again). Sqlite3 is also now used to store information about downloaded VODs.

NOTE: If you used the previous shell only version, the script will re-download ALL VODs as I changed the way they are stored.
If you wish to add VODs downloaded with previous versions to the new database, use this script: https://gist.github.com/Brisppy/5365d9cf816c1c45ab985032fd6976bf
