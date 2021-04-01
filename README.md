# 📁 Twitch Vod Archiver 📁
A python script for archiving past Twitch VODs along with their corresponding chat logs for an entire Twitch channel.
Chat logs are grabbed with [tcd](https://github.com/PetterKraabol/Twitch-Chat-Downloader), with VODs downloaded with [twitch-dl](https://github.com/ihabunek/twitch-dl), before being remuxed with [ffmpeg](https://ffmpeg.org/).

My recommendation is to run this script on a schedule, allowing it to grab new VODs on a regular basis.


## Recent Changes
### **IMPORTANT (2021-03-30)**

A large flaw in the code slipped past me, causing VODs downloaded with the Python version of the script to be a jumbled mess of various segments of the VODs. Sadly there isn't really a way of recovering the VOD, short of re-downloading it. This is an important lesson for me, and I'm sorry that I didn't catch this. I will be testing updates more thoroughly moving forward before pushing them. 

My recommendation is to basically nuke any VODs downloaded with the Python version (including the sqlite databse, or individually affected VODs contained within with an sqlite browser), and redownload them with this new version (Which I properly tested :P). You can tell if a VOD is broken by skipping to random points and watching for 20 or so seconds, if the video skips, the VOD is out of order.

I also modified how the .ts files are combined into the final .mp4 as the old method wasn't the 'proper' method (Even though it still worked). This shouldn't necessitate a redownload, but if you really want to be careful you probably should.

The VOD subdirectory variable has also been slightly modified, so now the CHANNEL variable (Used to create the folder VOD_SUBDIRECTORY/CHANNEL) now uses the provided value from Twitch, rather than what is provided as an argument. This may not cause any issues as the only modification should be to the capitalization of the VOD_SUBDIRECTORY/CHANNEL folder, but you may still want to update this manually if your filesystem differentiates between capitalized and non-capitalized directory names.

**(2021-03-25)**

Now rewritten in Python 3, allowing the script to work on MOST platforms.
This is the first time I've fully rewritten a script in another language, there may be small issues so please let me know if you have any problems.
Some filenames MAY have changed (Spaces are tolerated again in VOD names again). Sqlite3 is also now used to store information about downloaded VODs.

NOTE: If you used the previous shell only version, the script will re-download ALL VODs as I changed the way they are stored.
If you wish to add VODs downloaded with previous versions to the new database, use this script: https://gist.github.com/Brisppy/5365d9cf816c1c45ab985032fd6976bf

# Notes
* VODs may end up slightly longer than advertised on Twitch, I believe this is due to slight variations in the framerate. If anyone finds a fix for this, please let me know. (It can be avoided by PIPING a list of the .ts files into FFMPEG, but I can't figure out how to do this with Python's Subprocess module without using os-specific commands.)
* We use the downloaded VOD duration to ensure that the VOD was successfully downloaded and combined properly, this is checked against Twitch's own API, which can show incorrect values. If you come across a VOD with a displayed length in the Twitch player longer than it actually goes for (If the VOD ends before the 'end' is reached), create a file named '.ignorelength' inside of the VOD's directory (Within the 'VOD_DIRECTORY/CHANNEL/DATE-VOD_NAME-VOD_ID' folder), you may also want to verify that the VODs are matching after archiving too.
* If your VOD_DIRECTORY is located on a SMB/CIFS share, you may encounter issues with querying and adding to the sqlite database. This can be resolved by mounting the share with the 'nobrl' option.
* If you wish to speed up (or slow down) the downloading of VOD pieces, CTRL-F (Find) the line with '--max-workers 20' and change the number to however many pieces you wish to download at once.

# Requirements
* **Python 3.8**
* **[ffmpeg](https://ffmpeg.org/)** (Must be accessible via PATH)
* **[tcd](https://github.com/PetterKraabol/Twitch-Chat-Downloader)** (python -m pip install tcd) (Must be accessible via PATH)
* **[twitch-dl](https://github.com/ihabunek/twitch-dl)** (python -m pip install twitch-dl) (Must be accessible via PATH)

# Installation
Clone the repository (Or download via the 'Code' button on the top of the page):

```git clone https://github.com/Brisppy/twitch-vod-archiver```

Modify the variables in 'variables.py'.
| Variable | Function |
|-------|------|
|```CLIENT_ID```|Twitch account Client ID - A method for retrieving this is shown below (See Retrieving Tokens).
|```OAUTH_TOKEN```|Twitch account OAuth token - A method for retrieving this is shown below (See Retrieving Tokens).
|```APP_CLIENT_ID```|Application Client ID retrieved from dev.twitch.tv.
|```APP_CLIENT_SECRET```|Application Secret retrieved from dev.twitch.tv.
|```VOD_DIRECTORY```|Location in which VODs will be stored, users are stored in separate folders within - **End with TWO backslashes on Windows (e.g 'Z:\\').**
|```SEND_PUSHBULLET```|**OPTIONAL:** 0/1 Whether or not you wish to send a pushbullet notification on download failure. **Do not surround with quotes.**
|```PUSHBULLET_KEY```|**OPTIONAL:** Your Pushbullet API key.

# Usage
Run the script, supplying the channel name. I use a crontab entry to run it nightly to grab any new VODs.

```python ./twitch-vod-archiver.py Brisppy```

# Retrieving Tokens
### To retrieve your CLIENT_ID and OAUTH_TOKEN:
1. Navigate to your twitch.tv channel page
2. Open the developer menu (F12 in Chrome)
3. Select the 'Network' tab and refresh the page
4. Press CTRL+F to bring up the search, and type in 'access_token' followed by ENTER
5. Double-click on the line beginning with URL, and the Headers menu should appear
6. Under 'Request Headers' you should find the line beginning with 'client-id:', this is used as the CLIENT_ID variable
7. Under 'Query String Parameters' you should find the line beginning with 'oauth_token:', this is used as the OAUTH_TOKEN variable

![Chrome developer menu showing location of CLIENT_ID and OAUTH_TOKEN](https://i.imgur.com/zbDbbFF.jpg)

### To retrieve the APP_CLIENT_ID and APP_CLIENT_SECRET:
1. Navigate to dev.twitch.tv
2. Register a new app called VOD Archiver with any redirect URL and under any Category
3. The provided Client ID is used as the APP_CLIENT_ID variable
4. The provided Client Secret is used as the APP_CLIENT_SECRET

# Extra Info
### How does the script work?
1. Upon being run, the script imports various Python modules, along with the 'variables.py' and 'src/vod_database_connect.py' files.
2. The main() function is then called which begins by creating directories if required, and setting up the sqlite database (Stored in the VOD_DIRECTORY/CHANNEL folder).
3. The USER_ID is then requested via the Twitch API for later use.
4. Now we check if the channel is live, if so, we ignore the most recent VOD as it is not yet complete.
5. We then get a list of VODs from the Channel via the Twitch API, and compare them with the downloaded VODs acquired from the sqlite database, adding NEW VODs to a queue.
6. Now we process each VOD in the VOD queue, first retrieving the chat via twitch-chat-downloader, then the video via twitch-dl.
7. After downloading the actual video files (Currently in the .ts format), we must combine them with ffmpeg.
8. After combining the .ts files into a single .mp4, we check the video length against the expected length retrieved from the Twitch API.
9. If the video length matches, we delete any temporary files, add the VOD information to the database and move onto the next VOD.

### How are the files stored?
Downloaded files are stored under one large directory which you provide in 'variables.py' (VOD_DIRECTORY).

    VOD_DIRECTORY ─┬─ CHANNEL#1 ─┬─ VOD#1 ─┬─ CHAT.log
                   │             │         └─ VOD.mp4
                   │             │
                   │             ├─ VOD#2 ─┬─ CHAT.log
                   │             │         └─ VOD.mp4
                   │             │
                   │             └─ vod_db.sqlite
                   │
                   └─ CHANNEL#2 ─┬─ VOD#1 ─┬─ CHAT.log
                                 │         └─ VOD.mp4
                                 │
                                 ├─ VOD#2 ─┬─ CHAT.log
                                 │         └─ VOD.mp4
                                 │
                                 └─ vod_db.sqlite

### Limitations
* Only one VOD can be grabbed at a time PER channel which is being archived, but multiple scripts for different CHANNELS can be run simultaneously.
* VODs cannot be downloaded individually - only a channel may be supplied.
* Subscriber-only VODs cannot be archived yet as it's not supported by [twitch-dl](https://github.com/ihabunek/twitch-dl), the creater has expressed some [interest](https://github.com/ihabunek/twitch-dl/issues/48) in implementing though.
