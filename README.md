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
* **Lightweight queueing** — metadata-only enqueuing for large playlists, and the next track loads while the current one plays
* **Docker support** — deployment with Docker Compose

## Discord Setup

1. **Create an app** in the [Discord Developer Portal](https://discord.com/developers/applications) and copy the bot token from its **Bot** page
2. **Enable the Server Members and Message Content intents** on the same page, the bot doesn't start without them
3. **Add the bot to your server** with an invite link from **OAuth2 → URL Generator**: scopes `bot` and `applications.commands`, permission **Administrator**

## Local Setup

### Requirements

* [Python 3.13+](https://www.python.org/downloads/) (the Docker image uses 3.15)
* [FFmpeg](https://ffmpeg.org/download.html) executable in PATH

### Installation

1. **Clone/download** this repository
2. **Create a `.env` file** in the root directory:
   ```
   BOT_TOKEN=your_bot_token_here
   ```
3. **Install dependencies**
   ```sh
   pip install -r requirements.txt
   ```
4. **Start the bot**
   ```sh
   python main.py
   ```

## Docker Setup

Requires [Docker](https://www.docker.com/) with Compose.

1. **Clone/download** this repository
2. **Create a `.env` file** in the root directory:
   ```
   BOT_TOKEN=your_bot_token_here
   COMMAND_PREFIX=!
   PLAYLIST_MAX=400
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

## Development

```sh
pip install -r requirements-dev.txt
ruff check .
ruff format .
pytest
```

The tests replace Discord, yt-dlp, FFmpeg and Spotify with fakes, so they run offline. Playback, voice and slash command behavior still need a manual check on a test server.

CI runs lint, tests and a Docker build on every pull request and push to `main`. Dependencies, the Docker base image and the CI actions are pinned and kept current by Renovate. Merge yt-dlp updates promptly, since YouTube changes regularly break older versions.

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

* `/help [command]` or `!help [command]` — List all commands, or show details for one
* `/ping` or `!ping` — Show bot latency
* `/hello` or `!hello` / `!hi` / `!hey` — Greet the bot
* `/about` or `!about` / `!info` / `!stats` — Bot information
* `/decide <question>` or `!decide <question>` — Get a yes/no answer
* `/hug [user]` or `!hug [username]` — Send a hug GIF
* `/slap [user] [reason]` or `!slap [username] [reason]` / `!punch` / `!hit` — Send a slap GIF
* `/poke <user> [reason]` or `!poke <username> [reason]` / `!tap` — Send a poke GIF
* `/coinflip` or `!coinflip` / `!flip` / `!coin` — Flip a coin (German)
* `/fliflaflu` or `!fliflaflu` / `!enemenemiste` / `!schnickschnackschnuck` — Rock-paper-scissors (German)
* `/roulette <options>` or `!roulette <option1 option2 ...>` / `!select` / `!choice` — Select a random option
* `/gif <search>` or `!gif <search>` — Fetch a random GIF from Tenor
* `/lolcoinflip [username]` or `!lolcoinflip` / `!lolflip` / `!lolcoin` — LoL-themed coin flip (German)

### Admin (Owner Only)

* `/shutdown` or `!shutdown` / `!s` / `!sleep` — Shut down the bot
* `/invite` or `!invite` — Get the bot's invite link
* `/servers` or `!servers` — List all servers the bot is in

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BOT_TOKEN` | ✅ | - | Discord bot token |
| `COMMAND_PREFIX` | ❌ | `!` | Prefix for text commands |
| `TENOR_TOKEN` | ❌ | - | Tenor API key for GIF search in `/gif`, `/slap` and `/poke`, which use built-in GIFs without it |
| `SPOTIFY_CLIENT_ID` | ❌ | - | Spotify API client ID (for Spotify URL support) |
| `SPOTIFY_CLIENT_SECRET` | ❌ | - | Spotify API client secret (for Spotify URL support) |
| `PLAYLIST_MAX` | ❌ | 400 | Max tracks to enqueue from a playlist |
| `YTDL_MAX_WORKERS` | ❌ | 4 | Max concurrent yt-dlp workers |
| `DISCONNECT_TIMEOUT` | ❌ | 300 | Seconds to stay in voice after the queue ends |
| `LOG_LEVEL` | ❌ | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |

### Getting Spotify API Credentials

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/)
2. Create a new app
3. Copy the **Client ID** and **Client Secret**
4. Add them to your `.env` file

**Note:** Spotify support is optional. The bot works without it for YouTube-only playback.
