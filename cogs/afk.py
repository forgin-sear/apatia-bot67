# cogs/afk.py
import discord
from discord.ext import commands
import config
from .utils import temp_reply

# Локальная база данных АФК: {user_id: {"time": "...", "reason": "..."}}
afk_database = {}

class AfkModal(discord.ui.Modal, title="Форма ухода в АФК"):
    time_str = discord.ui.TextInput(
        label="Срок АФК (До какого числа / времени)", 
        placeholder="До 25.07 / 2 дня",
        required=True
    )
    reason = discord.ui.TextInput(
        label="Причина АФК", 
        placeholder="Отпуск / Работа / Учеба",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        afk_database[interaction.user.id] = {
            "time": self.time_str.value,
            "reason": self.reason.value
        }

        cog = interaction.client.get_cog("AfkCog")
        if cog:
            await cog.update_afk_board(interaction.guild)

        await temp_reply(interaction, "Вы успешно занесены в список АФК!")


class AfkControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Уйти в АФК", style=discord.ButtonStyle.primary, custom_id="btn_go_afk")
    async def go_afk(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AfkModal())

    @discord.ui.button(label="Вернуться из АФК", style=discord.ButtonStyle.success, custom_id="btn_back_afk")
    async def back_afk(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in afk_database:
            del afk_database[interaction.user.id]
            await temp_reply(interaction, "Вы успешно убраны из списка АФК!")
            cog = interaction.client.get_cog("AfkCog")
            if cog:
                await cog.update_afk_board(interaction.guild)
        else:
            await interaction.response.send_message("Вас нет в списке АФК!", ephemeral=True)

    @discord.ui.button(label="🚨 ВЫЗВАТЬ ВСЕХ В ИГРУ (High)", style=discord.ButtonStyle.danger, custom_id="btn_ping_afk")
    async def ping_all_afk(self, interaction: discord.Interaction, button: discord.ui.Button):
        high_role = interaction.guild.get_role(config.ROLE_IDS.get("HIGH"))
        is_high_or_above = high_role and interaction.user.top_role.position >= high_role.position
        if not (is_high_or_above or interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message(
                "Эта кнопка доступна только от роли **High** и выше!", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        if not afk_database:
            return await interaction.followup.send("В АФК сейчас никого нет!", ephemeral=True)

        count = 0
        for user_id in list(afk_database.keys()):
            member = interaction.guild.get_member(user_id)
            if member:
                try:
                    await member.send("⚠️ **ВНИМАНИЕ!** Руководство семьи просит вас зайти в игру! Вы находитесь в АФК слишком долго.")
                    count += 1
                except Exception:
                    pass

        await temp_reply(interaction, f"🔔 Сообщение с вызовом в игру отправлено **{count}** участникам из АФК!")


class AfkCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.board_message_id = None

    async def update_afk_board(self, guild: discord.Guild):
        channel_id = config.CHANNEL_IDS.get("AFK")
        if not channel_id:
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            return

        embed = discord.Embed(
            title="🏝️ СПИСОК УЧАСТНИКОВ В АФК",
            color=discord.Color.blue()
        )

        if not afk_database:
            embed.description = "*В данный момент никто не сидит в АФК.*"
        else:
            desc = ""
            for uid, info in afk_database.items():
                desc += f"👤 <@{uid}> — **Срок:** {info['time']} | **Причина:** {info['reason']}\n"
            embed.description = desc

        embed.set_footer(text="Нажмите кнопку ниже, чтобы уйти или выйти из АФК.")

        if self.board_message_id:
            try:
                msg = await channel.fetch_message(self.board_message_id)
                await msg.edit(embed=embed, view=AfkControlView())
                return
            except Exception:
                pass

        msg = await channel.send(embed=embed, view=AfkControlView())
        self.board_message_id = msg.id

    @discord.app_commands.command(name="setup_afk", description="Создать табло АФК")
    async def setup_afk(self, interaction: discord.Interaction):
        await self.update_afk_board(interaction.guild)
        await temp_reply(interaction, "Табло АФК инициализировано!")

async def setup(bot):
    await bot.add_cog(AfkCog(bot))
    bot.add_view(AfkControlView())  # чтобы кнопки жили и после перезапуска бота