import os
import discord
from discord.ext import commands

# ИСПРАВЛЕНО: Правильный способ получения стандартных намерений
intents = discord.Intents.default()
intents.message_content = True  # Разрешаем боту читать текст сообщений

# Создаем экземпляр бота с префиксом команды '!'
bot = commands.Bot(command_prefix='!', intents=intents)

# Событие: бот успешно запустился и подключился к серверам
@bot.event
async def on_ready():
    print(f'Бот {bot.user.name} успешно запущен и готов к работе!')

# Команда !hello
@bot.command()
async def hello(ctx):
    await ctx.send(f'Привет, {ctx.author.name}! Тест хостинга прошел успешно! 👋')

# Запуск бота с использованием переменной окружения
if __name__ == "__main__":
    token = os.getenv('DISCORD_TOKEN')
    if token:
        bot.run(token)
    else:
        print("Ошибка: Переменная окружения 'DISCORD_TOKEN' не найдена!")
