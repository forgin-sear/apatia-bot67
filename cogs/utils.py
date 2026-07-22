# cogs/utils.py
"""
Общие хелперы для всех когов.

Идея: обычные "успешные" уведомления бота (эфемерные сообщения вида
"Готово!", "Комната переименована!" и т.п.) не должны висеть и требовать
ручного закрытия — они сами исчезают через несколько секунд.

Сообщения об ОШИБКАХ/предупреждения (нет прав, неверный ввод и т.д.)
через обычный interaction.response.send_message(...) не трогаем —
они как были, так и остаются, пока юзер сам их не закроет, чтобы человек
успел прочитать, что пошло не так.

Примечание про надпись Discord "нажмите, чтобы убрать" — это фишка
самого клиента Discord для любых эфемерных сообщений, её нельзя убрать
кодом бота. Но если сообщение исчезает само через 5 секунд, эта
проблема на практике перестаёт быть проблемой.
"""
import asyncio
import discord


def schedule_delete(message, delay: int = 5):
    """Планирует тихое удаление уже отправленного/отредактированного сообщения."""
    if message is None:
        return

    async def _later():
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except Exception:
            pass

    asyncio.create_task(_later())


async def temp_reply(interaction: discord.Interaction, content: str = None, *,
                      embed: discord.Embed = None, view: discord.ui.View = None,
                      ephemeral: bool = True, delay: int = 5):
    """
    Замена interaction.response.send_message(...) / interaction.followup.send(...)
    для сообщений-подтверждений, которые не нужно оставлять висеть.

    Сама разбирается, был ли уже дан ответ на interaction (defer/edit) —
    и шлёт либо через response, либо через followup.
    """
    kwargs = {"ephemeral": ephemeral}
    if content is not None:
        kwargs["content"] = content
    if embed is not None:
        kwargs["embed"] = embed
    if view is not None:
        kwargs["view"] = view

    if interaction.response.is_done():
        msg = await interaction.followup.send(**kwargs)
    else:
        await interaction.response.send_message(**kwargs)
        try:
            msg = await interaction.original_response()
        except Exception:
            msg = None

    schedule_delete(msg, delay)
    return msg


async def temp_edit(interaction: discord.Interaction, content: str = None, *,
                     embed: discord.Embed = None, view: discord.ui.View = None,
                     delay: int = 5):
    """
    Замена interaction.response.edit_message(...) (используется в Select-меню)
    для финальных статусных сообщений — после показа результата исчезает само.
    """
    await interaction.response.edit_message(content=content, embed=embed, view=view)
    try:
        msg = await interaction.original_response()
    except Exception:
        msg = None
    schedule_delete(msg, delay)
    return msg


async def temp_edit_original(interaction: discord.Interaction, content: str = None, *,
                              embed: discord.Embed = None, view: discord.ui.View = None,
                              delay: int = 5):
    """
    Замена interaction.edit_original_response(...) — используется там, где
    interaction уже был deferred раньше (например, после response.defer()).
    """
    msg = await interaction.edit_original_response(content=content, embed=embed, view=view)
    schedule_delete(msg, delay)
    return msg
