import os
import json
import discord
from discord.ext import commands, tasks

# ==================== ВЕРТИКАЛЬНЫЙ БЛОК НАСТРОЕК ====================
CONFIG = {
    "dev_id": 421352414948622336,  # <-- ТВОЙ DISCORD ID (сюда придут логи синхронизации)
    "interval_hours": 6,           # Интервал автоматического обновления
    
    "sections": {
        "старший_состав": {
            "title": "📋 | Старший Состав",
            "color": 0xE74C3C,
            "roles": {
                111111111111111111: ["Генеральный Директор", False, []], 
                222222222222222222: ["Зам. Директора", True, []],         
                333333333333333333: ["Исполнительный Директор", True, []]
            }
        },
        "jd": {
            "title": "💼 | Подразделение JD",
            "color": 0x3498DB,
            "roles": {
                948666656132051025: ["Куратор JD", False, []],
                959893836669284383: ["Сотрудник JD", True, []] 
            }
        },
        "rm": {
            "title": "🚗 | Подразделение RM",
            "color": 0x2ECC71,
            "roles": {
                666666666666666666: ["Глава RM", False, []],
                777777777777777777: ["Зам. Главы RM", True, []]
            }
        },
        "ad": {
            "title": "📢 | Подразделение AD",
            "color": 0xF1C40F,
            "roles": {
                888888888888888888: ["Глава AD", False, []]
            }
        },
        "ed": {
            "title": "🎓 | Подразделение ED",
            "color": 0x9B59B6,
            "roles": {
                999999999999999999: ["Глава ED", False, []]
            }
        },
        "bm": {
            "title": "📊 | Подразделение BM",
            "color": 0x34495E,
            "roles": {
                101010101010101010: ["Глава BM", False, []]
            }
        },
        "контракты": {
            "title": "📜 | Действующие Контракты",
            "color": 0xE67E22,
            "roles": {
                202020202020202020: ["Contr. press", False, []],
                303030303030303030: ["Contr. blogs", False, []]
            }
        }
    }
}
DATA_FILE = "bot_state.json"
# ==============================================================================

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

# ----------------- РАБОТА С БАЗОЙ ДАННЫХ (JSON) -----------------
def load_saved_ids() -> dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Ошибка чтения файла БД: {e}")
    return {}

def save_ids(section_key: str, channel_id: int, message_id: int):
    data = load_saved_ids()
    data[section_key] = {"channel_id": channel_id, "message_id": message_id}
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Ошибка записи в файл БД: {e}")
# ------------------------------------------------------------------

async def notify_dev(text: str):
    if CONFIG["dev_id"] in (0, 123456789012345678):
        return print(f"[Лог]: {text}")
    try:
        user = bot.get_user(CONFIG["dev_id"]) or await bot.fetch_user(CONFIG["dev_id"])
        if user:
            await user.send(text)
    except Exception as e:
        print(f"Ошибка отправки в ЛС: {e}")


def generate_embeds(guild: discord.Guild, key: str) -> list[discord.Embed]:
    section = CONFIG["sections"][key]
    lines = []
    seen_members = set() 
    
    for r_id, role_info in section["roles"].items():
        role = guild.get_role(r_id)
        if not role:
            bot.loop.create_task(notify_dev(f"⚠️ **Роль не найдена:** ID `{r_id}` в секции `{key}`."))
            continue
            
        custom_name, filter_duplicates, blacklist_roles = role_info
        valid_members = []
        
        for member in role.members:
            if blacklist_roles and any(member.get_role(b_id) for b_id in blacklist_roles):
                continue
            if filter_duplicates and member.id in seen_members:
                continue
            valid_members.append(member)
            seen_members.add(member.id)

        lines.append(f"**{custom_name or role.name}**")
        lines.extend([f"• {m.mention}" for m in valid_members] if valid_members else ["— Нет участников —"])
        lines.append("")

    embeds, current_text = [], ""
    for line in lines:
        if len(current_text) + len(line) + 1 > 4000:
            embeds.append(discord.Embed(color=section["color"], description=current_text))
            current_text = line
        else:
            current_text = f"{current_text}\n{line}" if current_text else line
            
    if current_text:
        embeds.append(discord.Embed(color=section["color"], description=current_text))
        
    total_staff = len(seen_members)
    embeds[0].title = section["title"]
    
    embeds[-1].set_footer(
        text=f"{total_staff} сотрудников • Автообновление: каждые {CONFIG['interval_hours']} ч."
    )
    embeds[-1].timestamp = discord.utils.utcnow()
    return embeds


