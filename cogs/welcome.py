# cogs/welcome.py
import discord
from discord.ext import commands
import config

# Ссылка на баннер семьи (можешь заменить на свою прямую ссылку)
FAMILY_BANNER_URL = "https://i.imgur.com/2XyZ8xQ.png" 

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
                embed = discord.Embed(
                    title="🥀 WELCOME TO APATIA FAMILY",
                    description=(
                        f"Приветствуем тебя на сервере, {member.mention}!\n\n"
                        f"📌 **С чего начать?**\n"
                        f"• Ознакомься с правилами нашего сервера.\n"
                        f"• Заполни анкету в канале заявок, чтобы попасть в состав.\n"
                        f"• Присоединяйся к общению в общем чате!\n"
                    ),
                    color=discord.Color.from_rgb(139, 0, 0)
                )
                
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_image(url=FAMILY_BANNER_URL)
                embed.set_footer(text="APATIA FAMILY • All rights reserved")

                await channel.send(content=f"Добро пожаловать, {member.mention}!", embed=embed)

async def setup(bot):
    await bot.add_cog(WelcomeCog(bot))