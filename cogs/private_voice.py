# cogs/private_voice.py
import discord
from discord.ext import commands
import config


def get_cog(interaction: discord.Interaction) -> "PrivateVoiceCog":
    return interaction.client.get_cog("PrivateVoiceCog")


async def get_owned_channel(interaction: discord.Interaction):
    """
    Проверяет, что пользователь сидит в войсе и что этот войс — приватный,
    созданный ботом. Возвращает канал или None (и сам отвечает на interaction
    сообщением об ошибке).
    """
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message("Вы должны находиться в своём приватном канале!", ephemeral=True)
        return None

    channel = interaction.user.voice.channel
    cog = get_cog(interaction)

    if not cog or channel.id not in cog.active_voices:
        await interaction.response.send_message("Это не приватный канал, созданный ботом!", ephemeral=True)
        return None

    owner_id = cog.active_voices[channel.id]
    is_owner = interaction.user.id == owner_id
    is_admin = interaction.user.guild_permissions.administrator

    if not is_owner and not is_admin:
        owner = interaction.guild.get_member(owner_id)
        await interaction.response.send_message(
            f"Управлять этой комнатой может только её владелец ({owner.mention if owner else owner_id})!",
            ephemeral=True
        )
        return None

    return channel


class RenameModal(discord.ui.Modal, title="Переименовать комнату"):
    new_name = discord.ui.TextInput(label="Новое название", placeholder="Комната Вани", max_length=95)

    def __init__(self, channel: discord.VoiceChannel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await self.channel.edit(name=str(self.new_name.value))
            await interaction.response.send_message(f"✅ Комната переименована в **{self.new_name.value}**!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Не удалось переименовать: {e}", ephemeral=True)


class LimitModal(discord.ui.Modal, title="Лимит участников"):
    limit = discord.ui.TextInput(label="Лимит (0 = без лимита, макс 99)", placeholder="5")

    def __init__(self, channel: discord.VoiceChannel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = int(str(self.limit.value))
            if value < 0 or value > 99:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Введите число от 0 до 99!", ephemeral=True)

        await self.channel.edit(user_limit=value)
        text = "без лимита" if value == 0 else f"**{value}** участников"
        await interaction.response.send_message(f"✅ Лимит комнаты: {text}.", ephemeral=True)


class KickSelectView(discord.ui.View):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.channel = channel

        options = [
            discord.SelectOption(label=m.display_name, value=str(m.id))
            for m in channel.members
        ]
        if options:
            self.select.options = options
        else:
            self.select.disabled = True
            self.select.placeholder = "В комнате больше никого нет"

    @discord.ui.select(placeholder="Кого выгнать из комнаты?")
    async def select(self, interaction: discord.Interaction, select: discord.ui.Select):
        member_id = int(select.values[0])
        member = interaction.guild.get_member(member_id)
        if member and member.voice and member.voice.channel and member.voice.channel.id == self.channel.id:
            await member.move_to(None)
            await interaction.response.edit_message(content=f"👢 {member.mention} выгнан из комнаты!", view=None)
        else:
            await interaction.response.edit_message(content="Этого участника уже нет в комнате.", view=None)


class TransferSelectView(discord.ui.View):
    def __init__(self, channel: discord.VoiceChannel, cog: "PrivateVoiceCog"):
        super().__init__(timeout=60)
        self.channel = channel
        self.cog = cog

        options = [
            discord.SelectOption(label=m.display_name, value=str(m.id))
            for m in channel.members if not m.bot
        ]
        if options:
            self.select.options = options
        else:
            self.select.disabled = True
            self.select.placeholder = "Некому передать права"

    @discord.ui.select(placeholder="Кому передать права владельца?")
    async def select(self, interaction: discord.Interaction, select: discord.ui.Select):
        new_owner_id = int(select.values[0])
        new_owner = interaction.guild.get_member(new_owner_id)
        self.cog.active_voices[self.channel.id] = new_owner_id
        await interaction.response.edit_message(
            content=f"👑 Права на комнату переданы: {new_owner.mention if new_owner else new_owner_id}!",
            view=None
        )


class VoiceControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Закрыть/Открыть", style=discord.ButtonStyle.secondary, custom_id="v_lock")
    async def lock_voice(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await get_owned_channel(interaction)
        if not channel:
            return

        overwrite = channel.overwrites_for(interaction.guild.default_role)
        if overwrite.connect is False:
            overwrite.connect = None
            await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
            await interaction.response.send_message("🔓 Комната открыта для всех!", ephemeral=True)
        else:
            overwrite.connect = False
            await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
            await interaction.response.send_message("🔒 Комната закрыта от посторонних!", ephemeral=True)

    @discord.ui.button(label="✏️ Название", style=discord.ButtonStyle.secondary, custom_id="v_rename")
    async def rename_voice(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await get_owned_channel(interaction)
        if not channel:
            return
        await interaction.response.send_modal(RenameModal(channel))

    @discord.ui.button(label="👥 Лимит", style=discord.ButtonStyle.secondary, custom_id="v_limit")
    async def limit_voice(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await get_owned_channel(interaction)
        if not channel:
            return
        await interaction.response.send_modal(LimitModal(channel))

    @discord.ui.button(label="👢 Кикнуть", style=discord.ButtonStyle.danger, custom_id="v_kick")
    async def kick_voice(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await get_owned_channel(interaction)
        if not channel:
            return
        await interaction.response.send_message("Выберите, кого кикнуть:", view=KickSelectView(channel), ephemeral=True)

    @discord.ui.button(label="👑 Передать права", style=discord.ButtonStyle.primary, custom_id="v_transfer")
    async def transfer_voice(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = await get_owned_channel(interaction)
        if not channel:
            return
        cog = get_cog(interaction)
        await interaction.response.send_message("Выберите нового владельца:", view=TransferSelectView(channel, cog), ephemeral=True)


class PrivateVoiceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_voices = {}  # {voice_channel_id: owner_id}

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        trigger_id = config.CHANNEL_IDS.get("VOICE_CREATE")

        # 1. Создание приватного войса при входе в триггер
        if after.channel and after.channel.id == trigger_id:
            category = after.channel.category
            new_chan = await member.guild.create_voice_channel(
                name=f"🔒 Приват {member.display_name}",
                category=category
            )
            self.active_voices[new_chan.id] = member.id
            await member.move_to(new_chan)

        # 2. Удаление пустого авто-созданного войса
        if before.channel and before.channel.id in self.active_voices:
            if len(before.channel.members) == 0:
                del self.active_voices[before.channel.id]
                try:
                    await before.channel.delete()
                except Exception:
                    pass

    @discord.app_commands.command(name="setup_voice_panel", description="Установить панель настройки войсов")
    async def setup_v_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🔊 Управление приватной комнатой",
            description=(
                "Зайдите в канал **'Создать комнату'**, затем используйте кнопки ниже, "
                "чтобы управлять вашей приваткой:\n\n"
                "🔒 **Закрыть/Открыть** — доступ для посторонних\n"
                "✏️ **Название** — переименовать комнату\n"
                "👥 **Лимит** — ограничить число участников\n"
                "👢 **Кикнуть** — выгнать участника из комнаты\n"
                "👑 **Передать права** — сделать владельцем другого"
            ),
            color=discord.Color.purple()
        )
        await interaction.channel.send(embed=embed, view=VoiceControlView())
        await interaction.response.send_message("Панель настроек войса установлена!", ephemeral=True)


async def setup(bot):
    await bot.add_cog(PrivateVoiceCog(bot))
    bot.add_view(VoiceControlView())  # чтобы кнопки жили и после перезапуска бота