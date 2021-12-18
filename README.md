# Simple Discord Music Bot

## Local Host:
### Requirements:
* Python 3.7+
* FFMPEG executable in PATH
* Discord, both app and developer bot (ownership)

### Usage:
* Manually create a .env-file and enter your bot-token (as BOT_TOKEN) and bot-id (as BOT_ID)
* Install required python libraries with ```pip install -r requirements.txt```
* Open your terminal, navigate to the file location and type "py main.py"
* Add your bot to your server with the link provided in the Discord Developer Portal

## Cloud Host (Heroku):
### Requirements:
* Python, FFMPEG and Opus Buildpacks in Heroku
* Discord, both app and developer bot (ownership)

### Usage:
* Connect the Git-Repository to Heroku under Deploy on the Heroku Dashboard
* Add your bot-token (as BOT_TOKEN) and bot-id (as BOT_ID) as config vars to Heroku 
* Deploy it under Deploy (not needed if automatic deploys are enabled)
* Turn on your Dyno Worker under Resources
* Add your bot to your server with the link provided in the Discord Developer Portal

## Key Features:
* Ability to play songs from youtube urls or search keywords
* Play, queue, repeat, pause, resume, stop and skip songs
* View songs in queue and remove specific songs
* Multi-server usage support
* Youtube playlist support (limited to playlists with ~ 20 songs due to bandwidth reasons)

## Future Milestones:
* support for spotify links