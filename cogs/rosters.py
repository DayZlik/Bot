import os
import json
import discord
from discord.ext import commands, tasks
from datetime import date

# ==================== ВЕРТИКАЛЬНЫЙ БЛОК НАСТРОЕК ====================
CONFIG = {
    "dev_id": 421352414948622336,  # <-- ТВОЙ DISCORD ID
    "interval_hours": 1,           # Интервал автоматического обновления
    
    "sections": {
        "старший_состав": {
            "title": "Состав",
            "color": 0xA23EFF,
            "roles": {
                1446489339126218853: ["Owner", False, []], 
                1430913711979233312: ["Dep. Owner", False, []],         
                1430913754463207560: ["Winchester", True, []]
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

class RostersCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Динамически регистрируем команды разделов (!jd, !rm и т.д.) при инициализации
        for cmd_name in CONFIG["sections"].keys():
            self.bot.add_command(self.make_command(cmd_name))

    async def cog_load(self):
        # Запуск таски автообновления при загрузке модуля
        if not self.auto_update.is_running():
            self.auto_update.start()

    def cog_unload(self):
        # Важно: удаляем динамические команды при выгрузке кога, чтобы не было конфликтов
        self.auto_update.cancel()
        for cmd_name in CONFIG["sections"].keys():
            self.bot.remove_command(cmd_name)

    # ----------------- РАБОТА С БАЗОЙ ДАННЫХ (JSON) -----------------
    def load_saved_ids(self) -> dict:
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Ошибка чтения файла БД составов: {e}")
        return {}

    def save_ids(self, section_key: str, channel_id: int, message_id: int):
        data = self.load_saved_ids()
        data[section_key] = {"channel_id": channel_id, "message_id": message_id}
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Ошибка записи в файл БД составов: {e}")

    # ----------------- ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ -----------------
    async def notify_dev(self, text: str):
        if CONFIG["dev_id"] in (0, 123456789012345678):
            return print(f"[Лог]: {text}")
        try:
            user = self.bot.get_user(CONFIG["dev_id"]) or await self.bot.fetch_user(CONFIG["dev_id"])
            if user:
                await user.send(text)
        except Exception as e:
            print(f"Ошибка отправки лога разработчику в ЛС: {e}")

    def generate_embeds(self, guild: discord.Guild, key: str) -> list[discord.Embed]:
        section = CONFIG["sections"][key]
        lines = []
        seen_members = set() 
        
        for r_id, role_info in section["roles"].items():
            role = guild.get_role(r_id)
            if not role:
                self.bot.loop.create_task(self.notify_dev(f"⚠️ **Роль не найдена:** ID `{r_id}` в секции `{key}`."))
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

    async def run_global_sync(self) -> tuple[int, list[str]]:
        saved_data = self.load_saved_ids()
        success_count = 0
        errors = []
        
        for name in CONFIG["sections"].keys():
            if name not in saved_data:
                continue
                
            ch_id = saved_data[name].get("channel_id")
            msg_id = saved_data[name].get("message_id")
            
            try:
                ch = self.bot.get_channel(ch_id) or await self.bot.fetch_channel(ch_id)
                msg = await ch.fetch_message(msg_id)
                await msg.edit(embeds=self.generate_embeds(ch.guild, name))
                success_count += 1
            except Exception as e:
                errors.append(f"Ошибка в секции `!{name}` (ID сообщения: `{msg_id}`): {e}")
                
        return success_count, errors

    # ----------------- КОМАНДЫ МОДУЛЯ -----------------
    @commands.command(name="sync")
    @commands.has_permissions(administrator=True)
    async def sync_all_lists(self, ctx):
        await self.notify_dev(f"🔄 **Запущена ручная синхронизация всех составов с сервера `{ctx.guild.name}`...**")
        success, errors = await self.run_global_sync()
        
        result_text = f"✅ **Синхронизация успешно завершена!**\nОбновлено списков: `{success}` из `{len(CONFIG['sections'])}`."
        if errors:
            result_text += f"\n⚠️ Обнаружено ошибок: `{len(errors)}`."
            errors_text = "\n".join(errors)
            await self.notify_dev(f"{result_text}\n```python\n{errors_text}\n```")
        else:
            await self.notify_dev(result_text)

    def make_command(self, name: str):
        """Фабрика для генерации динамических команд разделов"""
        @commands.has_permissions(administrator=True)
        async def cmd(ctx):
            try:
                msg = await ctx.send(embeds=self.generate_embeds(ctx.guild, name))
                self.save_ids(name, ctx.channel.id, msg.id)
                await self.notify_dev(f"✅ **Эмбед `!{name}` успешно создан в канале <#{ctx.channel.id}>!**")
            except Exception as e:
                await self.notify_dev(f"💥 **Ошибка выполнения команды `!{name}`:**\n```python\n{e}\n```")
        return commands.Command(cmd, name=name)

    # ----------------- ТАСКИ И СЛУШАТЕЛИ -----------------
    @tasks.loop(hours=CONFIG["interval_hours"])
    async def auto_update(self):
        _, errors = await self.run_global_sync()
        if errors:
            errors_text = "\n".join(errors)
            await self.notify_dev(f"⚠️ **Ошибки при плановом автообновлении списков:**\n```python\n{errors_text}\n```")

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound): 
            return
        if isinstance(error, commands.MissingPermissions):
            await self.notify_dev(f"🔒 **Попытка доступа!**\nЮзер: {ctx.author.mention}\nКоманда: `{ctx.message.content}`")
            return
        await self.notify_dev(f"💥 **Ошибка команды `{ctx.command}`:**\n```python\n{error}\n```")

async def setup(bot):
    await bot.add_cog(RostersCog(bot))
