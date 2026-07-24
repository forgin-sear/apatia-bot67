import discord
from discord.ext import commands
import os
import asyncio
from flask import Flask
from threading import Thread
import config

# --- МИНИ ВЕБ-СЕРВЕР ДЛЯ RENDER ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()
# ----------------------------------

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Список cog-модулей, которые загружаются при старте.
# Если положишь файлы в папку cogs/ — не меняй пути.
INITIAL_EXTENSIONS = [
    "cogs.afk",
    "cogs.applications",
    "cogs.private_voice",
    "cogs.welcome",
    "cogs.mp_signup",
    "cogs.vacation",
    "cogs.rules",
    "cogs.roster",
]

# Если задать GUILD_ID в Environment Variables на Render — слэш-команды
# появятся почти мгновенно (гильд-синк). Без него — до часа (глобальный синк).
GUILD_ID = os.getenv("GUILD_ID")


@bot.event
async def on_guild_join(guild: discord.Guild):
    """
    Страховка от 'угона' бота: если его всё-таки добавили не туда,
    куда нужно (список ALLOWED_GUILD_IDS в config.py) — бот сам
    покидает такой сервер, не дожидаясь ручного вмешательства.
    """
    allowed = getattr(config, "ALLOWED_GUILD_IDS", [])
    if allowed and guild.id not in allowed:
        print(f"⚠️ Бота добавили на посторонний сервер '{guild.name}' (ID: {guild.id}) — выхожу.")
        try:
            await guild.leave()
        except Exception as e:
            print(f"❌ Не удалось покинуть сервер {guild.id}: {e}")


@bot.event
async def on_ready():
    print(f'🔥 Бот {bot.user.name} успешно запущен!')

    try:
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            bot.tree.copy_global_to(guild=guild)  # <-- копируем глобальные команды в гильдию
            synced = await bot.tree.sync(guild=guild)
            print(f'⚡ Синхронизировано {len(synced)} слэш-команд для гильдии {GUILD_ID}')
        else:
            synced = await bot.tree.sync()
            print(f'⚡ Синхронизировано {len(synced)} слэш-команд глобально (может занять до 1 часа)')
    except Exception as e:
        print(f'❌ Ошибка синхронизации команд: {e}')


async def load_extensions():
    for ext in INITIAL_EXTENSIONS:
        try:
            await bot.load_extension(ext)
            print(f'✅ Загружен модуль: {ext}')
        except Exception as e:
            print(f'❌ Не удалось загрузить {ext}: {e}')


async def main():
    keep_alive()  # Запускаем веб-сервер
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("❌ ОШИБКА: BOT_TOKEN не найден в Environment Variables!")
        return

    await load_extensions()
    await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
