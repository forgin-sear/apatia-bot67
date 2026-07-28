# cogs/applications.py
"""
ВАЖНОЕ ПРО АРХИТЕКТУРУ ЭТОГО ФАЙЛА:

Раньше кнопки заявок (Взять/Принять/Отклонить/направления/решения в ветках)
были реализованы как discord.ui.View с decorator-колбэками, а нужные данные
(ID кандидата, кто взял заявку в работу и т.д.) хранились в Python-словаре
в памяти бота (cog.applications).

Проблема: после КАЖДОГО переподключения/рестарта бота (сон на Render,
краш, редеплой) эти Python-объекты и словарь исчезают. Кнопка в Discord
при этом остаётся видимой (она хранится на стороне Discord), но бот
её больше "не узнаёт" — и любое нажатие превращается в вечное
"Приложение не отвечает".

Решение: все нужные данные закодированы прямо в custom_id кнопок
(ID кандидата, ID исходного сообщения) и в footer embed'а (кто взял
заявку в работу, кто отвечает за ветку). Обработка идёт через общий
слушатель on_interaction, который каждый раз читает состояние заново
из самого сообщения — а не из памяти. Поэтому кнопки работают ВСЕГДА,
даже если бот только что перезапустился.
"""
import os
import re
from datetime import timedelta
import discord
from discord.ext import commands
import config
from .utils import temp_reply, temp_edit_original


def has_recruiter_access(member: discord.Member) -> bool:
    ids = {config.ROLE_IDS.get("RECRUITER"), config.ROLE_IDS.get("HIGH")}
    return any(r.id in ids for r in member.roles)


def build_panel_embed_files():
    embed = discord.Embed(
        title="🥀 Вступление в семью APATIA",
        description=config.APPLICATION_INFO_TEXT,
        color=discord.Color.dark_red()
    )
    files = []
    path = config.APPLICATION_BANNER_FILE
    if os.path.isfile(path):
        filename = os.path.basename(path)
        f = discord.File(path, filename=filename)
        embed.set_image(url=f"attachment://{filename}")
        files.append(f)
    else:
        print(f"⚠️ Баннер панели заявок не найден: {path}. Положи картинку по этому пути.")
    return embed, files


# ==========================================
#   ЧТЕНИЕ СОСТОЯНИЯ ПРЯМО ИЗ EMBED'А СООБЩЕНИЯ
# ==========================================

def extract_field(embed: discord.Embed, name: str) -> str:
    for field in embed.fields:
        if field.name == name:
            return field.value
    return ""


def extract_applicant_id(embed: discord.Embed):
    value = extract_field(embed, "Кандидат")
    m = re.search(r"\d+", value)
    return int(m.group()) if m else None


def extract_claimed_by(embed: discord.Embed):
    if not embed.footer or not embed.footer.text:
        return None
    m = re.search(r"claimed:(\d+)", embed.footer.text)
    return int(m.group(1)) if m else None


def extract_thread_meta(embed: discord.Embed):
    """Возвращает (responsible_id, orig_message_id) из footer сообщения в ветке."""
    if not embed.footer or not embed.footer.text:
        return None, None
    text = embed.footer.text
    r = re.search(r"responsible:(\d+)", text)
    o = re.search(r"orig:(\d+)", text)
    responsible_id = int(r.group(1)) if r else None
    orig_id = int(o.group(1)) if (o and o.group(1) != "0") else None
    return responsible_id, orig_id


# ==========================================
#   СБОРКА VIEW (только визуал, БЕЗ python-колбэков —
#   вся логика обрабатывается в ApplicationsCog.on_interaction)
# ==========================================

def build_new_application_view(applicant_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="🔍 Взять на рассмотрение", style=discord.ButtonStyle.primary,
                                     custom_id=f"app_claim:{applicant_id}"))
    view.add_item(discord.ui.Button(label="✅ Принять", style=discord.ButtonStyle.success,
                                     custom_id=f"app_accept:{applicant_id}"))
    view.add_item(discord.ui.Button(label="❌ Отклонить", style=discord.ButtonStyle.danger,
                                     custom_id=f"app_decline:{applicant_id}"))
    view.add_item(discord.ui.Button(label="📞 На обзвон", style=discord.ButtonStyle.secondary,
                                     custom_id=f"app_call:{applicant_id}"))
    return view


