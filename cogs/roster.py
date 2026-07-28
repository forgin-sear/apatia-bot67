# cogs/roster.py
import asyncio
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
    already_shown = set()  # id тех, кто уже попал в более старшую роль выше по списку
    counts = []  # (label, число человек с этой ролью) — для сводки внизу

    for role_key, label in ROSTER_ROLES:
        role_id = config.ROLE_IDS.get(role_key)
        role = guild.get_role(role_id) if role_id else None
        if not role:
            embed.add_field(name=label, value="_роль не найдена, проверь config.py_", inline=False)
            continue

        # role.members читается из локального кэша участников бота.
        # В bot.py уже включён intents.members, так что кэш должен быть полным.
        all_members = [m for m in role.members if not m.bot]
        counts.append((label, len(all_members)))

        if role_key == "APATIA":
            # Apatia — это "все члены семьи", сюда вписываем ВСЕХ с этой ролью,
            # независимо от того, что они уже показаны выше как Leader/High/и т.д.
            members = all_members
        else:
            # Остальные роли: показываем человека только в самой старшей его роли —
            # если он уже "засветился" выше по списку (роль повыше), тут его не дублируем.
            members = [m for m in all_members if m.id not in already_shown]
            already_shown.update(m.id for m in all_members)

        if not members:
            value = "_пусто_"
        else:
            found_any = True
            value = "\n".join(f"{i + 1}. {m.mention}" for i, m in enumerate(members))
            if len(value) > 1024:
                value = value[:1000] + "\n… (список обрезан, слишком много участников)"

        embed.add_field(name=label, value=value, inline=False)

    if not found_any:
        embed.description = "⚠️ Ни в одной из отслеживаемых ролей пока никого нет (или роли не настроены)."

    # Сводка по количеству — в самом низу таблицы
    summary_lines = [f"{label}: **{count}**" for label, count in counts]
    embed.add_field(name="🔢 Количество игроков в фаме по ролям", value="\n".join(summary_lines) or "_нет данных_", inline=False)

    embed.set_footer(text="Обновляется автоматически при изменении ролей")
    embed.timestamp = discord.utils.utcnow()
    return embed


def build_new_members_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="🆕 Новички без роли (только New)",
        description=(
            "Люди на сервере, у которых до сих пор только роль **New** — значит, "
            "они ещё не подали заявку или заявка не рассмотрена. Отсортировано "
            "от самых \"старых\" (кто дольше всех висит без движения)."
        ),
        color=discord.Color.blue()
    )

    role_id = config.ROLE_IDS.get("NEW")
    role = guild.get_role(role_id) if role_id else None
    if not role:
        embed.description = "⚠️ Роль NEW не найдена, проверь config.py."
        return embed

    members = [m for m in role.members if not m.bot]
    # Сортируем по дате входа на сервер — кто дольше всех без движения, тот наверху
    members.sort(key=lambda m: m.joined_at or discord.utils.utcnow())

    if not members:
        embed.add_field(name="Список", value="_Сейчас таких нет — все либо подали заявку, либо уже в семье._", inline=False)
    else:
        now = discord.utils.utcnow()
        lines = []
        for m in members:
            if m.joined_at:
                days = (now - m.joined_at).days
                days_text = f"{days} дн." if days > 0 else "меньше дня"
            else:
                days_text = "неизвестно"
            lines.append(f"• {m.mention} — на сервере: **{days_text}**")

        value = "\n".join(lines)
        if len(value) > 1024:
            value = value[:1000] + "\n… (список обрезан, слишком много участников)"
        embed.add_field(name=f"Список ({len(members)})", value=value, inline=False)

    embed.set_footer(text="Обновляется автоматически при входе/выходе и изменении ролей")
    embed.timestamp = discord.utils.utcnow()
    return embed


class RosterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.message_id = None      # id сообщения-таблицы состава (сбрасывается при рестарте)
        self.new_board_message_id = None  # id сообщения-доски новичков (сбрасывается при рестарте)

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

    async def refresh_new_board(self, guild: discord.Guild):
        channel_id = config.CHANNEL_IDS.get("NEW_BOARD")
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if not channel:
            return

        embed = build_new_members_embed(guild)

        if self.new_board_message_id:
            try:
                msg = await channel.fetch_message(self.new_board_message_id)
                await msg.edit(embed=embed)
                return
            except Exception:
                pass

        msg = await channel.send(embed=embed)
        self.new_board_message_id = msg.id

    @discord.app_commands.command(
        name="setup_new_board",
        description="Создать/обновить доску 'новички без роли' для рекрутов в канале NEW_BOARD"
    )
    async def setup_new_board(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.refresh_new_board(interaction.guild)
        await temp_reply(interaction, "✅ Доска новичков создана/обновлена!")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # Новый участник почти сразу получает роль New (см. welcome.py) —
        # обновим доску с небольшой задержкой, чтобы роль успела примениться.
        await asyncio.sleep(3)
        await self.refresh_new_board(member.guild)

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
        # Обновляем таблицы только если реально поменялись роли
        # (а не ник/статус/и т.п. — иначе будет дёргать API почём зря)
        if before.roles == after.roles:
            return

        before_ids = {r.id for r in before.roles}
        after_ids = {r.id for r in after.roles}
        changed_ids = before_ids ^ after_ids

        tracked_ids = {config.ROLE_IDS.get(key) for key, _ in ROSTER_ROLES}
        if changed_ids & tracked_ids:
            await self.refresh_roster(after.guild)

        new_role_id = config.ROLE_IDS.get("NEW")
        if new_role_id and new_role_id in changed_ids:
            await self.refresh_new_board(after.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # Если ушедший был в одной из отслеживаемых ролей — обновим соответствующую таблицу
        member_role_ids = {r.id for r in member.roles}

        tracked_ids = {config.ROLE_IDS.get(key) for key, _ in ROSTER_ROLES}
        if member_role_ids & tracked_ids:
            await self.refresh_roster(member.guild)

        new_role_id = config.ROLE_IDS.get("NEW")
        if new_role_id and new_role_id in member_role_ids:
            await self.refresh_new_board(member.guild)


async def setup(bot):
    await bot.add_cog(RosterCog(bot))
