# cogs/applications.py
import discord
from discord.ext import commands
import config

class RejectReasonModal(discord.ui.Modal, title="Укажите причину отказа"):
    reason = discord.ui.TextInput(
        label="Причина", 
        style=discord.TextStyle.paragraph, 
        placeholder="Например: Не подходит возраст / плохая история...", 
        required=True
    )

    def __init__(self, applicant_id: int, message: discord.Message):
        super().__init__()
        self.applicant_id = applicant_id
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        member = guild.get_member(self.applicant_id)

        if member:
            try:
                await member.send(f"❌ Ваша заявка в семью **APATIA** была отклонена.\n**Причина:** {self.reason.value}")
            except Exception:
                pass

        embed = discord.Embed(
            title="❌ Заявка ОТКЛОНЕНА",
            description=f"Кандидат: <@{self.applicant_id}>\nРекрутер: {interaction.user.mention}\n**Причина:** {self.reason.value}",
            color=discord.Color.red()
        )
        await self.message.edit(content=None, embed=embed, view=None)
        await interaction.followup.send("Отказ отправлен!", ephemeral=True)


class ApplicationProcessView(discord.ui.View):
    def __init__(self, applicant_id: int, app_data: dict):
        super().__init__(timeout=None)
        self.applicant_id = applicant_id
        self.app_data = app_data

    async def create_direction_thread(self, interaction: discord.Interaction, direction_type: str, requirements_text: str):
        await interaction.response.defer(ephemeral=True)
        log_channel = interaction.channel
        member = interaction.guild.get_member(self.applicant_id)

        thread_name = f"︱{direction_type}︱{self.app_data['static']}"
        thread = await log_channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.private_thread,
            invitable=False
        )

        if member:
            await thread.add_user(member)
        await thread.add_user(interaction.user)

        embed = discord.Embed(
            title=f"🎯 Направление: {direction_type}",
            description=f"Кандидат: <@{self.applicant_id}>\nОтветственный рекрутер: {interaction.user.mention}\n\n"
                        f"📋 **Требования от кандидата:**\n{requirements_text}",
            color=discord.Color.gold()
        )
        
        view = ThreadDecisionView(applicant_id=self.applicant_id, parent_message=interaction.message)
        await thread.send(content=f"Кандидат {member.mention if member else ''} | Рекрутер {interaction.user.mention}", embed=embed, view=view)
        
        await interaction.message.edit(
            content=f"⏳ Заявка взята в работу ({direction_type}) рекрутером {interaction.user.mention}. Обсуждение в ветке: {thread.mention}",
            view=None
        )
        await interaction.followup.send(f"Ветка {thread.mention} создана!", ephemeral=True)

    @discord.ui.button(label="РП СТАК", style=discord.ButtonStyle.primary, custom_id="btn_rp_stack")
    async def rp_stack(self, interaction: discord.Interaction, button: discord.ui.Button):
        reqs = "1. Записать и скинуть откаты стрельбы/РП ситуаций.\n2. Пройти устное собеседование в войсе.\n3. Скинуть скриншот статистики персонажа."
        await self.create_direction_thread(interaction, "РП СТАК", reqs)

    @discord.ui.button(label="КРАЙМ", style=discord.ButtonStyle.secondary, custom_id="btn_crime_stack")
    async def crime_stack(self, interaction: discord.Interaction, button: discord.ui.Button):
        reqs = "1. Скинуть откаты с ганвар / каптов / арены.\n2. Продемонстрировать знание правил крайм-структур.\n3. Скриншот скиллов и откатов."
        await self.create_direction_thread(interaction, "КРАЙМ", reqs)

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.danger, custom_id="btn_reject_app")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RejectReasonModal(self.applicant_id, interaction.message))


class ThreadDecisionView(discord.ui.View):
    def __init__(self, applicant_id: int, parent_message: discord.Message):
        super().__init__(timeout=None)
        self.applicant_id = applicant_id
        self.parent_message = parent_message

    @discord.ui.button(label="ПРИНЯТЬ В СЕМЬЮ", style=discord.ButtonStyle.success, custom_id="btn_accept_final")
    async def accept_final(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        guild = interaction.guild
        member = guild.get_member(self.applicant_id)

        if member:
            new_role = guild.get_role(config.ROLE_IDS["NEW"])
            if new_role and new_role in member.roles:
                await member.remove_roles(new_role)

            try:
                await member.send("🎉 **Поздравляем!** Вы успешно приняты в семью **APATIA**!")
            except Exception:
                pass

        embed = discord.Embed(
            title="✅ Заявка ПРИНЯТА",
            description=f"Кандидат: <@{self.applicant_id}>\nПринял рекрутер: {interaction.user.mention}",
            color=discord.Color.green()
        )
        await self.parent_message.edit(content=None, embed=embed, view=None)
        await interaction.followup.send("Кандидат принят! Ветка закрывается.")
        await interaction.channel.edit(archived=True, locked=True)

    @discord.ui.button(label="ОТКЛОНИТЬ", style=discord.ButtonStyle.danger, custom_id="btn_reject_final")
    async def reject_final(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RejectReasonModal(self.applicant_id, self.parent_message))


class ApplicationModal(discord.ui.Modal, title="Заявка в семью APATIA"):
    static_id = discord.ui.TextInput(label="Static ID и Имя в игре", placeholder="123456 | Vanya Apatia")
    age = discord.ui.TextInput(label="Ваш возраст", placeholder="16")
    online = discord.ui.TextInput(label="Онлайн в день", placeholder="4-6 часов")
    info = discord.ui.TextInput(label="О себе / Опыт", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        log_channel = interaction.guild.get_channel(config.CHANNEL_IDS["APP_LOG"])

        app_data = {
            "static": self.static_id.value,
            "age": self.age.value,
            "online": self.online.value,
            "info": self.info.value
        }

        embed = discord.Embed(title=f"📥 Новая заявка от {interaction.user.name}", color=discord.Color.red())
        embed.add_field(name="Кандидат", value=interaction.user.mention, inline=False)
        embed.add_field(name="Static ID", value=self.static_id.value, inline=True)
        embed.add_field(name="Возраст", value=self.age.value, inline=True)
        embed.add_field(name="Онлайн", value=self.online.value, inline=True)
        embed.add_field(name="Инфо", value=self.info.value, inline=False)

        if log_channel:
            recruiter_role = interaction.guild.get_role(config.ROLE_IDS["RECRUITER"])
            tag = recruiter_role.mention if recruiter_role else "@everyone"
            view = ApplicationProcessView(applicant_id=interaction.user.id, app_data=app_data)
            await log_channel.send(content=f"🔔 {tag} Поступила новая заявка!", embed=embed, view=view)

        await interaction.followup.send("Ваша заявка отправлена рекрутерам!", ephemeral=True)


class ApplicationPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Подать заявку", style=discord.ButtonStyle.danger, custom_id="btn_open_app")
    async def open_app(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ApplicationModal())


class ApplicationsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="setup_apps", description="Установить панель заявок")
    async def setup_apps(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🥀 Вступление в семью APATIA",
            description="Нажмите кнопку ниже, чтобы подать заявку в наш состав.",
            color=discord.Color.dark_red()
        )
        await interaction.channel.send(embed=embed, view=ApplicationPanelView())
        await interaction.response.send_message("Панель создана!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(ApplicationsCog(bot))