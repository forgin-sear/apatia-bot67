# cogs/welcome.py
import os
import discord
from discord.ext import commands
import config


def build_welcome_files(member: discord.Member):
    """
    Возвращает (embed, files) для карточки приветствия.
    Картинка баннера берётся ЛОКАЛЬНО из config.WELCOME_BANNER_FILE,
    поэтому больше не будет битой ссылки imgur.
    """
    embed = discord.Embed(
        title="🥀 WELCOME TO APATIA FAMILY",
        description=(
            f"Рады видеть тебя у нас, {member.mention}! 🥀\n\n"
            f"📌 **Куда двигаться дальше:**\n"
            f"• Загляни в правила — там всё по делу и без воды.\n"
            f"• Оставь анкету в канале заявок, чтобы попасть в состав семьи.\n"
            f"• Не стесняйся, залетай в общий чат знакомиться!\n"
        ),
        color=discord.Color.from_rgb(139, 0, 0)
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text="APATIA FAMILY • All rights reserved")

    files = []
    banner_path = config.WELCOME_BANNER_FILE
    if os.path.isfile(banner_path):
        filename = os.path.basename(banner_path)
        file = discord.File(banner_path, filename=filename)
        embed.set_image(url=f"attachment://{filename}")
        files.append(file)
    else:
        # Файла нет — просто не показываем картинку, но бот не падает
        print(f"⚠️ Баннер приветствия не найден: {banner_path}. "
              f"Положи картинку по этому пути, чтобы она отображалась.")

    return embed, files


class WelcomeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # 1. Автоматическая выдача роли New
        role_id = config.ROLE_IDS.get("NEW")
        if role_id:
            role = member.guild.get_role(role_id)
            if role:
                try:
                    await member.add_roles(role)
                except Exception as e:
                    print(f"Ошибка при выдаче роли новичку: {e}")

        # 2. Отправка карточки приветствия
        channel_id = config.CHANNEL_IDS.get("WELCOME")
        if channel_id:
            channel = member.guild.get_channel(channel_id)
            if channel:
                embed, files = build_welcome_files(member)
                await channel.send(content=f"Добро пожаловать, {member.mention}!", embed=embed, files=files)


async def setup(bot):
    await bot.add_cog(WelcomeCog(bot))