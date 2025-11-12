**(2025-11-13) Version 4.4.4**
**Changes and Fixes:**
* Fix exception when video playlist doesn't include framerate.
* Fix issues fetching VODs due to API changes.


**(2025-09-27) Version 4.4.3**
**Changes and Fixes:**
* Fix invalid UTC import.
* Fix issues with stream qualities being unordered, causing incorrect quality to be downloaded (https://github.com/Brisppy/twitch-archiver/issues/54).


**(2025-04-30) Version 4.4.2**
**Changes and Fixes:**
* Fix issue with old VODs being sorted incorrectly when downloading.
* Fix issue fetching highlights from database if multiple highlights exist for a single VOD.
* Add handling for rare issue with VODs with no available video content.
* Fix issue with Twitch playlist durations being incorrect for some highlights.
* Fix issue failing to fetch the final segment for some highlights.
* Fix regression from 4.4.1 when fetching stream IDs.


**(2025-04-30) Version 4.4.1**
**Changes and Fixes:**
* Fix issue with HTTP 500 errors halting VOD archival (#44).
* Fix issue with highlights being ordered incorrectly (#44).
* Fix issue failing to fetch some Highlight stream IDs (#44).
* Fix issue with highlights where the final segment may be missing some data (#44).
* When archiving multiple channels, all the VODs from every channel will be collected and archived at once rather than consecutively.
* When downloading multiple VODs (including when archiving a channel), VODs will be downloaded oldest > newest. This behaviour can be disabled with the `--unsorted` argument (#45).
* Fix unsupported VODs causing halting.
* Improved safety of directory removal.
* Fix problems removing directories on Linux.
* Fix failing to fetch stream IDs for older VODs (#48).
* Fix timestamps of old VODs not being interpreted correctly.
* Fix issue with some VODs with un-retrievable video.
* Fix rare issue with VODs which aren't linked to a channel (#49).
* Fix inconsistency with folder timestamps.


**(2025-02-24) Version 4.4.0**
**Additions:**
* Support for downloading Highlights. This must be enabled when archiving channels with the `-H` or `--highlights` argument.
* Add support for Discord notifications via webhooks. This can be enable by passing the URL for a webhook with the `-W` or `--discord-webhook` argument.

**Changes and Fixes:**
* Fix occasional `QueryNotFound` errors when fetching VOD information.
* Fix issues with repairing VOD corruptions if the first part is corrupt.
* Updated Python requirements.
* Fix problems with Docker install failing.
* Docker install overhauled to use locally downloaded repository.


**(2025-01-01) Version 4.3.0**

**Additions:**
* Add support for Twitch Turbo and Subscriptions for disabling advertisements during stream and VOD archival (https://github.com/Brisppy/twitch-archiver/issues/39).

**Changes and Fixes:**
* Improvements to logging.
* Fix issue with VODs being marked as archived when merging failed.
* Fix issue with incorrect VOD parts being marked as corrupt in streams over ~26 hours (https://github.com/Brisppy/twitch-archiver/issues/40).
* Fix exception being raised when stream finishes without any parts having been downloaded (https://github.com/Brisppy/twitch-archiver/issues/41).


**(2024-10-05) Version 4.2.0**

**Additions:**
* Added chapter archiving for streams without VODs (https://github.com/Brisppy/twitch-archiver/issues/35).

**Changes and Fixes:**
* Fix stream archiver waiting the full buffer length even when the stream ends early.
* Fix issue with empty VOD attributes.
* Fix streams without VODs being merged out of order if they are under 5 minutes (https://github.com/Brisppy/twitch-archiver/issues/38).
* Fix issue with database updates failing for streams without VODs.
* Fix issue with final stream segment not being downloaded for streams with paired VODs (only affects streams where the VOD was deleted before the VOD downloader finished)
* Fix issue fetching VOD metadata when VOD has been deleted.
* Fix issue with updating stream chapters when no game info found.


**(2024-07-28) Version 4.1.0**

**IMPORTANT NOTICE**
Any stream archived without a paired VOD grabbed with the `watch` flag enabled is likely corrupt due to an overlooked error with the previous archiving method, this archiving method was and still is not guaranteed to be flawless, but is a "best effort" attempt at archiving these kinds of streams. Apologies that this wasn't caught sooner. 

**Changes and Fixes:**
 * Rewrote object for storing stream segments to prevent parts being potentially overwritten.
 * Add flag for ignoring part corruptions used for streams without paired VODs.
 * Fix stream merged with ffmpeg being out of order if stream was buffered before archiver ran (#36).
 * Fix streams without a VOD starting from a non-zero part number if buffered.
 * Fix streams without a VOD not being downloaded if they have unusual part durations.
 * Fix buffer being overwritten if archiving restarted during buffer interval.
 * Add debug flag to grab stream and ignore any paired VOD.


**(2024-06-22) Version 4.0.11**

**Changes and Fixes:**
 * Fix regression on Windows when merging VODs (#34).
 * Fix error if no channel videos available in live-only mode.
 * Fix error if no VODs available in database when archiving a stream-only channel.
 * Add handling for expected 404 errors at the end of a stream.
 * Fix exception when raising StreamSegmentDownloadError.

**(2024-05-26) Version 4.0.10**

**Changes and Fixes:**
 * Fix regression introduced in v4.0.9 for VODs with titles containing `'` on Linux (https://github.com/Brisppy/twitch-archiver/issues/33).

**(2024-05-26) Version 4.0.9**

**Changes and Fixes:**
 * Fix downloading of VODs with titles containing `!`  on Linux (https://github.com/Brisppy/twitch-archiver/issues/33).

**(2024-05-19) Version 4.0.8**

**Changes and Fixes:**
 * Fix issue with fetching VOD access tokens.
 * Fix failing tests.

**(2024-05-07) Version 4.0.7**

**Changes and Fixes:**
 * Fix error logging when downloading stream segments or fetching stream parts fails.
 * Fix issues with fetching stream parts for newly live streams.

**(2024-03-06) Version 4.0.6**

**Changes and Fixes:**
 * Fix downloaded thumbnails being very low resolution.
 * Raise temporary buffer before archiving to reduce chance for the paired stream VOD being missed.
 * Bump required Python version (3.7 -> 3.9).
 * Fix docker build failing due to outdated Python version (https://github.com/Brisppy/twitch-archiver/pull/32 - Thanks @helmut1337).

**(2024-01-28) Version 4.0.5**

**Additions**
 * Add ability to change temporary download directory via the environment variable `TWITCH_ARCHIVER_TMP_DIR`.

**Changes and Fixes:**
 * Optimized imports.
 * Fix test for `get_vod_owner()`
 * Fix real-time archiver failing to exit on some exception.
 * Fix fetching latest video if running in `live-only` mode.

**(2024-01-24) Version 4.0.4**

**Changes and Fixes:**
 * Add retrying to all API functions.
 * Reduce processing time for channel videos when running in `live-only` mode.
 * Fix issues with retry loop in stream downloader not functioning (https://github.com/Brisppy/twitch-archiver/issues/29).
 * Add catch and unsupported log message for highlight videos.

**(2024-01-18) Version 4.0.3**

**Changes and Fixes:**
 * Fix issues with stream titles containing multibyte characters (https://github.com/Brisppy/twitch-archiver/issues/27).
 * Fix issue with long stream titles resulting in file paths longer than Windows can handle.

**(2024-01-17) Version 4.0.2**

**Changes and Fixes:**
 * Fix issues with channels containing non-english display names (https://github.com/Brisppy/twitch-archiver/issues/26).

**(2024-01-13) Version 4.0.1**

This update has been a long time coming, pretty much all the central processing code was refactored to follow better, more modern coding standards. This was primarily to make it easier to find and fix bugs, and to develop new features.
In addition to this, some new features have also been implemented.

TLDR: expect everything faster and better polished, and any new features will be far easier to implement. 

NOTE: If you used any of the .dev versions with the `real-time` flag I would recommend re-downloading archived VODs, there were issues with segment alignment which may have corrupted the VODs.

**Additions:**
 * Added support for inputting a list of VOD IDs or channels has been added. Simply add `-f | --file` in conjunction with `-c | --channel` or `-v | --vod` and the corresponding value(s) will be interpreted as a file path.
 * Added parallel chat archiving to allow multiple chat logs to be downloaded simultaneously (https://github.com/Brisppy/twitch-archiver/issues/22).

**Changes and Fixes:**
 * Moved all API requests to the GQL API, authentication (`client-id / client-secret`) is no longer required for archiving.
 * Refactored entire codebase to follow object-oriented practices.
 * Add `--vod` as substitute for the `--vod-id` argument.
 * The `-w | --watch-only` mode is much lighter, using significantly fewer requests.
 * The `-L | --log-file` flag has been replaced with  `-L | --log-dir`, where a directory is supplied in which log files will be placed rather than a file.
 * Logging with the `--real-time` archiver enabled now properly works on both Windows and Linux.
 * Fixed an issue with older Twitch VODs with a different timestamp format (https://github.com/Brisppy/twitch-archiver/issues/25).

**(2023-08-31) Version 3.0.7**

**Changes and Fixes:**
 * Increased the start delay for newly live channels.

**(2023-08-13) Version 3.0.6**

**IMPORTANT**
This patch is to fix a critical bug which may have caused some VODs to not be downloaded. No data should be lost, but there may be invalid entries in the vod database (~/.config/twitch-archiver/vods.db), and some VODs may have failed to download.

My recommendation is to look over the past month comparing downloaded VODs to those on the channel, and to download any missing VODs manually to the channel directory.

**Changes and Fixes:**
 * Fixed an issue where new streams would be given old VOD ids causing them to be re-downloaded.

**(2023-07-10) Version 3.0.5**

**Changes and Fixes:**
 * Fixed an issue with lock files not clearing.
 * Cleaned up lock file creation and deletion.
 * Changed authentication to bypass new API requirements.
 * Reverted changes to chat logger (https://github.com/Brisppy/twitch-archiver/commit/ea78f2c12c7698a5f201013e5d940d9a601e7f06).
 * Reduced delay on archival start for recent streams.
 * Fixed an issue where a stream would be considered 'STREAM-ONLY' if it had just started.
 * Moved temporary buffer and .lock files to `$TMP/twitch-archiver`.
 * Fixed an issue with VOD download workers failing to exit.
 * Clarified some logging for live VODs.

**(2023-05-08) Version 3.0.4**

**Important:**
  * The real-time stream archiver is no longer used by default. See the [WIKI](https://github.com/Brisppy/twitch-archiver/wiki/Wiki#real-time-archiver) for more info.
  * The `-S | --stream-only` argument has been changed to `-l | --live-only`, and paired environment variable has changed from `TWITCH_ARCHIVER_STREAM_ONLY` to `TWITCH_ARCHIVER_LIVE_ONLY`.
  * The `-N | --no-stream` argument has been changed to `-a | --archive-only`, and paired environment variable has changed from `TWITCH_ARCHIVER_NO_STREAM` to `TWITCH_ARCHIVER_ARCHIVE_ONLY`.
  * Twitch-Archiver is now available as a Python package, see [here](https://github.com/Brisppy/twitch-archiver#installation--usage) for new installation and usage instructions.
  * Due to new anti-bot protections chat downloading is less reliable - if more than ~40 messages are sent in a second some may be missed.

**Additions:**
  * Added argument and environment variable to enable real-time stream archiving. Read [this](https://github.com/Brisppy/twitch-archiver/wiki/Wiki#real-time-archiver) before using.
  * Added exception for unsupported stream part duration.
  * Added buffer for freshly live streams to grab stream start if not being archived to a VOD.
  * Added logging for offline channels.
  * Added reliable method for grabbing archives of streams created within the last few seconds.

**Changes and Fixes:**
  * Restructured and cleaned up project for transition to Python package.
  * Removed `Utils` class.
  * Improved update checker to support development and release candidate builds.
  * Fixed an issue if the connection timed out while fetching new stream segments.
  * Reduced non-debug logging verbosity.
  * Reduced archive delay for streams started within the last few seconds.
  * Changed method of downloading chat logs to get around new authentication requirements.
  * Fixed missing requirements from Python package.
  * Updated dockerfile.

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
