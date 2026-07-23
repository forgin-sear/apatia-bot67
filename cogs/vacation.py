# cogs/vacation.py
import os
import discord
from discord.ext import commands
import config
from .utils import temp_reply


def build_vacation_embed(guild: discord.Guild):
    embed = discord.Embed(
        title="🏖️ Заявка на отпуск",
        description=(
            "Привет! Здесь можно оставить заявку на отпуск.\n\n"
            "❗ Отпуск берётся не на пару часов — если нужно отойти ненадолго, "
            "для этого есть канал **АФК**.\n\n"
            "📋 **Формат заявки:**\n"
            "Отпуск с **[число.месяц]** по **[число.месяц]**"
        ),
        color=discord.Color.dark_red()
    )

    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    files = []
    path = config.WELCOME_BANNER_FILE
    if os.path.isfile(path):
        filename = os.path.basename(path)
        f = discord.File(path, filename=filename)
        embed.set_image(url=f"attachment://{filename}")
        files.append(f)

    return embed, files


class VacationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(
        name="setup_vacation_info",
        description="Установить инфо-карточку в канале заявок на отпуск"
    )
    async def setup_vacation_info(self, interaction: discord.Interaction):
        embed, files = build_vacation_embed(interaction.guild)
        await interaction.channel.send(embed=embed, files=files)
        await temp_reply(interaction, "Карточка с инфо об отпуске установлена!")


async def setup(bot):
    await bot.add_cog(VacationCog(bot))
