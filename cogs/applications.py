# cogs/applications.py
import os
import discord
from discord.ext import commands
import config


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


async def resolve_application(interaction: discord.Interaction, applicant_id: int, decision: str,
                               reason: str = None, direction: str = None,
                               thread: discord.Thread = None, original_message: discord.Message = None):
    """
    Финализирует заявку: пишет кандидату в ЛС, кидает итог в историю,
    подробный лог — в лог-канал для хай-рангов, чистит состояние.
    decision: "accepted" | "declined"
    """
    guild = interaction.guild
    member = guild.get_member(applicant_id)
    recruiter = interaction.user

    if decision == "accepted":
        new_role = guild.get_role(config.ROLE_IDS.get("NEW"))
        if member and new_role and new_role in member.roles:
            try:
                await member.remove_roles(new_role)
            except Exception:
                pass
        if member:
            try:
                await member.send("🎉 **Поздравляем!** Ваша заявка в семью **APATIA** одобрена. Добро пожаловать!")
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
            result_embed = discord.Embed(
                title="✅ Заявка ПРИНЯТА" if decision == "accepted" else "❌ Заявка ОТКЛОНЕНА",
                description=history_text,
                color=color
            )
            await original_message.edit(content=None, embed=result_embed, view=None)
        except Exception:
            pass

    if thread:
        # Для веток (РП СТАК / КРАЙМ): кидаем подробный итог в LOGS
        # и полностью удаляем ветку, вместо архивации.
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
                 thread: discord.Thread = None, direction: str = None,
                 source_view: discord.ui.View = None, source_message: discord.Message = None):
        super().__init__()
        self.applicant_id = applicant_id
        self.original_message = original_message
        self.thread = thread
        self.direction = direction
        self.source_view = source_view
        self.source_message = source_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await resolve_application(
            interaction, self.applicant_id, "declined", reason=str(self.reason.value),
            direction=self.direction, thread=self.thread, original_message=self.original_message
        )
        if self.source_view is not None:
            self.source_view.resolved = True
        if self.source_message is not None:
            try:
                await self.source_message.edit(view=None)
            except Exception:
                pass
        await interaction.followup.send("Отказ отправлен, кандидат уведомлён.", ephemeral=True)


class ThreadDecisionView(discord.ui.View):
    def __init__(self, applicant_id: int, direction: str, original_message: discord.Message):
        super().__init__(timeout=None)
        self.applicant_id = applicant_id
        self.direction = direction
        self.original_message = original_message
        self.resolved = False

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.applicant_id:
            await interaction.response.send_message("Нельзя решать по своей же заявке!", ephemeral=True)
            return False
        if not has_recruiter_access(interaction.user):
            await interaction.response.send_message("Недостаточно прав для решения по заявке!", ephemeral=True)
            return False
        if self.resolved:
            await interaction.response.send_message("Решение по этой заявке уже вынесено.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Принять в семью", style=discord.ButtonStyle.success, custom_id="thread_accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        self.resolved = True
        await interaction.response.defer()
        await resolve_application(
            interaction, self.applicant_id, "accepted",
            direction=self.direction, thread=interaction.channel, original_message=self.original_message
        )
        try:
            await interaction.message.edit(view=None)
        except Exception:
            pass

    @discord.ui.button(label="❌ Отклонить", style=discord.ButtonStyle.danger, custom_id="thread_reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        await interaction.response.send_modal(RejectReasonModal(
            self.applicant_id, original_message=self.original_message, thread=interaction.channel,
            direction=self.direction, source_view=self, source_message=interaction.message
        ))


