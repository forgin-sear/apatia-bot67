# cogs/rules.py
import discord
from discord.ext import commands
import config
from .utils import temp_reply


def build_rules_embed() -> discord.Embed:
    leader = config.LEADERSHIP_IDS.get("LEADER")
    dep1 = config.LEADERSHIP_IDS.get("DEPUTY_1")
    dep2 = config.LEADERSHIP_IDS.get("DEPUTY_2")

    text = (
        "**1. Общение**\n"
        "Материться можно, без фанатизма — но материть (оскорблять) конкретного участника нельзя. "
        "За переход на личности — наказание на усмотрение модерации.\n\n"

        "**2. Ник в Discord**\n"
        "Обязателен формат: `Имя Фамилия | Статик`.\n\n"

        "**3. АФК**\n"
        "Если ваш персонаж находится в игре, а вы отошли (смотрите видео, отвлеклись и т.п.) и НЕ отметились "
        "через панель АФК — выдаётся **НВС**.\n\n"

        "**4. Семейные МП (капты)**\n"
        "Во время фам-МП флуд не по теме — **мут**.\n\n"

        "**5. Испытательный срок**\n"
        "» **КРАЙМ** — 3 дня.\n"
        "» **РП СТАК** — 24 часа.\n"
        "Продлить срок можно, написав в свою ветку куратору направления (РП СТАК или КРАЙМ).\n\n"

        "**6. Обязанности по направлениям**\n"
        "» **РП СТАК** — делаете контракты Грин, участие в фам-контрактах обязательно "
        "(пакеты Грин доступны 24/7 в наборах).\n"
        "» **КРАЙМ** — обязательна явка на капты (фам-МП) и на контракты, если зовут.\n\n"

        "**7. Наказания**\n"
        "Банов пока нет. За нарушение п.3 — **НВС**. **Кик** — на усмотрение хай-состава, по ситуации.\n\n"

        "**8. Иерархия**\n"
        f"Лидер — {f'<@{leader}>' if leader else '—'}\n"
        f"Заместители — {f'<@{dep1}>' if dep1 else '—'}, {f'<@{dep2}>' if dep2 else '—'}\n"
        "По всем важным вопросам — к ним."
    )

    embed = discord.Embed(
        title="📜 Правила семьи APATIA",
        description=text,
        color=discord.Color.dark_red()
    )
    embed.set_footer(text="Нажмите кнопку ниже, чтобы подтвердить, что ознакомились, и получить роль.")
    return embed


class RulesConfirmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ Я ознакомился с правилами", style=discord.ButtonStyle.success, custom_id="rules_confirm")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        apatia_role = interaction.guild.get_role(config.ROLE_IDS.get("APATIA"))
        awaiting_role = interaction.guild.get_role(config.ROLE_IDS.get("AWAITING_RULES"))

        if not apatia_role or not awaiting_role:
            return await interaction.response.send_message(
                "❌ Роли APATIA/AWAITING_RULES не настроены, скажи хай-рангу проверить config.py!", ephemeral=True
            )

        if apatia_role in interaction.user.roles:
            return await interaction.response.send_message("Вы уже подтвердили правила ранее!", ephemeral=True)

        if awaiting_role not in interaction.user.roles:
            return await interaction.response.send_message(
                "Эта кнопка доступна только после того, как вашу заявку одобрят — сначала подайте заявку!",
                ephemeral=True
            )

        try:
            await interaction.user.remove_roles(awaiting_role)
            await interaction.user.add_roles(apatia_role)
        except Exception as e:
            return await interaction.response.send_message(f"❌ Не удалось выдать роль: {e}", ephemeral=True)

        await temp_reply(interaction, "✅ Спасибо! Добро пожаловать в APATIA 🥀")


class RulesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="setup_rules", description="Установить панель правил с кнопкой подтверждения")
    async def setup_rules(self, interaction: discord.Interaction):
        await interaction.channel.send(embed=build_rules_embed(), view=RulesConfirmView())
        await temp_reply(interaction, "Панель правил установлена!")


async def setup(bot):
    await bot.add_cog(RulesCog(bot))
    bot.add_view(RulesConfirmView())  # чтобы кнопка жила и после рестарта бота
