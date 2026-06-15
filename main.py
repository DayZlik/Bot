import os
import discord
from discord.ext import commands, tasks  # Подключили модуль задач по таймеру

# ==================== БЛОК НАСТРОЕК (КОНФИГУРАЦИЯ) ====================
BOT_CONFIG = {
    "prefix": "!",  # Командный префикс бота
    
    # --- НАСТРОЙКИ АВТО-ОБНОВЛЕНИЯ ---
    "update_interval_hours": 6,  # Как часто обновлять состав (в часах)
    
    # Сюда нужно будет вставить ID ПОСЛЕ того, как вызовешь команду !создать_состав
    "target_channel_id": 0,      # Замени на ID канала, когда получишь его от бота
    "target_message_id": 0,      # Замени на ID сообщения, когда получишь его от бота
    # ---------------------------------

    "embed": {
        "title": "📋 | Старший Состав",
        "color": 0xE74C3C,  # Красный цвет полоски
        "empty_text": "— Нет участников —",
        "bullet": "•"
    },
    
    "roles": [
        {"id": 1516122208974536866, "name_override": "Генеральный Директор"},
        {"id": 1516122249529393263, "name_override": "Зам. Директора"},
        {"id": 1516122280780890172, "name_override": "Главный Редактор"},
        {"id": 1516122325270139031, "name_override": "Зам. Главного Редактора"},
        {"id": 1516122352373731339, "name_override": "Ассистенты Директора"},
        {"id": 1516122857145634968, "name_override": "Куратор JD"}
    ]
}
# ======================================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=BOT_CONFIG["prefix"], intents=intents)


def generate_staff_embed(guild: discord.Guild) -> discord.Embed:
    """Функция сборки эмбеда (осталась прежней)"""
    embed_settings = BOT_CONFIG["embed"]
    embed = discord.Embed(title=embed_settings["title"], color=discord.Color(embed_settings["color"]))
    description_lines = []
    
    for role_info in BOT_CONFIG["roles"]:
        role = guild.get_role(role_info["id"])
        if not role:
            print(f"Предупреждение: Роль с ID {role_info['id']} не найдена.")
            continue
            
        role_name = role_info["name_override"] if role_info["name_override"] else role.name
        description_lines.append(f"**{role_name}**")
        
        if role.members:
            for member in role.members:
                description_lines.append(f"{embed_settings['bullet']} {member.mention}")
        else:
            description_lines.append(embed_settings["empty_text"])
            
        description_lines.append("")
        
    embed.description = "\n".join(description_lines)
    return embed


# ==================== АВТО-ОБНОВЛЕНИЕ ПО ТАЙМЕРУ ====================
@tasks.loop(hours=BOT_CONFIG["update_interval_hours"])
async def auto_update_staff():
    channel_id = BOT_CONFIG["target_channel_id"]
    message_id = BOT_CONFIG["target_message_id"]
    
    # Если ID еще не настроены, просто ничего не делаем
    if channel_id == 0 or message_id == 0:
        return
        
    print("[Лог] Начинаю автоматическое обновление состава...")
    try:
        # Находим канал (сначала в кэше, если нет — запрашиваем у Discord)
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        # Находим то самое сообщение, которое нужно отредактировать
        message = await channel.fetch_message(message_id)
        
        # Генерируем новый актуальный эмбед
        new_embed = generate_staff_embed(channel.guild)
        
        # Редактируем старое сообщение, заменяя эмбед на новый
        await message.edit(embed=new_embed)
        print("[Лог] Состав успешно обновлен по таймеру!")
    except Exception as e:
        print(f"[Ошибка] Не удалось автоматически обновить состав: {e}")


@bot.event
async def on_ready():
    print(f'Бот {bot.user.name} запущен!')
    
    # Запускаем цикл авто-обновления, если он еще не запущен
    if not auto_update_staff.is_running():
        auto_update_staff.start()
        print(f"Цикл авто-обновления запущен! Интервал: {BOT_CONFIG['update_interval_hours']} ч.")
# ======================================================================


@bot.command(name="создать_состав")
@commands.has_permissions(administrator=True)
async def create_staff_msg(ctx):
    """Команда для ПЕРВОЙ отправки сообщения. Бот выдаст ID, которые нужно сохранить."""
    try:
        # Создаем и отправляем эмбед
        embed = generate_staff_embed(ctx.guild)
        sent_message = await ctx.send(embed=embed)
        
        # Выводим подсказку для администратора
        setup_info = (
            "✅ **Сообщение с составом успешно создано!**\n\n"
            "Чтобы включить авто-обновление, скопируй эти данные и вставь в `BOT_CONFIG` вашего кода:\n"
            f'`"target_channel_id": {ctx.channel.id},`\n'
            f'`"target_message_id": {sent_message.id},`\n\n'
            "После изменения кода на хостинге, обязательно перезапусти бота!"
        )
        # Отправляем это сообщение автору команды в ЛС или прямо в чат (тут отправка в чат)
        await ctx.send(setup_info, delete_after=60) # Удалится через минуту, чтобы не засорять чат
        
    except Exception as e:
        await ctx.send(f"❌ Ошибка: {e}")


if __name__ == "__main__":
    token = os.getenv('DISCORD_TOKEN')
    if token:
        bot.run(token)
    else:
        print("Ошибка: Переменная окружения 'DISCORD_TOKEN' не найдена!")
