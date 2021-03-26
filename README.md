# 📁 Twitch Vod Archiver 📁
A python script for archiving past Twitch VODs along with their corresponding chat logs for an entire Twitch channel.

The script can be run on a schedule, grabbing new VODs as they appear.


## Recent Changes
**(2021-03-25)**

Now rewritten in Python 3, allowing the script to work on MOST platforms.
This is the first time I've fully rewritten a script in another language, there may be small issues so please let me know if you have any problems.
Some filenames MAY have changed (Spaces are tolerated again in VOD names again). Sqlite3 is also now used to store information about downloaded VODs.

NOTE: If you used the previous shell only version, the script will re-download ALL VODs as I changed the way they are stored.
If you wish to add VODs downloaded with previous versions to the new database, use this script:

# Requirements
* **Python 3.8**
* **[ffmpeg](https://ffmpeg.org/)** (Must be accessible via PATH)
* **[tcd](https://github.com/PetterKraabol/Twitch-Chat-Downloader)** (python -m pip install tcd) (Must be accessible via PATH)
* **[twitch-dl](https://github.com/ihabunek/twitch-dl)** (python -m pip install twitch-dl) (Must be accessible via PATH)

# Installation
Clone the repository (Or download via the 'Code' button on the top of the page):

```git clone https://github.com/Brisppy/twitch-vod-archiver```

Modify the variables in twitch-vod-archiver.sh
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

# Download method
Streamlink was originally used for downloading the VODs, but doesn't give much control over how the pieces are combined. Instead twitch-dl is used with the --no-join argument to allow the script to do the joining of the downloaded pieces in order to solve the issue outlined below.

The method for downloading the actual VOD is quite convoluted in order to resolve an issue with VOD 864884048, a 28HR long VOD which when downloaded, never was the correct length. 
For some reason the some of the downloaded .ts files have incorrect timestamps, with piece 09531.ts having a 'start' value of 95376.766, and the following piece (09532.ts) having a 'start' value of -56.951689. When combining all of the pieces this produces an error (non-monotonous dts in output stream), resulting in an output file with a shorter duration than the original VOD. To resolve this, the .ts files are combined with ffmpeg using their numbered order rather than included start value or .m3u8 playlist.

# Extra Info
### How does the script work?
1. Upon being run, the script imports various Python modules, along with the 'variables.py' and 'src/vod_database_connect.py' files.
2. The main() function is then called which begins by creating directories if required, and setting up the sqlite database (Stored in the VOD_DIRECTORY/CHANNEL folder).
3. The USER_ID is then requested via the Twitch API for later use.
4. Now we check if the channel is live, if so, we ignore the most recent VOD as it is not yet complete.
5. We then get a list of VODs from the Channel via the Twitch API, and compare them with the downloaded VODs acquired from the sqlite database, adding NEW VODs to a queue.
6. Now we process each VOD in the VOD queue, first retrieving the chat via twitch-chat-downloader, then the video via twitch-dl.
7. After downloading the actual video files (Currently in the .ts format), we must combine them with ffmpeg.
8. After combining the .ts files into a single .mp4, we check the video length against the expecetd length retrieved from the Twitch API.
9. If the video length matches, we delete any temporary files, add the VOD information to the database and move onto the next VOD.

### How are the files stored?
Downloaded files are stored under one large directory which you provide in 'variables.py' (VOD_DIRECTORY).

# 📁 Twitch Vod Archiver 📁
A python script for archiving past Twitch VODs along with their corresponding chat logs for an entire Twitch channel.

The script can be run on a schedule, grabbing new VODs as they appear.


## Recent Changes
**(2021-03-25)**

Now rewritten in Python 3, allowing the script to work on MOST platforms.
This is the first time I've fully rewritten a script in another language, there may be small issues so please let me know if you have any problems.
Some filenames MAY have changed (Spaces are tolerated again in VOD names again). Sqlite3 is also now used to store information about downloaded VODs.

NOTE: If you wish to add VODs downloaded with previous versions to the new database, use this script:

# Requirements
* **Python 3.8**
* **[ffmpeg](https://ffmpeg.org/)** (Must be accessible via PATH)
* **[tcd](https://github.com/PetterKraabol/Twitch-Chat-Downloader)** (python -m pip install tcd) (Must be accessible via PATH)
* **[twitch-dl](https://github.com/ihabunek/twitch-dl)** (python -m pip install twitch-dl) (Must be accessible via PATH)

# Installation
Clone the repository (Or download via the 'Code' button on the top of the page):

```git clone https://github.com/Brisppy/twitch-vod-archiver```

Modify the variables in twitch-vod-archiver.sh
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

# Download method
Streamlink was originally used for downloading the VODs, but doesn't give much control over how the pieces are combined. Instead twitch-dl is used with the --no-join argument to allow the script to do the joining of the downloaded pieces in order to solve the issue outlined below.

The method for downloading the actual VOD is quite convoluted in order to resolve an issue with VOD 864884048, a 28HR long VOD which when downloaded, never was the correct length. 
For some reason the some of the downloaded .ts files have incorrect timestamps, with piece 09531.ts having a 'start' value of 95376.766, and the following piece (09532.ts) having a 'start' value of -56.951689. When combining all of the pieces this produces an error (non-monotonous dts in output stream), resulting in an output file with a shorter duration than the original VOD. To resolve this, the .ts files are combined with ffmpeg using their numbered order rather than included start value or .m3u8 playlist.

# Extra Info
### How does the script work?
1. Upon being run, the script imports various Python modules, along with the 'variables.py' and 'src/vod_database_connect.py' files.
2. The main() function is then called which begins by creating directories if required, and setting up the sqlite database (Stored in the VOD_DIRECTORY/CHANNEL folder).
3. The USER_ID is then requested via the Twitch API for later use.
4. Now we check if the channel is live, if so, we ignore the most recent VOD as it is not yet complete.
5. We then get a list of VODs from the Channel via the Twitch API, and compare them with the downloaded VODs acquired from the sqlite database, adding NEW VODs to a queue.
6. Now we process each VOD in the VOD queue, first retrieving the chat via twitch-chat-downloader, then the video via twitch-dl.
7. After downloading the actual video files (Currently in the .ts format), we must combine them with ffmpeg.
8. After combining the .ts files into a single .mp4, we check the video length against the expecetd length retrieved from the Twitch API.
9. If the video length matches, we delete any temporary files, add the VOD information to the database and move onto the next VOD.

### How are the files stored?
Downloaded files are stored under one large directory which you provide in 'variables.py' (VOD_DIRECTORY).

    VOD_DIRECTORY ─┬─ CHANNEL#1 ─┬─ VOD#1 ─── CHAT.log
                   │             │            VOD.mp4
                   │             │
                   │             ├─ VOD#2 ─── CHAT.log
                   │             │            VOD.mp4
                   │             │
                   │             └─ vod_db.sqlite
                   │
                   └─ CHANNEL#2 ─┬─ VOD#1 ─── CHAT.log
                                 │            VOD.mp4
                                 │
                                 ├─ VOD#2 ─── CHAT.log
                                 │            VOD.mp4
                                 │
                                 └─ vod_db.sqlite

# Limitations
* Only the 100 most recent VODs are retrieved - this can be fixed but wasn't necessary for my us case - I can add it if required though.
* Only one VOD can be grabbed at a time PER channel which is being archived - You can increase the number of download threads though
* VODs cannot be downloaded individually - only a channel may be supplied


# TODO
* Swap tokens / client ID to the dev.twitch.tv application variant. Would require token creation / refreshing.
* Add ability to grab VODs past #100


# Limitations
* Only the 100 most recent VODs are retrieved - this can be fixed but wasn't necessary for my us case - I can add it if required though.
* Only one VOD can be grabbed at a time PER channel which is being archived - You can increase the number of download threads though
* VODs cannot be downloaded individually - only a channel may be supplied


# TODO
* Swap tokens / client ID to the dev.twitch.tv application variant. Would require token creation / refreshing.
* Add ability to grab VODs past #100