class DirectionSelectView(discord.ui.View):
    def __init__(self, applicant_id: int, app_data: dict, original_message: discord.Message):
        super().__init__(timeout=180)
        self.applicant_id = applicant_id
        self.app_data = app_data
        self.original_message = original_message

    async def _create_thread(self, interaction: discord.Interaction, direction: str, instructions: str):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        member = guild.get_member(self.applicant_id)
        log_channel = guild.get_channel(config.CHANNEL_IDS.get("APP_LOG"))

        thread_name = f"︱{direction}︱{self.app_data.get('static', '')}"[:100]
        thread = await log_channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.private_thread,
            invitable=False
        )

        if member:
            await thread.add_user(member)
        await thread.add_user(interaction.user)

        # Добавляем всех рекрутов и хай-ранг — доступ к ветке только у них
        added = {interaction.user.id, self.applicant_id}
        for key in ("RECRUITER", "HIGH"):
            role = guild.get_role(config.ROLE_IDS.get(key))
            if role:
                for m in role.members:
                    if m.id not in added:
                        try:
                            await thread.add_user(m)
                            added.add(m.id)
                        except Exception:
                            pass

        self.app_data["claimed_by"] = interaction.user.id
        self.app_data["direction"] = direction
        self.app_data["thread_id"] = thread.id

        embed = discord.Embed(
            title=f"🎯 Направление: {direction}",
            description=(
                f"Кандидат: <@{self.applicant_id}>\nОтветственный рекрутер: {interaction.user.mention}\n\n"
                f"📋 **Что нужно сделать кандидату:**\n{instructions}"
            ),
            color=discord.Color.gold()
        )
        view = ThreadDecisionView(self.applicant_id, direction, self.original_message)
        await thread.send(
            content=f"{member.mention if member else ''} | {interaction.user.mention}",
            embed=embed, view=view
        )

        try:
            info_embed = self.original_message.embeds[0]
            info_embed.color = discord.Color.gold()
            info_embed.set_footer(text=f"🎯 Направление: {direction} | Ветка: {thread.name}")
            await self.original_message.edit(
                content=f"⏳ Заявка в работе ({direction}) — {interaction.user.mention}. Обсуждение: {thread.mention}",
                embed=info_embed, view=None
            )
        except Exception:
            pass

        cog = interaction.client.get_cog("ApplicationsCog")
        if cog:
            await cog.log_action(
                guild,
                f"🎯 Рекрутер {interaction.user.mention} направил <@{self.applicant_id}> на **{direction}**, создана ветка {thread.mention}",
                discord.Color.gold()
            )

        await interaction.followup.send(f"Ветка {thread.mention} создана!", ephemeral=True)

    @discord.ui.button(label="РП СТАК", style=discord.ButtonStyle.primary)
    async def rp_stack(self, interaction: discord.Interaction, button: discord.ui.Button):
        instructions = (
            "1️⃣ Смени игровую фамилию на **Apatia**.\n"
            "2️⃣ Скинь в эту ветку скриншот профиля/статистики персонажа."
        )
        await self._create_thread(interaction, "РП СТАК", instructions)

    @discord.ui.button(label="КРАЙМ", style=discord.ButtonStyle.secondary)
    async def crime(self, interaction: discord.Interaction, button: discord.ui.Button):
        instructions = (
            "1️⃣ Скинь в эту ветку запись отката (ганворк / капты / арена).\n"
            "2️⃣ Загрузи видео на **RuTube** или **YouTube** и пришли ссылку прямо сюда."
        )
        await self._create_thread(interaction, "КРАЙМ", instructions)


