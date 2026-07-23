# cogs/mp_signup.py
import discord
from discord.ext import commands
import config
from .utils import temp_reply


def has_high_rank_access(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    ids = {
        config.ROLE_IDS.get("HIGH"),
        config.ROLE_IDS.get("DEP_OWN"),
        config.ROLE_IDS.get("OWNER"),
        config.ROLE_IDS.get("LEADER"),
    }
    return any(r.id in ids for r in member.roles)


def build_signup_embed(data: dict) -> discord.Embed:
    lines = [f"⏰ **Время:** {data['time']}", ""]

    main_count = len(data["main"])
    lines.append(f"**Основной список ({main_count}/{data['main_slots']})**")
    if data["main"]:
        lines.extend(f"{i + 1}) <@{uid}>" for i, uid in enumerate(data["main"]))
    else:
        lines.append("_Пока никто не записался_")

    if data["reserve_slots"] > 0:
        reserve_count = len(data["reserve"])
        lines.append("")
        lines.append(f"**Замена ({reserve_count}/{data['reserve_slots']})**")
        if data["reserve"]:
            lines.extend(f"{i + 1}) <@{uid}>" for i, uid in enumerate(data["reserve"]))
        else:
            lines.append("_Пусто_")

    return discord.Embed(
        title=f"📋 Запись на: {data['title']}",
        description="\n".join(lines),
        color=discord.Color.blurple()
    )


class MPCreateModal(discord.ui.Modal, title="Новая запись на МП"):
    mp_title = discord.ui.TextInput(label="Название МП", placeholder="CPT VS SPAZE")
    time_str = discord.ui.TextInput(label="Время", placeholder="17:33 22.07.2026")
    main_slots = discord.ui.TextInput(label="Кол-во основных мест", placeholder="35")
    reserve_slots = discord.ui.TextInput(
        label="Кол-во мест в замене (0 = без замены)", placeholder="3", required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            main_slots = int(str(self.main_slots.value))
            if main_slots <= 0 or main_slots > 99:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                "❌ Кол-во основных мест должно быть числом от 1 до 99!", ephemeral=True
            )

        reserve_raw = str(self.reserve_slots.value).strip()
        reserve_slots = 0
        if reserve_raw:
            try:
                reserve_slots = int(reserve_raw)
                if reserve_slots < 0 or reserve_slots > 99:
                    raise ValueError
            except ValueError:
                return await interaction.response.send_message(
                    "❌ Кол-во мест в замене должно быть числом от 0 до 99!", ephemeral=True
                )

        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        signup_channel = guild.get_channel(config.CHANNEL_IDS.get("MP_SIGNUP"))
        ping_channel = guild.get_channel(config.CHANNEL_IDS.get("MP_PING"))

        if not signup_channel:
            return await temp_reply(interaction, "❌ Канал для записи не найден, проверь config.py!")

        data = {
            "title": str(self.mp_title.value),
            "time": str(self.time_str.value),
            "main_slots": main_slots,
            "reserve_slots": reserve_slots,
            "main": [],
            "reserve": [],
        }

        msg = await signup_channel.send(embed=build_signup_embed(data), view=SignupControlView())

        cog = interaction.client.get_cog("MPSignupCog")
        if cog:
            cog.signups[msg.id] = data

        if ping_channel:
            role_mentions = []
            main_role = guild.get_role(config.ROLE_IDS.get("MAIN"))
            apatia_role = guild.get_role(config.ROLE_IDS.get("APATIA"))
            if main_role:
                role_mentions.append(main_role.mention)
            if apatia_role:
                role_mentions.append(apatia_role.mention)
            tag_line = " ".join(role_mentions)

            ping_embed = discord.Embed(
                description=(
                    f"🔔 **Открыта регистрация на МП: {data['title']}**\n"
                    f"⏰ Время: {data['time']}\n"
                    f"🔥 Успевайте занять место — свободные слоты разбирают быстро!\n"
                    f"📍 Регистрация: {msg.jump_url}"
                ),
                color=discord.Color.orange()
            )
            await ping_channel.send(
                content=tag_line,
                embed=ping_embed,
                allowed_mentions=discord.AllowedMentions(roles=True)
            )

        await temp_reply(interaction, "✅ Запись создана, уведомление разослано!")


class SignupControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ Зарегистрироваться", style=discord.ButtonStyle.success, custom_id="mp_join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("MPSignupCog")
        if not cog or interaction.message.id not in cog.signups:
            return await interaction.response.send_message("Эта запись больше не активна.", ephemeral=True)

        data = cog.signups[interaction.message.id]
        uid = interaction.user.id

        if uid in data["main"] or uid in data["reserve"]:
            return await interaction.response.send_message("Вы уже записаны!", ephemeral=True)

        if len(data["main"]) < data["main_slots"]:
            data["main"].append(uid)
            place = "основной список"
        elif data["reserve_slots"] > 0 and len(data["reserve"]) < data["reserve_slots"]:
            data["reserve"].append(uid)
            place = "замену"
        else:
            return await interaction.response.send_message(
                "Свободных мест не осталось (ни в основном списке, ни в замене)!", ephemeral=True
            )

        await interaction.response.edit_message(embed=build_signup_embed(data))
        await temp_reply(interaction, f"✅ Вы записаны в {place}!")

    @discord.ui.button(label="❌ Отсоединиться", style=discord.ButtonStyle.danger, custom_id="mp_leave")
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("MPSignupCog")
        if not cog or interaction.message.id not in cog.signups:
            return await interaction.response.send_message("Эта запись больше не активна.", ephemeral=True)

        data = cog.signups[interaction.message.id]
        uid = interaction.user.id

        if uid in data["main"]:
            data["main"].remove(uid)
            if data["reserve"]:
                promoted = data["reserve"].pop(0)
                data["main"].append(promoted)
        elif uid in data["reserve"]:
            data["reserve"].remove(uid)
        else:
            return await interaction.response.send_message("Вы и так не записаны на это МП!", ephemeral=True)

        await interaction.response.edit_message(embed=build_signup_embed(data))
        await temp_reply(interaction, "❎ Вы отписались от записи.")


class MPPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📋 Создать запись на МП", style=discord.ButtonStyle.primary, custom_id="mp_open_create")
    async def open_create(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_high_rank_access(interaction.user):
            return await interaction.response.send_message(
                "Создавать запись на МП могут только хай-ранги!", ephemeral=True
            )
        await interaction.response.send_modal(MPCreateModal())


class MPSignupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.signups = {}  # message_id -> {title, time, main_slots, reserve_slots, main[], reserve[]}
        # ⚠️ Хранится в памяти — при рестарте бота активные записи (и кто куда записан) сбросятся,
        # сами сообщения в канале останутся, но кнопки на них перестанут работать со старыми данными.

    @discord.app_commands.command(name="setup_mp_panel", description="Установить панель создания записи на МП")
    async def setup_mp_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📋 Запись на МП",
            description=(
                "Нажмите кнопку ниже, чтобы открыть регистрацию на новое МП.\n"
                "Доступно только хай-рангам (High и выше)."
            ),
            color=discord.Color.blurple()
        )
        await interaction.channel.send(embed=embed, view=MPPanelView())
        await temp_reply(interaction, "Панель создания записи на МП установлена!")


async def setup(bot):
    await bot.add_cog(MPSignupCog(bot))
    bot.add_view(MPPanelView())        # чтобы кнопка "Создать запись" жила и после рестарта
    bot.add_view(SignupControlView())  # чтобы кнопки записи/отписки жили и после рестарта
