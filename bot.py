import asyncio
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

import discord
import yt_dlp
from dotenv import load_dotenv


load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("music-bot")

YOUTUBE_URL_PATTERN = re.compile(
    r"https?://(?:(?:www|m|music)\.)?youtube\.com/[^\s<>]+|"
    r"https?://youtu\.be/[^\s<>]+",
    re.IGNORECASE,
)
YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "error",
}
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


@dataclass
class Track:
    url: str
    requested_by: discord.abc.User


class MusicBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)

        self.text_channel_id = self._optional_id("TEXT_CHANNEL_ID")
        self.voice_channel_id = self._optional_id("VOICE_CHANNEL_ID")
        self.text_channel_name = os.getenv("TEXT_CHANNEL_NAME", "besties🤍✨")
        self.voice_channel_name = os.getenv("VOICE_CHANNEL_NAME", "Music")
        self.guild_id = self._optional_id("GUILD_ID")
        self.queues: dict[int, asyncio.Queue[Track]] = {}
        self.queue_workers: dict[int, asyncio.Task[None]] = {}
        self.play_history: dict[int, list[Track]] = {}
        self.play_history_index: dict[int, int] = {}
        self.previous_tracks: dict[int, Track] = {}
        self.current_tracks: dict[int, Track] = {}

    @staticmethod
    def _optional_id(variable: str) -> Optional[int]:
        value = os.getenv(variable)
        if not value:
            return None
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"{variable} must be a numeric Discord ID.") from exc

    async def on_ready(self) -> None:
        logger.info("Logged in as %s (ID: %s)", self.user, self.user.id if self.user else "?")

    def _find_text_channel(self, message: discord.Message) -> Optional[discord.TextChannel]:
        if not isinstance(message.channel, discord.TextChannel):
            return None
        if self.text_channel_id is not None:
            return message.channel if message.channel.id == self.text_channel_id else None
        if message.channel.name != self.text_channel_name:
            return None
        if self.guild_id is not None and message.guild_id != self.guild_id:
            return None
        return message.channel

    def _find_voice_channel(self, guild: discord.Guild) -> Optional[discord.VoiceChannel]:
        if self.voice_channel_id is not None:
            channel = guild.get_channel(self.voice_channel_id)
            return channel if isinstance(channel, discord.VoiceChannel) else None
        if self.guild_id is not None and guild.id != self.guild_id:
            return None
        return discord.utils.get(guild.voice_channels, name=self.voice_channel_name)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if not self._find_text_channel(message):
            return

        command = message.content.strip().lower()
        if command in {"!clear", "!skip", "!stop", "!start", "!previous"}:
            guild = message.guild
            if guild is None:
                return
            voice_client = guild.voice_client
            if command == "!clear":
                queue = self.queues.get(guild.id)
                if queue is not None:
                    while not queue.empty():
                        try:
                            queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                        else:
                            queue.task_done()

                if voice_client is not None and (
                    voice_client.is_playing() or voice_client.is_paused()
                ):
                    voice_client.stop()
                    await message.reply(
                        "Stopped the current track and cleared the queue. "
                        "Post a YouTube link to play something new."
                    )
                else:
                    await message.reply(
                        "Cleared the queue. Post a YouTube link to play something new."
                    )
                return

            if command == "!stop":
                if voice_client is not None and voice_client.is_playing():
                    voice_client.pause()
                    await message.reply("Paused playback. Send `!start` to continue.")
                elif voice_client is not None and voice_client.is_paused():
                    await message.reply("Playback is already paused. Send `!start` to continue.")
                else:
                    await message.reply("Nothing is playing to pause.")
                return

            if command == "!start":
                if voice_client is not None and voice_client.is_paused():
                    voice_client.resume()
                    await message.reply("Resumed playback.")
                elif voice_client is not None and voice_client.is_playing():
                    await message.reply("Playback is already running.")
                else:
                    await message.reply("There is no paused track to resume.")
                return

            if command == "!previous":
                history = self.play_history.get(guild.id, [])
                history_index = self.play_history_index.get(guild.id, -1)
                if (
                    voice_client is None
                    or not (voice_client.is_playing() or voice_client.is_paused())
                    or history_index <= 0
                ):
                    await message.reply("There is no previous track to play.")
                    return

                history_index -= 1
                self.play_history_index[guild.id] = history_index
                self.previous_tracks[guild.id] = history[history_index]
                voice_client.stop()
                await message.reply("Playing the previous track from the beginning.")
                return

            if voice_client is None or not (voice_client.is_playing() or voice_client.is_paused()):
                await message.reply("Nothing is playing to skip.")
            else:
                voice_client.stop()
                await message.reply("Skipped. Starting the next queued track, if there is one.")
            return

        match = YOUTUBE_URL_PATTERN.search(message.content)
        if not match:
            return
        if message.guild is None:
            return

        voice_channel = self._find_voice_channel(message.guild)
        if voice_channel is None:
            await message.reply(
                "I couldn't find the configured Music voice channel. Check the bot's channel settings."
            )
            return

        queue = self.queues.setdefault(message.guild.id, asyncio.Queue())
        await queue.put(Track(match.group(0).rstrip(".,!?"), message.author))
        position = queue.qsize()
        await message.add_reaction("🎵")

        worker = self.queue_workers.get(message.guild.id)
        if worker is None or worker.done():
            self.queue_workers[message.guild.id] = asyncio.create_task(
                self._play_queue(message.guild, voice_channel, message.channel, queue)
            )
        elif position > 1:
            await message.reply(f"Added to the music queue (position {position}).")

    async def _play_queue(
        self,
        guild: discord.Guild,
        voice_channel: discord.VoiceChannel,
        text_channel: discord.abc.Messageable,
        queue: asyncio.Queue[Track],
    ) -> None:
        try:
            while True:
                from_queue = guild.id not in self.previous_tracks
                if from_queue:
                    if queue.empty():
                        break
                    track = await queue.get()
                    history = self.play_history.setdefault(guild.id, [])
                    history_index = self.play_history_index.get(guild.id, -1)
                    del history[history_index + 1 :]
                    history.append(track)
                    self.play_history_index[guild.id] = len(history) - 1
                else:
                    track = self.previous_tracks.pop(guild.id)
                self.current_tracks[guild.id] = track
                try:
                    await self._play_track(guild, voice_channel, text_channel, track)
                except (
                    discord.DiscordException,
                    OSError,
                    ValueError,
                    yt_dlp.utils.DownloadError,
                ) as exc:
                    logger.exception("Unable to play requested track")
                    await text_channel.send(f"Couldn't play that YouTube link: {exc}")
                finally:
                    if from_queue:
                        queue.task_done()
                    if self.current_tracks.get(guild.id) is track:
                        self.current_tracks.pop(guild.id, None)
        finally:
            self.queue_workers.pop(guild.id, None)
            if not queue.empty():
                self.queue_workers[guild.id] = asyncio.create_task(
                    self._play_queue(guild, voice_channel, text_channel, queue)
                )

    async def _play_track(
        self,
        guild: discord.Guild,
        voice_channel: discord.VoiceChannel,
        text_channel: discord.abc.Messageable,
        track: Track,
    ) -> None:
        voice_client = guild.voice_client
        if voice_client is None:
            voice_client = await voice_channel.connect()
        elif voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)

        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, self._extract_audio, track.url)
        source = discord.FFmpegPCMAudio(info["url"], **FFMPEG_OPTIONS)
        finished = loop.create_future()

        def after_playback(error: Optional[Exception]) -> None:
            def finish() -> None:
                if finished.done():
                    return
                if error:
                    finished.set_exception(error)
                else:
                    finished.set_result(None)

            loop.call_soon_threadsafe(finish)

        voice_client.play(source, after=after_playback)
        title = discord.utils.escape_markdown(info.get("title", "YouTube video"))
        await text_channel.send(f"Now playing **{title}** (requested by {track.requested_by.mention}).")
        await finished

    @staticmethod
    def _extract_audio(url: str) -> dict[str, str]:
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as downloader:
            info = downloader.extract_info(url, download=False)
        audio_url = info.get("url")
        if not audio_url:
            raise ValueError("YouTube did not provide an audio stream.")
        return {"url": audio_url, "title": info.get("title", "YouTube video")}


def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Set DISCORD_TOKEN in your .env file before starting the bot.")
    MusicBot().run(token)


if __name__ == "__main__":
    main()
