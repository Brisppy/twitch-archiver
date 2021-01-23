# twitch-vod-archiver
A script for archiving past Twitch VODs as well as the corresponding chat log.

# Requirements
* **Python 3.8**
* **ffmpeg** (ffprobe is used to verify the download was successful)
* **[tcd](https://github.com/PetterKraabol/Twitch-Chat-Downloader)** (pip3 install tcd)
* **[Streamlink](https://streamlink.github.io/)** (pip3 install streamlink)

# Installation
Clone the repository
```git clone https://github.com/Brisppy/twitch-vod-archiver```

Modify the variables in twitch-vod-archiver.sh
| Variable | Function |
|-------|------|
|```CLIENT_ID```|Twitch account Client ID - A method for retrieving this is shown below (See Retrieving Tokens).
|```OAUTH_TOKEN```|Twitch account OAuth token - A method for retrieving this is shown below (See Retrieving Tokens).
|```APP_CLIENT_ID```|Application Client ID retrieved from dev.twitch.tv.
|```APP_CLIENT_SECRET```|Application Secret retrieved from dev.twitch.tv.
|```VOD_DIRECTORY```|Location in which VODs will be stored, users are stored in separate folders within - **Do NOT end with a slash(/)**.
|```SEND_PUSHBULLET```|**OPTIONAL:** 0/1 Whether or not you wish to send a pushbullet notification on download failure.
|```PUSHBULLET_KEY```|**OPTIONAL** Your Pushbullet API key.

# Usage
Run the script, supplying the channel name. I use a crontab entry to run it nightly to grab any new VODs.

```./twitch-vod-archiver.sh brisppy```

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

# TODO
* Swap tokens / client ID to the dev.twitch.tv application variant. Would require token creation / refreshing.
* Allow multiple channels to be archived with one script
* Use parallel tmux processes to download multiple VODs at once