def build_direction_view(applicant_id: int, orig_message_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=180)
    view.add_item(discord.ui.Button(label="РП СТАК", style=discord.ButtonStyle.primary,
                                     custom_id=f"dir_rp:{applicant_id}:{orig_message_id}"))
    view.add_item(discord.ui.Button(label="КРАЙМ", style=discord.ButtonStyle.secondary,
                                     custom_id=f"dir_crime:{applicant_id}:{orig_message_id}"))
    return view


def build_thread_decision_view(applicant_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="✅ Принять в семью", style=discord.ButtonStyle.success,
                                     custom_id=f"thread_accept:{applicant_id}"))
    view.add_item(discord.ui.Button(label="❌ Отклонить", style=discord.ButtonStyle.danger,
                                     custom_id=f"thread_reject:{applicant_id}"))
    return view


DIRECTION_INSTRUCTIONS = {
    "РП СТАК": (
        "1️⃣ Смени игровую фамилию на **Apatia**.\n"
        "2️⃣ Скинь в эту ветку скриншот профиля/статистики персонажа."
    ),
    "КРАЙМ": (
        "1️⃣ Скинь в эту ветку запись отката (ганворк / капты / арена).\n"
        "2️⃣ Загрузи видео на **RuTube** или **YouTube** и пришли ссылку прямо сюда."
    ),
}

# Испытательный срок по направлениям (в часах) — берём прямо из правил (rules.py):
# «РП СТАК — 24 часа», «КРАЙМ — 3 дня»
TRIAL_PERIOD_HOURS = {
    "РП СТАК": 24,
    "КРАЙМ": 72,
}


# ==========================================
#   ФИНАЛИЗАЦИЯ ЗАЯВКИ (принять/отклонить)
# ==========================================

async def resolve_application(interaction: discord.Interaction, applicant_id: int, decision: str,
                               reason: str = None, direction: str = None,
                               thread: discord.Thread = None, original_message: discord.Message = None):
    guild = interaction.guild
    member = guild.get_member(applicant_id)
    if member is None:
        try:
            member = await guild.fetch_member(applicant_id)
        except Exception:
            member = None
    recruiter = interaction.user

    if decision == "accepted":
        new_role = guild.get_role(config.ROLE_IDS.get("NEW"))
        if member and new_role and new_role in member.roles:
            try:
                await member.remove_roles(new_role)
            except Exception:
                pass

        awaiting_role = guild.get_role(config.ROLE_IDS.get("AWAITING_RULES"))
        if member and awaiting_role:
            try:
                await member.add_roles(awaiting_role)
            except Exception:
                pass
        if member:
            rules_id = config.CHANNEL_IDS.get("RULES")
            rules_ref = f"<#{rules_id}>" if rules_id else "канал с правилами"

            trial_line = ""
            trial_hours = TRIAL_PERIOD_HOURS.get(direction) if direction else None
            if trial_hours:
                # Точку отсчёта берём от создания ветки направления (если она ещё жива),
                # а не от момента принятия — так срок не "обнуляется" из-за задержки рекрутера.
                start_time = thread.created_at if thread else discord.utils.utcnow()
                trial_end_unix = int((start_time + timedelta(hours=trial_hours)).timestamp())
                trial_line = (
                    f"\n\n⏳ **Испытательный срок ({direction}): {trial_hours} ч.**\n"
                    f"Истекает: <t:{trial_end_unix}:F> (<t:{trial_end_unix}:R>)"
                )

            try:
                await member.send(
                    "🎉 **Поздравляем!** Ваша заявка в семью **APATIA** одобрена. Добро пожаловать!\n\n"
                    f"Дальше нужно:\n"
                    f"1️⃣ Ознакомиться с правилами — {rules_ref}, и нажать там кнопку "
                    f"«✅ Я ознакомился с правилами» (после этого получишь роль).\n"
                    f"2️⃣ Сменить ник на формат `Имя Фамилия | Статик`."
                    f"{trial_line}"
                )
            except Exception:
                pass
        direction_part = f" (направление: **{direction}**)" if direction else ""
        history_text = f"✅ Рекрутер {recruiter.mention} принял кандидата <@{applicant_id}>{direction_part}"
        log_text = f"✅ **Принят** — кандидат: <@{applicant_id}> | Рекрутер: {recruiter.mention}{direction_part}"
        color = discord.Color.green()
    else:
        if member:
            try:
                await member.send(f"❌ Ваша заявка в семью **APATIA** отклонена.\n**Причина:** {reason}")
            except Exception:
                pass
        direction_part = f" (направление: **{direction}**)" if direction else ""
        history_text = f"❌ Рекрутер {recruiter.mention} отказал кандидату <@{applicant_id}>{direction_part}\n**Причина:** {reason}"
        log_text = f"❌ **Отказано** — кандидат: <@{applicant_id}> | Рекрутер: {recruiter.mention}{direction_part} | Причина: {reason}"
        color = discord.Color.red()

    cog = interaction.client.get_cog("ApplicationsCog")
    if cog:
        await cog.post_history(guild, history_text, color)
        cog.applications.pop(applicant_id, None)

    if original_message:
        try:
            await original_message.delete()
        except Exception:
            pass

    if thread:
        if cog:
            thread_log_text = f"{log_text} | Ветка «{thread.name}» удалена"
            await cog.log_action(guild, thread_log_text, color)
        try:
            await thread.send(embed=discord.Embed(description=history_text, color=color))
        except Exception:
            pass
        try:
            await thread.delete()
        except Exception:
            pass
    else:
        if cog:
            await cog.log_action(guild, log_text, color)


