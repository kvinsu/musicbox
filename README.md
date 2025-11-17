![ReadMeHeader](https://user-images.githubusercontent.com/28533473/153753726-e0133b1c-7274-4856-9f70-2ed5408a9417.jpg)

# MusicBox

* A simple YouTube music bot for Discord

## Key Features

* **Music Playback** — from YouTube video or playlist URLs or using search keywords
* **Playlist support** — automatically skips unavailable/copyrighted videos and plays remaining tracks
* **Queue management** — view, add, remove, shuffle, and clear songs
* **Playback controls** — play, pause, resume, stop, skip, and repeat modes
* **Multi-server support** — independent queues per guild
* **Fun commands** — coin flips, GIF search, hugs, dere-type generator, and more
* **Lightweight queueing** — metadata-only enqueuing for improved performance on large playlists

## Local Setup

### Requirements

* [Python 3.11+](https://www.python.org/downloads/) (tested with 3.11.7+)
* [FFmpeg](https://ffmpeg.org/download.html) executable in PATH
* Discord app and a bot account (with ownership or admin permissions)

### Installation

1. **Clone/download** this repository
2. **Create a `.env` file** in the root directory:
   ```
   BOT_TOKEN=your_bot_token_here
   BOT_ID=your_bot_id_here
   ```
3. **Install dependencies**
   ```sh
   pip install -r requirements.txt
   ```
4. **Add the bot to your server** using the OAuth2 invite link from the Discord Developer Portal and admin permissions
5. **Start the bot**
   ```sh
   python main.py
   ```

## Commands

### Music

* `!play <url|search>` — Play a song or playlist from YouTube
* `!skip` — Skip the current song
* `!pause` — Pause playback
* `!resume` — Resume playback
* `!stop` — Stop playback and clear the queue
* `!repeat` / `!loop` — Toggle repeat mode
* `!queue` — Show the current queue
* `!nowplaying` / `!np` — Show the currently playing song
* `!clear` — Clear the queue
* `!remove <index>` — Remove a song from the queue by index
* `!shuffle` — Shuffle the queue
* `!join` — Make the bot join your voice channel
* `!leave` — Make the bot leave the voice channel

### General

* `!ping` — Show bot latency
* `!hello` / `!hi` / `!hey` — Greet the bot
* `!about` / `!info` / `!stats` — Bot information
* `!decide <question>` — Get a yes/no answer
* `!hug [username]` — Send a hug GIF
* `!slap [username]` / `!punch` / `!hit` — Send a slap GIF
* `!coinflip` / `!flip` / `!coin` — Flip a coin (German)
* `!lolcoinflip` / `!lolflip` / `!lolcoin` — LoL-themed coin flip (German)
* `!fliflaflu` / `!enemenemiste` / `!schnickschnackschnuck` — Rock-paper-scissors (German)
* `!roulette [option1 option2 ...]` / `!select` / `!choice` — Select a random option
* `!dere <username>` — Generate a dere-type personality
* `!gif <search>` — Fetch a random GIF from Tenor

### Admin (Owner Only)

* `!shutdown` / `!s` / `!sleep` — Shut down the bot
* `!invite` — Get the bot's invite link
* `!servers` — List all servers the bot is in

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BOT_TOKEN` | ✅ | - | Discord bot token |
| `BOT_ID` | ✅ | - | Discord bot client ID |
| `TENOR_TOKEN` | ❌ | - | Tenor API key (for GIF commands; uses fallback if missing) |
| `PLAYLIST_MAX` | ❌ | 100 | Max tracks to enqueue from a playlist |
| `SELF_HOST` | ❌ | false | Set to `true` if self-hosting |


## Future Milestones

* support for spotify links/playlists
