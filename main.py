import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv
import logging
import random

load_dotenv()

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

from music import Music
from youtube_notifications import check_for_new_videos
from rust_integration import (
    rust_socket,
    track_player_inactivity,
    handle_afk_message_command,
)
from twitter_handler import handle_twitter_links
from tools import SyncCog
from liga import (
    check_and_post_game_stats,
    get_last_games_embed,
    get_summoner_puuid,
    SUMMONER_NAME,
    REGION,
    RIOT_API_KEY,
    RIOT_TAGLINE,
    MAX_GAMES,
)

TOKEN = os.getenv("MAIDEN")
GUILD = os.getenv("GUILD")
GUID2 = os.getenv("GUILD2")


class CustomBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=discord.Intents.all(),
            application_id=int(os.getenv("APPLICATION_ID")),
        )

    async def setup_hook(self):
        try:
            await self.add_cog(Music(self))
            await self.add_cog(SyncCog(self))
            guild_id = os.getenv("GUILD")
            if guild_id:
                guild = discord.Object(id=int(guild_id))
                await self.tree.sync(guild=guild)
                logging.info("Successfully synced application commands to guild")
            else:
                await self.tree.sync()
                logging.info("Successfully synced global application commands")
        except Exception as e:
            logging.error(f"Failed to sync application commands: {e}")


client = CustomBot()

@client.tree.command(name="yap", description="Join your voice channel")
async def yap(interaction: discord.Interaction):
    logging.info(f"Yap command triggered by {interaction.user}")
    logging.info(f"Guild ID: {interaction.guild_id}")
    logging.info(f"Application ID: {client.application_id}")

    await interaction.response.defer(ephemeral=True)

    if not interaction.user.voice:
        await interaction.followup.send(
            "You need to be in a voice channel first!", ephemeral=True
        )
        return

    voice_channel = interaction.user.voice.channel

    try:
        if interaction.guild.voice_client:
            if interaction.guild.voice_client.channel == voice_channel:
                await interaction.followup.send(
                    f"I'm already in {voice_channel.name}!", ephemeral=True
                )
                return
            await interaction.guild.voice_client.disconnect()

        await voice_channel.connect()

        await interaction.followup.send(
            f"Connected to {voice_channel.name}!", ephemeral=True
        )

    except discord.errors.ClientException as ce:
        await interaction.followup.send(
            f"Voice client error: {str(ce)}", ephemeral=True
        )
        logging.error(f"Voice client error in yap command: {str(ce)}")
    except Exception as e:
        await interaction.followup.send(
            f"An error occurred while connecting: {str(e)}", ephemeral=True
        )
        logging.error(f"Error in yap command: {str(e)}")


@client.tree.command(name="ick", description="Disconnect bot from voice channel")
async def ick(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        if not interaction.guild.voice_client:
            await interaction.followup.send(
                "I'm not in a voice channel!", ephemeral=True
            )
            return
        channel_name = interaction.guild.voice_client.channel.name

        await interaction.guild.voice_client.disconnect()

        await interaction.followup.send(
            f"Disconnected from {channel_name}!", ephemeral=True
        )

    except Exception as e:
        logging.error(f"Error in ick command: {str(e)}")
        await interaction.followup.send(
            "An error occurred while disconnecting.", ephemeral=True
        )


@client.tree.command(name="time", description="Get current Rust server time")
async def time(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        rust_time = (await rust_socket.get_time()).time
        message = f"🕒 Current Rust server time: {rust_time}"

        channel = client.get_channel(int(os.getenv("DISCORD_CHANNEL_ID5")))
        await channel.send(message)

        await rust_socket.send_team_message(message)

        await interaction.followup.send("✅ Time updated!", ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)


@client.tree.command(
    name="last",
    description=f"Get the last n games of the tracked summoner (max {MAX_GAMES})",
)
@app_commands.describe(n="Number of games to show (1-10)")
async def last(interaction: discord.Interaction, n: app_commands.Range[int, 1, 10]):
    await interaction.response.defer()

    puuid = await get_summoner_puuid(SUMMONER_NAME, RIOT_TAGLINE, RIOT_API_KEY)
    if not puuid:
        await interaction.followup.send("Unable to fetch summoner data.")
        return

    embed = await get_last_games_embed(puuid, n, REGION, RIOT_API_KEY)
    if embed:
        await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send("No game data available or API error occurred.")


@client.event
async def on_ready():
    target_steam_id = os.getenv("TARGET_STEAM_ID")
    if target_steam_id:
        client.loop.create_task(
            track_player_inactivity(int(target_steam_id), client)
        )
    else:
        logging.warning("TARGET_STEAM_ID not set, skipping player inactivity tracking")
    client.loop.create_task(check_lol_stats_loop(client))
    print(f"Successfully logged in as {client.user}!")
    await client.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching, name="You from above"
        )
    )
    check_for_new_videos.start(client)


async def check_lol_stats_loop(client):
    import asyncio

    while True:
        try:
            await check_and_post_game_stats(client)
        except Exception as e:
            logger.error(f"Error in LoL stats check loop: {e}")
        await asyncio.sleep(120)


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    content_lower = message.content.lower()
    if "twitter.com" in content_lower or "x.com" in content_lower:
        await handle_twitter_links(message)
        return

    if message.content.lower() == "wanda":
        responses = [
            "Pafi",
            "Lafi",
        ]
        chosen_response = random.choice(responses)
        await message.channel.send(chosen_response)

    if message.content.lower() == "panda":
        responses = [
            "Tafi",
            "Lafi",
            "PANDA",
            "panda",
            "Panda Panda",
            "GRRRRRA",
        ]
        chosen_response = random.choice(responses)
        await message.channel.send(chosen_response)

    responses = {
        "sminema": "specheli",
        "sminem": "Eminem",
        "eminem": "Sminem",
        "сминем": "Bounjour boy Eminem",
        "wanda pafi": "Натисни го бе!",
    }

    content_lower = message.content.lower()
    if content_lower in responses:
        await message.channel.send(responses[content_lower])
        return

    if message.content.lower() == "!afk":
        await handle_afk_message_command(message)
        return


client.run(TOKEN)
