import discord
from discord.ext import commands
import os
import asyncio

# Включаем все интенты для корректного чтения ролей и участников
intents = discord.Intents.all()

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"==========================================")
    print(f"🔥 Бот запущен как: {bot.user.name}#{bot.user.discriminator}")
    print(f"🆔 ID бота: {bot.user.id}")
    print(f"==========================================")

async def load_extensions():
    """Автоматически сканирует папку cogs и загружает все модули"""
    if not os.path.exists("./cogs"):
        os.makedirs("./cogs")
        print("📁 Папка './cogs' отсутствовала и была успешно создана.")

    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            try:
                await bot.load_extension(f"cogs.{filename[:-3]}")
                print(f"✅ Модуль успешно загружен: cogs.{filename[:-3]}")
            except Exception as e:
                print(f"❌ Не удалось загрузить модуль cogs.{filename[:-3]} | Ошибка: {e}")

async def main():
    async with bot:
        await load_extensions()
        # Вместо os.getenv можно вставить токен строкой, если не используешь .env environment
        await bot.start(os.getenv('DISCORD_TOKEN') or "ТВОЙ_ТОКЕН_СЮДА")

if __name__ == "__main__":
    asyncio.run(main())
