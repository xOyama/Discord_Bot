import discord
from discord.ext import commands
from discord import app_commands
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GUILD = os.getenv("GUILD")


class SyncCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="sync", description="Manually sync application commands (Admin only)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def sync(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            guild_id = os.getenv("GUILD")

            if guild_id:
                guild = discord.Object(id=int(guild_id))
                await self.bot.tree.sync(guild=guild)
                logger.info(f"Successfully synced commands to guild {guild_id}")
                await interaction.followup.send(
                    f"✅ Commands synced to guild {guild_id}",
                    ephemeral=True,
                )
            else:
                await self.bot.tree.sync()
                logger.info("Successfully synced global commands")
                await interaction.followup.send(
                    "✅ Commands synced globally", ephemeral=True
                )

        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")
            await interaction.followup.send(f"❌ Sync failed: {str(e)}", ephemeral=True)

    @sync.error
    async def sync_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.followup.send(
                "❌ You need administrator permissions to use this command.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"❌ An error occurred: {str(error)}", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(SyncCog(bot))
