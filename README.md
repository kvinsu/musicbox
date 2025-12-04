![ReadMeHeader](https://user-images.githubusercontent.com/28533473/153753726-e0133b1c-7274-4856-9f70-2ed5408a9417.jpg)

# MusicBox

* A simple YouTube music bot for Discord

## Key Features

* **Hybrid Commands** — all commands work with both prefix (`!play`) and slash (`/play`) formats
* **Music Playback** — from YouTube video or playlist URLs or using search keywords
* **Spotify Support** — play Spotify tracks, playlists, and albums (resolves to YouTube)
* **Playlist support** — automatically skips unavailable/copyrighted videos and plays remaining tracks
* **Queue management** — view, add, remove, shuffle, and clear songs
* **Playback controls** — play, pause, resume, stop, skip, and repeat modes
* **Multi-server support** — independent queues per guild
* **Fun commands** — coin flips, GIF search, and more
* **Lightweight queueing** — metadata-only enqueuing for improved performance on large playlists
* **Docker support** — deployment with Docker Compose

## Local Setup

### Requirements

* [Python 3.11+](https://www.python.org/downloads/) (tested with 3.11.7+)
* [FFmpeg](https://ffmpeg.org/download.html) executable in PATH
* [Docker](https://www.docker.com/) to run the app
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

## Docker Setup

1. **Clone/download** this repository
2. **Create a `.env` file** in the root directory:
   ```
   BOT_TOKEN=your_bot_token_here
   BOT_ID=your_bot_id_here
   COMMAND_PREFIX=!
   PLAYLIST_MAX=100
   TENOR_TOKEN=your_tenor_token_here
   ```
3. **Build and run** the container:
   ```sh
   docker-compose up -d
   ```
4. **Stop the bot**:
   ```sh
   docker-compose down
   ```

## Commands

All commands support both **prefix** (`!command`) and **slash** (`/command`) formats.

### Music

* `/play <url|search>` or `!play <url|search>` — Play a song or playlist from YouTube
* `/skip` or `!skip` — Skip the current song
* `/pause` or `!pause` — Pause playback
* `/resume` or `!resume` — Resume playback
* `/stop` or `!stop` — Stop playback and clear the queue
* `/repeat` or `!repeat` / `!loop` — Toggle repeat mode
* `/queue` or `!queue` — Show the current queue
* `/nowplaying` or `!nowplaying` / `!np` — Show the currently playing song
* `/clear` or `!clear` — Clear the queue
* `/remove <index>` or `!remove <index>` — Remove a song from the queue by index
* `/shuffle` or `!shuffle` — Shuffle the queue
* `/join` or `!join` — Make the bot join your voice channel
* `/leave` or `!leave` — Make the bot leave the voice channel

### General

* `/ping` or `!ping` — Show bot latency
* `/hello` or `!hello` / `!hi` / `!hey` — Greet the bot
* `/about` or `!about` / `!info` / `!stats` — Bot information
* `/decide <question>` or `!decide <question>` — Get a yes/no answer
* `/hug [user]` or `!hug [username]` — Send a hug GIF
* `/slap [user]` or `!slap [username]` / `!punch` / `!hit` — Send a slap GIF
* `/coinflip` or `!coinflip` / `!flip` / `!coin` — Flip a coin (German)
* `/fliflaflu` or `!fliflaflu` / `!enemenemiste` / `!schnickschnackschnuck` — Rock-paper-scissors (German)
* `/roulette <options>` or `!roulette [option1 option2 ...]` / `!select` / `!choice` — Select a random option
* `/dere <user>` or `!dere <username>` — Generate a dere-type personality
* `/gif <search>` or `!gif <search>` — Fetch a random GIF from Tenor
* `!lolcoinflip` / `!lolflip` / `!lolcoin` — LoL-themed coin flip (German, prefix only)

### Admin (Owner Only)

* `/shutdown` or `!shutdown` / `!s` / `!sleep` — Shut down the bot
* `/invite` or `!invite` — Get the bot's invite link
* `/servers` or `!servers` — List all servers the bot is in

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BOT_TOKEN` | ✅ | - | Discord bot token |
| `BOT_ID` | ✅ | - | Discord bot client ID |
| `COMMAND_PREFIX` | ❌ | `!` | Prefix for text commands |
| `TENOR_TOKEN` | ❌ | - | Tenor API key (only required for GIF search commands) |
| `SPOTIFY_CLIENT_ID` | ❌ | - | Spotify API client ID (for Spotify URL support) |
| `SPOTIFY_CLIENT_SECRET` | ❌ | - | Spotify API client secret (for Spotify URL support) |
| `PLAYLIST_MAX` | ❌ | 400 | Max tracks to enqueue from a playlist |
| `YTDL_MAX_WORKERS` | ❌ | 4 | Max concurrent yt-dlp workers |
| `DISCONNECT_TIMEOUT` | ❌ | 300 | Auto-disconnect timeout in seconds |
| `LOG_LEVEL` | ❌ | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `SELF_HOST` | ❌ | true | Set to `false` if cloud-hosting |

### Getting Spotify API Credentials

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/)
2. Create a new app
3. Copy the **Client ID** and **Client Secret**
4. Add them to your `.env` file

**Note:** Spotify support is optional. The bot works without it for YouTube-only playback.