class NewApplicationView(discord.ui.View):
    def __init__(self, applicant_id: int, app_data: dict):
        super().__init__(timeout=None)
        self.applicant_id = applicant_id
        self.app_data = app_data  # тот же dict, что лежит в cog.applications[applicant_id]

    async def _guard(self, interaction: discord.Interaction, need_claimer: bool) -> bool:
        if interaction.user.id == self.applicant_id:
            await interaction.response.send_message("Нельзя рассматривать собственную заявку!", ephemeral=True)
            return False
        if not has_recruiter_access(interaction.user):
            await interaction.response.send_message("Недостаточно прав для рассмотрения заявок!", ephemeral=True)
            return False

        claimed_by = self.app_data.get("claimed_by")
        if need_claimer:
            if claimed_by is None:
                await interaction.response.send_message("Сначала возьмите заявку на рассмотрение!", ephemeral=True)
                return False
            if claimed_by != interaction.user.id:
                claimer = interaction.guild.get_member(claimed_by)
                await interaction.response.send_message(
                    f"Заявку уже рассматривает {claimer.mention if claimer else claimed_by}!", ephemeral=True
                )
                return False
        else:
            if claimed_by is not None and claimed_by != interaction.user.id:
                claimer = interaction.guild.get_member(claimed_by)
                await interaction.response.send_message(
                    f"Заявка уже взята в работу рекрутером {claimer.mention if claimer else claimed_by}!", ephemeral=True
                )
                return False
        return True

    @discord.ui.button(label="🔍 Взять на рассмотрение", style=discord.ButtonStyle.primary, custom_id="app_claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction, need_claimer=False):
            return
        if self.app_data.get("claimed_by") == interaction.user.id:
            return await interaction.response.send_message("Вы уже ведёте эту заявку.", ephemeral=True)

        self.app_data["claimed_by"] = interaction.user.id
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.orange()
        embed.set_footer(text=f"🔍 На рассмотрении у {interaction.user.display_name}")
        await interaction.response.edit_message(embed=embed, view=self)

        cog = interaction.client.get_cog("ApplicationsCog")
        if cog:
            await cog.log_action(
                interaction.guild,
                f"🔍 Рекрутер {interaction.user.mention} взял в работу заявку <@{self.applicant_id}>",
                discord.Color.orange()
            )

    @discord.ui.button(label="✅ Принять", style=discord.ButtonStyle.success, custom_id="app_accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction, need_claimer=True):
            return
        await interaction.response.send_message(
            "Выберите направление для кандидата (сначала убедитесь, что нет читов/нарушений):",
            view=DirectionSelectView(self.applicant_id, self.app_data, interaction.message),
            ephemeral=True
        )

    @discord.ui.button(label="❌ Отклонить", style=discord.ButtonStyle.danger, custom_id="app_decline")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction, need_claimer=True):
            return
        await interaction.response.send_modal(
            RejectReasonModal(self.applicant_id, original_message=interaction.message)
        )

    @discord.ui.button(label="📞 На обзвон", style=discord.ButtonStyle.secondary, custom_id="app_call")
    async def call(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction, need_claimer=True):
            return
        member = interaction.guild.get_member(self.applicant_id)
        sent = False
        if member:
            try:
                await member.send(
                    f"📞 Рекрутер **{interaction.user.display_name}** просит вас зайти в голосовой канал "
                    f"для короткого собеседования по вашей заявке в **APATIA**."
                )
                sent = True
            except Exception:
                pass
        await interaction.response.send_message(
            "Кандидату отправлено приглашение на обзвон!" if sent else "Не удалось отправить ЛС кандидату (закрыты сообщения).",
            ephemeral=True
        )
        cog = interaction.client.get_cog("ApplicationsCog")
        if cog:
            await cog.log_action(
                interaction.guild,
                f"📞 Рекрутер {interaction.user.mention} пригласил на обзвон <@{self.applicant_id}>",
                discord.Color.blurple()
            )


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
        log_channel = interaction.guild.get_channel(config.CHANNEL_IDS["APP_LOG"])

        app_data = {
            "applicant_id": interaction.user.id,
            "static": str(self.static_id.value),
            "age": str(self.age.value),
            "online": str(self.online.value),
            "info": str(self.info.value),
            "claimed_by": None,
        }
        if cog:
            cog.applications[interaction.user.id] = app_data

        embed = discord.Embed(title=f"📥 Новая заявка от {interaction.user.name}", color=discord.Color.red())
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="Кандидат", value=interaction.user.mention, inline=False)
        embed.add_field(name="Static ID", value=app_data["static"], inline=True)
        embed.add_field(name="Возраст", value=app_data["age"], inline=True)
        embed.add_field(name="Онлайн", value=app_data["online"], inline=True)
        embed.add_field(name="Инфо", value=app_data["info"], inline=False)
        embed.set_footer(text="⏳ Ожидает рассмотрения")

        if log_channel:
            recruiter_role = interaction.guild.get_role(config.ROLE_IDS["RECRUITER"])
            tag = recruiter_role.mention if recruiter_role else ""
            view = NewApplicationView(interaction.user.id, app_data)
            await log_channel.send(content=f"🔔 {tag} Поступила новая заявка!", embed=embed, view=view)

        await interaction.followup.send("Ваша заявка отправлена рекрутерам! Ожидайте ответа в ЛС.", ephemeral=True)


class ApplicationPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📝 Подать заявку в семью", style=discord.ButtonStyle.danger, custom_id="btn_open_app")
    async def open_app(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ApplicationModal())


class ApplicationsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.applications = {}  # applicant_id -> app_data dict (сбрасывается при рестарте бота)

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

    @discord.app_commands.command(name="setup_apps", description="Установить панель заявок")
    async def setup_apps(self, interaction: discord.Interaction):
        embed, files = build_panel_embed_files()
        await interaction.channel.send(embed=embed, files=files, view=ApplicationPanelView())
        await interaction.response.send_message("Панель заявок создана!", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ApplicationsCog(bot))
    bot.add_view(ApplicationPanelView())  # чтобы кнопка "Подать заявку" жила и после рестарта бота