async def run_global_sync() -> tuple[int, list[str]]:
    saved_data = load_saved_ids()
    success_count = 0
    errors = []
    
    for name in CONFIG["sections"].keys():
        if name not in saved_data:
            continue
            
        ch_id = saved_data[name].get("channel_id")
        msg_id = saved_data[name].get("message_id")
        
        try:
            ch = bot.get_channel(ch_id) or await bot.fetch_channel(ch_id)
            msg = await ch.fetch_message(msg_id)
            await msg.edit(embeds=generate_embeds(ch.guild, name))
            success_count += 1
        except Exception as e:
            errors.append(f"Ошибка в секции `!{name}` (ID сообщения: `{msg_id}`): {e}")
            
    return success_count, errors


# ----------------- КОМАНДЫ ДЛЯ АДМИНИСТРАЦИИ -----------------

@bot.command(name="sync")
@commands.has_permissions(administrator=True)
async def sync_all_lists(ctx):
    # Оповещение о начале процесса отправляется разработчику в ЛС
    await notify_dev(f"🔄 **Запущена ручная синхронизация всех составов с сервера `{ctx.guild.name}`...**")
    
    success, errors = await run_global_sync()
    
    result_text = f"✅ **Синхронизация успешно завершена!**\nОбновлено списков: `{success}` из `{len(CONFIG['sections'])}`."
    if errors:
        result_text += f"\n⚠️ Обнаружено ошибок: `{len(errors)}`."
        errors_text = "\n".join(errors)
        # ИСПРАВЛЕНО: Закрывающие кавычки f-строки и блока кода расставлены верно
        await notify_dev(f"{result_text}\n```python\n{errors_text}\n```")
    else:
        await notify_dev(result_text)


def make_command(name: str):
    @commands.has_permissions(administrator=True)
    async def cmd(ctx):
        try:
            msg = await ctx.send(embeds=generate_embeds(ctx.guild, name))
            save_ids(name, ctx.channel.id, msg.id)
            await notify_dev(f"✅ **Эмбед `!{name}` успешно создан в канале <#{ctx.channel.id}>!**")
        except Exception as e:
            await notify_dev(f"💥 **Ошибка выполнения команды `!{name}`:**\n```python\n{e}\n```")
    return commands.Command(cmd, name=name)
# --------------------------------------------------------------


@tasks.loop(hours=CONFIG["interval_hours"])
async def auto_update():
    _, errors = await run_global_sync()
    if errors:
        errors_text = "\n".join(errors)
        await notify_dev(f"⚠️ **Ошибки при плановом автообновлении списков:**\n```python\n{errors_text}\n```")


@bot.event
async def on_ready():
    print(f'Бот {bot.user.name} успешно запущен и готов к работе!')
    if not auto_update.is_running():
        auto_update.start()

for cmd_name in CONFIG["sections"].keys():
    bot.add_command(make_command(cmd_name))

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound): return
    if isinstance(error, commands.MissingPermissions):
        await notify_dev(f"🔒 **Попытка доступа!**\nЮзер: {ctx.author.mention}\nКоманда: `{ctx.message.content}`")
        return
    await notify_dev(f"💥 **Ошибка команды `{ctx.command}`:**\n```python\n{error}\n```")

if __name__ == "__main__":
    bot.run(os.getenv('DISCORD_TOKEN'))
