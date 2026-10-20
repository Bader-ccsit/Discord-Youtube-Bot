# YouTube voice music bot

This bot watches the configured Discord text channel for a YouTube video link,
then queues its audio in the configured voice channel. It does not download or
save the video.

## Requirements

- Python 3.10 or newer
- FFmpeg installed and available on `PATH`
- A Discord application/bot with permission to view the text channel, read
  messages, send messages, connect to voice, and speak

## Setup

1. Create a bot in the [Discord Developer Portal](https://discord.com/developers/applications),
   invite it to your server with the permissions above, and enable **Message
   Content Intent** under **Bot → Privileged Gateway Intents**.
2. Install FFmpeg and make sure `ffmpeg` works from a new terminal.
3. Create a virtual environment and install the Python dependencies:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   py -m pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env`, then set `DISCORD_TOKEN` to your bot token.
   Keep the token private and never commit `.env`. The example includes the
   server and channel IDs; update them if you use a different server. If you
   leave channel IDs blank, the bot uses `TEXT_CHANNEL_NAME` and
   `VOICE_CHANNEL_NAME` instead.
5. Start the bot:

   ```powershell
   py bot.py
   ```

To enable the repository's local secret checks after cloning, run
`git config core.hooksPath .githooks`. The checks reject common token and
private-key patterns in staged changes and commits being pushed. Keep `.env`
and `pass.txt` out of Git; hooks are an extra safeguard, not a substitute for
rotating a credential that has been exposed.

Paste a YouTube video link in the configured text channel. The bot queues links
in the order received and plays them in the configured voice channel. Keep the
bot process running while you use it.

In the configured text channel, send `!stop` to pause playback (`!start` resumes
the same track), `!skip` to advance to the next queued link, or `!previous` to
play the previous track from its beginning. Send `!clear` to stop the current
track and remove queued tracks; the next YouTube link you post will play next.
Pausing keeps the queue intact.

## Notes

- If the bot does not see messages, verify **Message Content Intent** is enabled
  both in the Developer Portal and in the code's Discord intents.
- The bot must be able to connect and speak in the `Music` voice channel.
- Use a video URL rather than a playlist URL; playback is limited to one video
  per submitted link.
