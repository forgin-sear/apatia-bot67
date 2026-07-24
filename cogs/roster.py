# cogs/roster.py
import discord
from discord.ext import commands
import config
from .utils import temp_reply

# Порядок ролей в таблице состава и как их подписывать.
# NEW и AWAITING_RULES сюда сознательно НЕ включены — это временные роли,
# а не "полноценный состав семьи".
ROSTER_ROLES = [
    ("LEADER", "👑 Leader"),
    ("OWNER", "🔱 Owner"),
    ("DEP_OWN", "🎖️ Dep.Own"),
    ("HIGH", "⭐ High"),
    ("MAIN_PLUS", "🔸 Main+"),
    ("MAIN", "🔹 Main"),
    ("RECRUITER", "🧭 Recruiter"),
    ("APATIA", "🥀 Apatia"),
]


def build_roster_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="📖 Состав семьи APATIA",
        color=discord.Color.dark_red()
    )

    found_any = False
    for role_key, label in ROSTER_ROLES:
        role_id = config.ROLE_IDS.get(role_key)
        role = guild.get_role(role_id) if role_id else None
        if not role:
            # Роль не настроена/не найдена — просто пропускаем, но не молчим совсем
            embed.add_field(name=label, value="_роль не найдена, проверь config.py_", inline=False)
            continue

        # role.members читается из локального кэша участников бота.
        # В bot.py уже включён intents.members, так что кэш должен быть полным.
        members = [m for m in role.members if not m.bot]
        if not members:
            value = "_пусто_"
        else:
            found_any = True
            value = "\n".join(f"{i + 1}. {m.mention}" for i, m in enumerate(members))
            # Дискорд режет значение поля на 1024 символа — на большой список подстрахуемся
            if len(value) > 1024:
                value = value[:1000] + "\n… (список обрезан, слишком много участников)"

        embed.add_field(name=label, value=value, inline=False)

    if not found_any:
        embed.description = "⚠️ Ни в одной из отслеживаемых ролей пока никого нет (или роли не настроены)."

    embed.set_footer(text="Обновляется автоматически при изменении ролей")
    embed.timestamp = discord.utils.utcnow()
    return embed


class RosterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.message_id = None  # id сообщения-таблицы (сбрасывается при рестарте бота)

    async def refresh_roster(self, guild: discord.Guild):
        channel_id = config.CHANNEL_IDS.get("ROSTER")
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if not channel:
            return

        embed = build_roster_embed(guild)

        if self.message_id:
            try:
                msg = await channel.fetch_message(self.message_id)
                await msg.edit(embed=embed)
                return
            except Exception:
                pass  # сообщение удалили/не нашли — создадим новое ниже

        msg = await channel.send(embed=embed)
        self.message_id = msg.id

    @discord.app_commands.command(
        name="setup_roster",
        description="Создать/обновить таблицу состава семьи по ролям в канале ROSTER"
    )
    async def setup_roster(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.refresh_roster(interaction.guild)
        await temp_reply(interaction, "✅ Таблица состава создана/обновлена!")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Обновляем таблицу только если реально поменялись роли
        # (а не ник/статус/и т.п. — иначе будет дёргать API почём зря)
        if before.roles == after.roles:
            return
        tracked_ids = {config.ROLE_IDS.get(key) for key, _ in ROSTER_ROLES}
        changed_ids = {r.id for r in before.roles} ^ {r.id for r in after.roles}
        if changed_ids & tracked_ids:
            await self.refresh_roster(after.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # Если ушедший был в одной из отслеживаемых ролей — тоже обновим таблицу
        tracked_ids = {config.ROLE_IDS.get(key) for key, _ in ROSTER_ROLES}
        if {r.id for r in member.roles} & tracked_ids:
            await self.refresh_roster(member.guild)


async def setup(bot):
    await bot.add_cog(RosterCog(bot))