class RejectReasonModal(discord.ui.Modal, title="Причина отказа"):
    reason = discord.ui.TextInput(
        label="Причина",
        style=discord.TextStyle.paragraph,
        placeholder="Например: не подходит по возрасту / плохая история / читы...",
        required=True
    )

    def __init__(self, applicant_id: int, original_message: discord.Message = None,
                 thread: discord.Thread = None, direction: str = None):
        super().__init__()
        self.applicant_id = applicant_id
        self.original_message = original_message
        self.thread = thread
        self.direction = direction

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await resolve_application(
            interaction, self.applicant_id, "declined", reason=str(self.reason.value),
            direction=self.direction, thread=self.thread, original_message=self.original_message
        )
        await temp_reply(interaction, "Отказ отправлен, кандидат уведомлён.")


class ApplicationModal(discord.ui.Modal, title="Заявка в семью APATIA"):
    static_id = discord.ui.TextInput(label="Static ID и Имя в игре", placeholder="123456 | Vanya Apatia")
    age = discord.ui.TextInput(label="Ваш возраст", placeholder="16")
    online = discord.ui.TextInput(label="Онлайн в день", placeholder="4-6 часов")
    info = discord.ui.TextInput(label="О себе / Опыт", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("ApplicationsCog")
        if cog and interaction.user.id in cog.applications:
            return await interaction.response.send_message(
                "У вас уже есть активная заявка на рассмотрении, дождитесь ответа!", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)
        log_channel = interaction.guild.get_channel(config.CHANNEL_IDS["APP_HISTORY"])

        if cog:
            cog.applications[interaction.user.id] = True  # просто пометка "есть активная заявка"

        embed = discord.Embed(title=f"📥 Новая заявка от {interaction.user.name}", color=discord.Color.red())
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="Кандидат", value=interaction.user.mention, inline=False)
        embed.add_field(name="Static ID", value=str(self.static_id.value), inline=True)
        embed.add_field(name="Возраст", value=str(self.age.value), inline=True)
        embed.add_field(name="Онлайн", value=str(self.online.value), inline=True)
        embed.add_field(name="Инфо", value=str(self.info.value), inline=False)
        embed.set_footer(text="⏳ Ожидает рассмотрения")

        if log_channel:
            recruiter_role = interaction.guild.get_role(config.ROLE_IDS["RECRUITER"])
            tag = recruiter_role.mention if recruiter_role else ""
            view = build_new_application_view(interaction.user.id)
            await log_channel.send(content=f"🔔 {tag} Поступила новая заявка!", embed=embed, view=view)

        await temp_reply(interaction, "Ваша заявка отправлена рекрутерам! Ожидайте ответа в ЛС.")


class ApplicationPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📝 Подать заявку в семью", style=discord.ButtonStyle.danger, custom_id="btn_open_app")
    async def open_app(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ApplicationModal())


class ApplicationsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Только пометка "есть активная заявка у пользователя" (не критично, если
        # сбросится при рестарте — просто теоретически можно подать заявку второй раз).
        # Всё, что реально важно для работы кнопок, хранится в самих сообщениях.
        self.applications = {}

    async def log_action(self, guild: discord.Guild, text: str, color: discord.Color):
        channel = guild.get_channel(config.CHANNEL_IDS.get("LOGS"))
        if channel:
            embed = discord.Embed(description=text, color=color, timestamp=discord.utils.utcnow())
            await channel.send(embed=embed)

    async def post_history(self, guild: discord.Guild, text: str, color: discord.Color):
        channel = guild.get_channel(config.CHANNEL_IDS.get("APP_HISTORY"))
        if channel:
            embed = discord.Embed(description=text, color=color, timestamp=discord.utils.utcnow())
            await channel.send(embed=embed)

    async def _fetch_orig_message(self, guild: discord.Guild, orig_id):
        if not orig_id:
            return None
        channel = guild.get_channel(config.CHANNEL_IDS.get("APP_HISTORY"))
        if not channel:
            return None
        try:
            return await channel.fetch_message(orig_id)
        except Exception:
            return None

    # ------------------------------------------------------------
    # Общий guard для кнопок на главной панели заявки (Взять/Принять/Отклонить/Обзвон)
    # ------------------------------------------------------------
    async def _guard_main(self, interaction: discord.Interaction, applicant_id: int, need_claimer: bool):
        if not interaction.message or not interaction.message.embeds:
            await interaction.response.send_message("Не удалось прочитать заявку (сообщение повреждено).", ephemeral=True)
            return None
        embed = interaction.message.embeds[0]

        if interaction.user.id == applicant_id:
            await interaction.response.send_message("Нельзя рассматривать собственную заявку!", ephemeral=True)
            return None
        if not has_recruiter_access(interaction.user):
            await interaction.response.send_message("Недостаточно прав для рассмотрения заявок!", ephemeral=True)
            return None

        claimed_by = extract_claimed_by(embed)
        if need_claimer:
            if claimed_by is None:
                await interaction.response.send_message("Сначала возьмите заявку на рассмотрение!", ephemeral=True)
                return None
            if claimed_by != interaction.user.id:
                claimer = interaction.guild.get_member(claimed_by)
                await interaction.response.send_message(
                    f"Заявку уже рассматривает {claimer.mention if claimer else claimed_by}!", ephemeral=True
                )
                return None
        else:
            if claimed_by is not None and claimed_by != interaction.user.id:
                claimer = interaction.guild.get_member(claimed_by)
                await interaction.response.send_message(
                    f"Заявка уже взята в работу рекрутером {claimer.mention if claimer else claimed_by}!", ephemeral=True
                )
                return None
        return embed

    # ------------------------------------------------------------
    # РОУТЕР: единая точка входа для всех кнопок заявок/веток.
    # Работает ВСЕГДА, даже сразу после рестарта бота, потому что
    # ничего не берёт из памяти — только из самого сообщения.
    # ------------------------------------------------------------
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "")
        if not custom_id or ":" not in custom_id:
            return

        parts = custom_id.split(":")
        prefix = parts[0]

        try:
            if prefix == "app_claim":
                await self._handle_claim(interaction, int(parts[1]))
            elif prefix == "app_accept":
                await self._handle_accept_open(interaction, int(parts[1]))
            elif prefix == "app_decline":
                await self._handle_decline_open(interaction, int(parts[1]))
            elif prefix == "app_call":
                await self._handle_call(interaction, int(parts[1]))
            elif prefix == "dir_rp":
                await self._handle_direction(interaction, int(parts[1]), int(parts[2]), "РП СТАК")
            elif prefix == "dir_crime":
                await self._handle_direction(interaction, int(parts[1]), int(parts[2]), "КРАЙМ")
            elif prefix == "thread_accept":
                await self._handle_thread_accept(interaction, int(parts[1]))
            elif prefix == "thread_reject":
                await self._handle_thread_reject(interaction, int(parts[1]))
        except Exception as e:
            print(f"❌ Ошибка обработки кнопки {custom_id}: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ Произошла ошибка: {e}", ephemeral=True)
            except Exception:
                pass

    # ---- обработчики главной панели ----

    async def _handle_claim(self, interaction: discord.Interaction, applicant_id: int):
        embed = await self._guard_main(interaction, applicant_id, need_claimer=False)
        if embed is None:
            return
        if extract_claimed_by(embed) == interaction.user.id:
            return await interaction.response.send_message("Вы уже ведёте эту заявку.", ephemeral=True)

        embed.color = discord.Color.orange()
        embed.set_footer(text=f"🔍 На рассмотрении у {interaction.user.display_name} | claimed:{interaction.user.id}")
        await interaction.response.edit_message(embed=embed)

        await self.log_action(
            interaction.guild,
            f"🔍 Рекрутер {interaction.user.mention} взял в работу заявку <@{applicant_id}>",
            discord.Color.orange()
        )

    async def _handle_accept_open(self, interaction: discord.Interaction, applicant_id: int):
        embed = await self._guard_main(interaction, applicant_id, need_claimer=True)
        if embed is None:
            return
        await interaction.response.send_message(
            "Выберите направление для кандидата (сначала убедитесь, что нет читов/нарушений):",
            view=build_direction_view(applicant_id, interaction.message.id),
            ephemeral=True
        )

    async def _handle_decline_open(self, interaction: discord.Interaction, applicant_id: int):
        embed = await self._guard_main(interaction, applicant_id, need_claimer=True)
        if embed is None:
            return
        await interaction.response.send_modal(
            RejectReasonModal(applicant_id, original_message=interaction.message)
        )

    async def _handle_call(self, interaction: discord.Interaction, applicant_id: int):
        embed = await self._guard_main(interaction, applicant_id, need_claimer=True)
        if embed is None:
            return
        member = interaction.guild.get_member(applicant_id)
        if member is None:
            try:
                member = await interaction.guild.fetch_member(applicant_id)
            except Exception:
                member = None

        sent = False
        if member:
            try:
                voice_channel_id = config.CHANNEL_IDS.get("RECRUIT_CALL")
                voice_line = f"\n\n🔊 Заходи сюда: <#{voice_channel_id}>" if voice_channel_id else ""
                await member.send(
                    f"📞 Рекрутер **{interaction.user.display_name}** просит вас зайти в голосовой канал "
                    f"для короткого собеседования по вашей заявке в **APATIA**.{voice_line}"
                )
                sent = True
            except Exception:
                pass

        if sent:
            await temp_reply(interaction, "Кандидату отправлено приглашение на обзвон!")
        else:
            await interaction.response.send_message(
                "Не удалось отправить ЛС кандидату (закрыты сообщения).", ephemeral=True
            )

        await self.log_action(
            interaction.guild,
            f"📞 Рекрутер {interaction.user.mention} пригласил на обзвон <@{applicant_id}>",
            discord.Color.blurple()
        )

    # ---- выбор направления -> создание ветки ----

    async def _handle_direction(self, interaction: discord.Interaction, applicant_id: int,
                                 orig_message_id: int, direction: str):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        original_message = await self._fetch_orig_message(guild, orig_message_id)
        if original_message and original_message.embeds:
            static_value = extract_field(original_message.embeds[0], "Static ID")
        else:
            static_value = ""

        member = guild.get_member(applicant_id)
        if member is None:
            try:
                member = await guild.fetch_member(applicant_id)
            except Exception:
                member = None

        thread_parent = guild.get_channel(config.CHANNEL_IDS.get("APP_LOG"))
        if not thread_parent:
            return await temp_reply(interaction, "❌ Канал APP_LOG не найден — проверь ID в config.py!")

        thread_name = f"︱{direction}︱{static_value}"[:100]
        try:
            thread = await thread_parent.create_thread(
                name=thread_name, type=discord.ChannelType.private_thread, invitable=False
            )
        except Exception as e:
            print(f"❌ Не удалось создать ветку направления {direction}: {e}")
            return await temp_reply(interaction, f"❌ Не удалось создать ветку: {e}")

        candidate_added = False
        if member:
            try:
                await thread.add_user(member)
                candidate_added = True
            except Exception as e:
                print(f"⚠️ Не удалось добавить кандидата в ветку {thread.id}: {e}")
        try:
            await thread.add_user(interaction.user)
        except Exception as e:
            print(f"⚠️ Не удалось добавить рекрутера в ветку {thread.id}: {e}")

        # Наблюдатели (RECRUITER/HIGH/DEP_OWN/OWNER/LEADER) НЕ добавляются в тред через
        # add_user — это вызывает у каждого системное уведомление Discord "вас добавили
        # в тред" на КАЖДУЮ новую заявку, что жутко бесит при частых заявках.
        #
        # Вместо этого дай нужным ролям право "Управление потоками" (Manage Threads)
        # на канале APP_LOG в настройках сервера (ПКМ по каналу → Права доступа →
        # выбрать роль → включить Manage Threads). Тогда они видят ВСЕ приватные
        # ветки в этом канале сами, без принудительного добавления и без уведомлений —
        # а нажимать кнопки решения всё равно смогут только кандидат+ответственный
        # рекрутер (это уже проверяется отдельно, через footer сообщения в ветке).

        if not candidate_added:
            try:
                await thread.send(
                    "⚠️ Не удалось автоматически добавить кандидата в эту ветку. "
                    "Добавь вручную: правой кнопкой по ветке → **Люди** → **Добавить людей**."
                )
            except Exception:
                pass

        instructions = DIRECTION_INSTRUCTIONS.get(direction, "")

        trial_hours = TRIAL_PERIOD_HOURS.get(direction)
        trial_line = ""
        trial_end_unix = None
        if trial_hours:
            trial_end = discord.utils.utcnow() + timedelta(hours=trial_hours)
            trial_end_unix = int(trial_end.timestamp())
            trial_line = (
                f"\n\n⏳ **Испытательный срок: {trial_hours} ч.**\n"
                f"Истекает: <t:{trial_end_unix}:F> (<t:{trial_end_unix}:R>)"
            )

        thread_embed = discord.Embed(
            title=f"🎯 Направление: {direction}",
            description=(
                f"Кандидат: <@{applicant_id}>\nОтветственный рекрутер: {interaction.user.mention}\n\n"
                f"📋 **Что нужно сделать кандидату:**\n{instructions}"
                f"{trial_line}"
            ),
            color=discord.Color.gold()
        )
        # Прячем в footer ID ответственного рекрутера и ID исходного сообщения заявки —
        # это позволяет кнопкам в ветке работать даже после рестарта бота.
        orig_marker = original_message.id if original_message else 0
        thread_embed.set_footer(text=f"responsible:{interaction.user.id}|orig:{orig_marker}")

        view = build_thread_decision_view(applicant_id)
        try:
            await thread.send(
                content=f"{member.mention if member else ''} | {interaction.user.mention}",
                embed=thread_embed, view=view
            )
        except Exception as e:
            print(f"❌ Не удалось отправить сообщение с инструкциями в ветку {thread.id}: {e}")

        if original_message:
            try:
                info_embed = original_message.embeds[0]
                info_embed.color = discord.Color.gold()
                info_embed.set_footer(text=f"🎯 Направление: {direction} | Ветка: {thread.name}")
                await original_message.edit(
                    content=f"⏳ Заявка в работе ({direction}) — {interaction.user.mention}. Обсуждение: {thread.mention}",
                    embed=info_embed, view=None
                )
            except Exception:
                pass

        await self.log_action(
            guild,
            f"🎯 Рекрутер {interaction.user.mention} направил <@{applicant_id}> на **{direction}**, создана ветка {thread.mention}",
            discord.Color.gold()
        )

        try:
            await temp_edit_original(interaction, content=f"Ветка {thread.mention} создана!", view=None)
        except Exception:
            await temp_reply(interaction, f"Ветка {thread.mention} создана!")

    # ---- решения внутри ветки направления ----

    async def _handle_thread_accept(self, interaction: discord.Interaction, applicant_id: int):
        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        responsible_id, orig_id = extract_thread_meta(embed) if embed else (None, None)

        if interaction.user.id == applicant_id:
            return await interaction.response.send_message("Нельзя решать по своей же заявке!", ephemeral=True)
        is_admin = interaction.user.guild_permissions.administrator
        if responsible_id is not None and interaction.user.id != responsible_id and not is_admin:
            return await interaction.response.send_message(
                "Решение по этой заявке может вынести только ответственный рекрутер!", ephemeral=True
            )

        direction = embed.title.replace("🎯 Направление: ", "") if embed and embed.title else None

        await interaction.response.defer()
        original_message = await self._fetch_orig_message(interaction.guild, orig_id)
        await resolve_application(
            interaction, applicant_id, "accepted",
            direction=direction, thread=interaction.channel, original_message=original_message
        )

    async def _handle_thread_reject(self, interaction: discord.Interaction, applicant_id: int):
        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        responsible_id, orig_id = extract_thread_meta(embed) if embed else (None, None)

        if interaction.user.id == applicant_id:
            return await interaction.response.send_message("Нельзя решать по своей же заявке!", ephemeral=True)
        is_admin = interaction.user.guild_permissions.administrator
        if responsible_id is not None and interaction.user.id != responsible_id and not is_admin:
            return await interaction.response.send_message(
                "Решение по этой заявке может вынести только ответственный рекрутер!", ephemeral=True
            )

        direction = embed.title.replace("🎯 Направление: ", "") if embed and embed.title else None
        original_message = await self._fetch_orig_message(interaction.guild, orig_id)

        await interaction.response.send_modal(
            RejectReasonModal(applicant_id, original_message=original_message,
                               thread=interaction.channel, direction=direction)
        )

    @discord.app_commands.command(
        name="setup_apps",
        description="Установить панель заявок"
    )
    async def setup_apps(self, interaction: discord.Interaction):
        embed, files = build_panel_embed_files()
        await interaction.channel.send(embed=embed, files=files, view=ApplicationPanelView())
        await temp_reply(interaction, "Панель заявок создана!")

    @discord.app_commands.command(
        name="setup_thread_visibility",
        description="Дать рекрутам и хай-рангам право видеть все приватные ветки заявок (без спам-уведомлений)"
    )
    async def setup_thread_visibility(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        channel = guild.get_channel(config.CHANNEL_IDS.get("APP_LOG"))
        if not channel:
            return await temp_reply(interaction, "❌ Канал APP_LOG не найден — проверь ID в config.py!")

        observer_role_keys = ("RECRUITER", "HIGH", "DEP_OWN", "OWNER", "LEADER")
        done, skipped = [], []
        for role_key in observer_role_keys:
            role_id = config.ROLE_IDS.get(role_key)
            role = guild.get_role(role_id) if role_id else None
            if not role:
                skipped.append(role_key)
                continue
            overwrite = channel.overwrites_for(role)
            overwrite.view_channel = True
            overwrite.manage_threads = True
            try:
                await channel.set_permissions(role, overwrite=overwrite)
                done.append(role.name)
            except Exception as e:
                skipped.append(f"{role_key} ({e})")

        text = f"✅ Право «видеть все ветки» выдано ролям: {', '.join(done) if done else '—'}."
        if skipped:
            text += f"\n⚠️ Пропущено: {', '.join(skipped)}."
        await temp_reply(interaction, text)


async def setup(bot):
    await bot.add_cog(ApplicationsCog(bot))
    bot.add_view(ApplicationPanelView())  # кнопка "Подать заявку" переживает рестарт бота
