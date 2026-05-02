import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import functools
from typing import Optional
import yt_dlp

YTDLP_OPTIONS = {
	'format': 'bestaudio/best',
	'extractaudio': True,
    'extract_flat': False,
	'audioformat': 'mp3',
	'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
	'restrictfilenames': True,
	'noplaylist': True,
	'nocheckcertificate': True,
	'ignoreerrors': False,
	'logtostderr': True,
	'quiet': True,
	'no_warnings': False,
	'default_search': 'auto',
	'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
	'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
	'options': '-vn',
}

class YTDLSource(discord.PCMVolumeTransformer):
	def __init__(self, source: discord.AudioSource, *, data: dict, volume: float = 0.5):
		super().__init__(source, volume)
		self.data = data
		self.title = data.get('title')
		self.url = data.get('url')
		self.duration = data.get('duration')
		self.webpage_url = data.get('webpage_url')

	@classmethod
	async def from_url(cls, url: str, *, loop=None):
		loop = loop or asyncio.get_event_loop()
		ytdl = yt_dlp.YoutubeDL(YTDLP_OPTIONS)

		try:
			partial = functools.partial(ytdl.extract_info, url, download=False)
			data = await loop.run_in_executor(None, partial)

			if 'entries' in data:
				data = data['entries'][0]

			return cls(
				discord.FFmpegPCMAudio(
					data['url'],
					**FFMPEG_OPTIONS
				),
				data=data
			)
		except Exception as e:
			print(f'Error processing YouTube URL: {e}')
			return None

class MusicPlayer:

	def __init__(self, interaction: discord.Interaction):
		self.bot = interaction.client
		self.guild = interaction.guild
		self.text_channel = interaction.channel
		self.queue = asyncio.Queue()
		self.next = asyncio.Event()
		self.current = None
		self.volume = 1
		self._loop = False
		self.current_url = None

		self.audio_player = self.bot.loop.create_task(self.player_loop())

	async def player_loop(self):
		await self.bot.wait_until_ready()

		while not self.bot.is_closed:
			self.next.clear()

			try:
				async with asyncio.timeout(180):
					if not self._loop:
						source = await self.queue.get()
						self.current_url = source.webpage_url
					else:
						if self.current_url:
							source = await YTDLSource.from_url(self.current_url, loop=self.bot.loop)
							if not source:
								self._loop = False
								continue
						else:
							self._loop = False
							continue
			except asyncio.TimeoutError:
				if self.guild.voice_client:
					await self.guild.voice_client.disconnect()
				return

			if not self.guild.voice_client:
				return

			self.current = source
			self.guild.voice_client.play(
				source,
				after=lambda _: self.bot.loop.call_soon_threadsafe(self.next.set)
			)

			if not self._loop:
				await self.text_channel.send(f'🎵 Now playing: {self.current.title}')

			await self.next.wait()
			source.cleanup()

			if not self._loop:
				self.current = None
				self.current_url = None

class Music(commands.Cog):
	def __init__(self, bot):
		self.bot = bot
		self.players = {}

	def get_player(self, interaction: discord.Interaction):
		if interaction.guild_id not in self.players:
			self.players[interaction.guild_id] = MusicPlayer(interaction)
		return self.players[interaction.guild_id]

	@app_commands.command(name="play", description="Play audio from a YouTube URL")
	async def play(self, interaction: discord.Interaction, url: str):
		await interaction.response.defer()

		if not interaction.user.voice:
			await interaction.followup.send(
				"You need to be in a voice channel to play music!",
				ephemeral=True
			)
			return

		voice_client = interaction.guild.voice_client
		if not voice_client:
			try:
				voice_client = await interaction.user.voice.channel.connect()
			except Exception as e:
				await interaction.followup.send(
					f"Could not connect to voice channel: {e}",
					ephemeral=True
				)
				return

		player = self.get_player(interaction)

		try:
			source = await YTDLSource.from_url(url, loop=self.bot.loop)
			if not source:
				await interaction.followup.send(
					"Could not process that YouTube URL",
					ephemeral=True
				)
				return

			await player.queue.put(source)
			await interaction.followup.send(f'🎵 Added to queue: {source.title}')

		except Exception as e:
			await interaction.followup.send(
				f"An error occurred: {str(e)}",
				ephemeral=True
			)

	@app_commands.command(name="stop", description="Stop playing and clear the queue")
	async def stop(self, interaction: discord.Interaction):
		await interaction.response.defer()

		if not interaction.guild.voice_client:
			await interaction.followup.send("I'm not playing anything right now!")
			return

		voice_client = interaction.guild.voice_client

		try:
			if interaction.guild_id in self.players:
				player = self.players[interaction.guild_id]

				while not player.queue.empty():
					try:
						await player.queue.get_nowait()
					except asyncio.QueueEmpty:
						break

			if voice_client.is_playing():
				voice_client.stop()

			await interaction.followup.send("🛑 Stopped playing and cleared the queue")

		except Exception as error:
			import logging
			logging.error(f"Error in stop command: {error}")
			await interaction.followup.send(
				f"An error occurred while stopping: {str(error)}",
				ephemeral=True
			)

	@app_commands.command(name="skip", description="Skip the current song")
	async def skip(self, interaction: discord.Interaction):
		if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
			interaction.guild.voice_client.stop()
			await interaction.response.send_message("⏭️ Skipped the current song")
		else:
			await interaction.response.send_message("No song is currently playing")

	@app_commands.command(name="loop", description="Toggle loop mode")
	async def loop(self, interaction: discord.Interaction):
		if interaction.guild_id in self.players:
			player = self.players[interaction.guild_id]
			player._loop = not player._loop
			await interaction.response.send_message(
				f"🔄 Loop mode: {'enabled' if player._loop else 'disabled'}"
			)
		else:
			await interaction.response.send_message("No music player active")
