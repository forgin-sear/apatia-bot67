# cogs/private_voice.py
import discord
from discord.ext import commands
import config

class VoiceControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Закрыть/Открыть", style=discord.ButtonStyle.secondary, custom_id="v_lock")
    async def lock_voice(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message("Вы должны находиться в своем приватном канале!", ephemeral=True)

        channel = interaction.user.voice.channel
        overwrite = channel.overwrites_for(interaction.guild.default_role)
        
        if overwrite.connect is False:
            overwrite.connect = None
            await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
            await interaction.response.send_message("🔓 Комната открыта для всех!", ephemeral=True)
        else:
            overwrite.connect = False
            await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
            await interaction.response.send_message("🔒 Комната закрыта от посторонних!", ephemeral=True)


class PrivateVoiceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_voices = {}  # {voice_id: owner_id}

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
            description="Зайдите в канал **'Создать комнату'**, затем используйте кнопки ниже для управления вашей приваткой.",
            color=discord.Color.purple()
        )
        await interaction.channel.send(embed=embed, view=VoiceControlView())
        await interaction.response.send_message("Панель настроек войса установлена!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(PrivateVoiceCog(bot))