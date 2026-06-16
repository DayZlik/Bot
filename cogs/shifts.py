import discord
from discord.ext import commands
import aiosqlite
from datetime import date, datetime, timedelta, timezone

# ==================== БЛОК НАСТРОЕК СМЕН ====================
CONFIG = {
    "bm": {
        "role_id": 101010101010101010,        
        "curator_role_id": 111222333444555,   
        "slots": ["07:00", "15:00", "23:00"]  
    },    
    "ad": {
        "role_id": 888888888888888888,        
        "curator_role_id": 555666777888999,   
        "slots": [
            "13:00 - 13:59", "14:00 - 14:59", "15:00 - 15:59", "16:00 - 16:59",
            "17:00 - 17:59", "18:00 - 18:59", "19:00 - 19:59", "20:00 - 20:59",
            "21:00 - 21:59", "22:00 - 22:59", "23:00 - 23:59", "00:00 - 00:59"
        ] 
    },    
    "24ad": {
        "role_id": 888888888888888888,        
        "curator_role_id": 555666777888999,   
        "slots": [
            "00:00 - 00:59", "01:00 - 01:59", "02:00 - 02:59", "03:00 - 03:59",
            "04:00 - 04:59", "05:00 - 05:59", "06:00 - 06:59", "07:00 - 07:59",
            "08:00 - 08:59", "09:00 - 09:59", "10:00 - 10:59", "11:00 - 11:59",
            "12:00 - 12:59", "13:00 - 13:59", "14:00 - 14:59", "15:00 - 15:59",
            "16:00 - 16:59", "17:00 - 17:59", "18:00 - 18:59", "19:00 - 19:59",
            "20:00 - 20:59", "21:00 - 21:59", "22:00 - 22:59", "23:00 - 23:59"
        ] 
    }
}
DB_NAME = "shifts.db"                         
# ============================================================

def get_moscow_date() -> date:
    """Гарантированно возвращает текущую дату по МСК (UTC+3)"""
    return datetime.now(timezone(timedelta(hours=3))).date()


async def get_shift_interface(shift_type: str, guild: discord.Guild, target_date=None):
    """Генерирует Embed и View на основе состояния БД и переданной даты"""
    if target_date is None:
        target_date = get_moscow_date()
        
    date_str = str(target_date)
    slots = CONFIG[shift_type]["slots"]
    
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT slot, user_id FROM shifts WHERE date = ? AND department = ?",
            (date_str, shift_type)
        )
        occupied_slots = {row[0]: row[1] for row in await cursor.fetchall()}

    current_date_str = target_date.strftime("%d.%m")
    
    if shift_type == "24ad":
        title_text = f"📆 Расписание смен — {current_date_str}"
        color_val = 0x7BFE6C
    elif shift_type == "ad":
        title_text = f"📆 Расписание дежурств — {current_date_str}"
        color_val = 0x7BFE6C
    else:
        title_text = f"📅 Расписание смен — Отдел BM — {current_date_str}"
        color_val = 0x3498DB

    if shift_type == "24ad" and target_date.weekday() == 6:
        title_text = f"📆 Расписание смен — {current_date_str}"
        embed = discord.Embed(title=title_text, description="🔒 **Бронирование на воскресенье недоступно, день директора.**", color=0xB26CFE)
        view = ShiftView(shift_type, occupied_slots={s: 0 for s in slots})
        return embed, view

    embed = discord.Embed(title=title_text, color=color_val)
    
    description_lines = []
    for slot in slots:
        if slot in occupied_slots:
            description_lines.append(f"❌ `{slot}` — <@{occupied_slots[slot]}>")
        else:
            description_lines.append(f"⚪️ `{slot}` — 🟢 *Свободно*")
            
    embed.description = "\n".join(description_lines)
    
    embed.add_field(
        name="Управление сменой", 
        value="• Выберите свободное время в меню, чтобы занять его.\n• Для отмены или передачи используйте кнопки ниже.", 
        inline=False
    )
    view = ShiftView(shift_type, occupied_slots)

    return embed, view


async def fetch_date_by_msg(message_id: int) -> str:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT date FROM panels WHERE message_id = ?", (message_id,))
        row = await cursor.fetchone()
        return row[0] if row else str(get_moscow_date())


# ==================== ОБЩАЯ ФУНКЦИЯ КЛИКА/ВЫБОРА СМЕНЫ ====================
async def process_booking(interaction: discord.Interaction, shift_type: str, slot_time: str, target_date_str: str):
    t_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()

    if shift_type == "24ad" and t_date.weekday() == 6:
        return await interaction.response.send_message("Бронирование на воскресенье недоступно, день директора.", ephemeral=True)

    required_role = CONFIG[shift_type]["role_id"]
    if not discord.utils.get(interaction.user.roles, id=required_role):
        return await interaction.response.send_message("❌ У вас нет нужной роли для работы в этом отделе.", ephemeral=True)

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT 1 FROM shifts WHERE date = ? AND department = ? AND user_id = ?",
            (target_date_str, shift_type, interaction.user.id)
        )
        if await cursor.fetchone():
            return await interaction.response.send_message("❌ Вы уже заняли одну смену на этот день в этом отделе!", ephemeral=True)

        cursor = await db.execute(
            "SELECT 1 FROM shifts WHERE date = ? AND department = ? AND slot = ?",
            (target_date_str, shift_type, slot_time)
        )
        if await cursor.fetchone():
            return await interaction.response.send_message("❌ Этот слот уже успел занять кто-то другой.", ephemeral=True)

        await db.execute(
            "INSERT INTO shifts (date, department, slot, user_id) VALUES (?, ?, ?, ?)",
            (target_date_str, shift_type, slot_time, interaction.user.id)
        )
        await db.commit()

    embed, view = await get_shift_interface(shift_type, interaction.guild, target_date=t_date)
    await interaction.response.edit_message(embed=embed, view=view)


# ==================== ВЫПАДАЮЩЕЕ МЕНЮ ДЛЯ СОТРУДНИКОВ ====================
class ShiftSelect(discord.ui.Select):
    def __init__(self, shift_type: str, free_slots: list, register_all: bool = False):
        if register_all:
            options = [discord.SelectOption(label="Заглушка", value="dummy")]
        else:
            options = [discord.SelectOption(label=slot, value=slot) for slot in free_slots]
            if not options:
                options = [discord.SelectOption(label="Все смены заняты", value="none", default=True)]
                
        super().__init__(
            placeholder="Выберите доступное время смены..." if not register_all and free_slots else "Все смены заняты",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"p_select_{shift_type}",
            disabled=bool(not register_all and not free_slots)
        )
        self.shift_type = shift_type

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] in ["none", "dummy"]:
            return await interaction.response.send_message("❌ Ошибка выбора.", ephemeral=True)
            
        target_date_str = await fetch_date_by_msg(interaction.message.id)
        await process_booking(interaction, self.shift_type, self.values[0], target_date_str)


# ==================== МОДАЛКА КУРАТОРА: СНЯТЬ ПО ID ====================
class CuratorRemoveByIdModal(discord.ui.Modal, title="Принудительное снятие"):
    user_input = discord.ui.TextInput(label="ID сотрудника", placeholder="Введи Discord ID цифрами...", required=True, min_length=15, max_length=21)

    def __init__(self, shift_type, parent_message):
        super().__init__()
        self.shift_type = shift_type
        self.parent_message = parent_message

    async def on_submit(self, interaction: discord.Interaction):
        raw_id = self.user_input.value.strip()
        if not raw_id.isdigit():
            return await interaction.response.send_message("❌ Неверный формат ID. Используйте только цифры.", ephemeral=True)
        
        target_id = int(raw_id)
        target_date_str = await fetch_date_by_msg(self.parent_message.id)
        t_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()

        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute(
                "SELECT slot FROM shifts WHERE date = ? AND department = ? AND user_id = ?",
                (target_date_str, self.shift_type, target_id)
            )
            row = await cursor.fetchone()
            
            if not row:
                return await interaction.response.send_message("❌ У данного сотрудника нет смены.", ephemeral=True)

            user_slot = row[0]
            await db.execute(
                "DELETE FROM shifts WHERE date = ? AND department = ? AND user_id = ?",
                (target_date_str, self.shift_type, target_id)
            )
            await db.commit()

        embed, view = await get_shift_interface(self.shift_type, interaction.guild, target_date=t_date)
        await self.parent_message.edit(embed=embed, view=view)
        await interaction.response.send_message(f"✅ Сотрудник <@{target_id}> принудительно снят со смены `{user_slot}`.", ephemeral=True)


# ==================== МОДАЛКА КУРАТОРА: ВВОД ПОЛУЧАТЕЛЯ СМЕНЫ ====================
class CuratorTransferTargetModal(discord.ui.Modal, title="Назначение смены куратором"):
    to_input = discord.ui.TextInput(label="ID сотрудника, кому перейдет смена", placeholder="Введи Discord ID цифрами...", required=True, min_length=15, max_length=21)

    def __init__(self, shift_type, parent_message, selected_slot):
        super().__init__()
        self.shift_type = shift_type
        self.parent_message = parent_message
        self.selected_slot = selected_slot

    async def on_submit(self, interaction: discord.Interaction):
        to_raw = self.to_input.value.strip()

        if not to_raw.isdigit():
            return await interaction.response.send_message("❌ Неверный формат ID. Поле должно содержать только цифры.", ephemeral=True)
        
        to_id = int(to_raw)
        target_date_str = await fetch_date_by_msg(self.parent_message.id)
        t_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()

        target_member = interaction.guild.get_member(to_id)
        if not target_member:
            return await interaction.response.send_message("❌ Новый сотрудник не найден на этом сервере.", ephemeral=True)

        required_role = CONFIG[self.shift_type]["role_id"]
        if not discord.utils.get(target_member.roles, id=required_role):
            return await interaction.response.send_message("❌ У нового сотрудника нет роли этого отдела.", ephemeral=True)

        async with aiosqlite.connect(DB_NAME) as db:
            # Проверяем, нет ли у получателя уже смены на этот день в этом отделе
            cursor = await db.execute(
                "SELECT 1 FROM shifts WHERE date = ? AND department = ? AND user_id = ?", 
                (target_date_str, self.shift_type, to_id)
            )
            if await cursor.fetchone():
                return await interaction.response.send_message("❌ У получателя смены уже есть активная смена на этот день.", ephemeral=True)

            # Перезаписываем (или создаем новую) смену через INSERT OR REPLACE
            # Для этого в нашей таблице нет UNIQUE полей, поэтому мы сначала удаляем старую запись на этот таймслот (если она была), а затем создаем новую
            await db.execute(
                "DELETE FROM shifts WHERE date = ? AND department = ? AND slot = ?",
                (target_date_str, self.shift_type, self.selected_slot)
            )
            await db.execute(
                "INSERT INTO shifts (date, department, slot, user_id) VALUES (?, ?, ?, ?)",
                (target_date_str, self.shift_type, self.selected_slot, to_id)
            )
            await db.commit()

        embed, view = await get_shift_interface(self.shift_type, interaction.guild, target_date=t_date)
        await self.parent_message.edit(embed=embed, view=view)
        await interaction.response.send_message(f"✅ Смена `{self.selected_slot}` успешно передана/назначена сотруднику <@{to_id}>.", ephemeral=True)


# ==================== ИЗМЕНЕНИЕ: СПИСОК ВСЕХ СМЕН ДЛЯ КУРАТОРА ====================
class CuratorTransferSelect(discord.ui.Select):
    def __init__(self, shift_type: str, parent_message: discord.Message, occupied_dict: dict):
        options = []
        all_slots = CONFIG[shift_type]["slots"]
        
        # Перебираем ВСЕ смены без исключения
        for slot in all_slots:
            if slot in occupied_dict:
                user_id = occupied_dict[slot]
                member = parent_message.guild.get_member(user_id)
                status = f"Занято: {member.display_name if member else f'ID: {user_id}'}"
            else:
                status = "Свободно"
                
            options.append(discord.SelectOption(
                label=f"⏰ {slot}",
                value=slot,
                description=status
            ))

        super().__init__(
            placeholder="🔄 Передача смены (выберите любую из списка)...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"p_curator_all_slots_select_{shift_type}",
            row=0
        )
        self.shift_type = shift_type
        self.parent_message = parent_message

    async def callback(self, interaction: discord.Interaction):
        # При клике на абсолютно любую смену — запрашиваем ID нового владельца
        await interaction.response.send_modal(CuratorTransferTargetModal(self.shift_type, self.parent_message, self.values[0]))


# ==================== ОБНОВЛЕННАЯ ПАНЕЛЬ КУРАТОРА ====================
class CuratorActionView(discord.ui.View):
    def __init__(self, shift_type: str, parent_message: discord.Message, occupied_dict: dict):
        super().__init__(timeout=60)
        self.shift_type = shift_type
        self.parent_message = parent_message
        
        # Передаем словарь занятых смен, чтобы показать статусы прямо в списке
        self.add_item(CuratorTransferSelect(shift_type, parent_message, occupied_dict))

    @discord.ui.button(label="🚫 Принудительно снять сотрудника (по ID)", style=discord.ButtonStyle.danger, row=1)
    async def remove_someone(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CuratorRemoveByIdModal(self.shift_type, self.parent_message))


# ==================== МОДАЛКА ПЕРЕДАЧИ (ДЛЯ СОТРУДНИКОВ) ====================
class TransferModal(discord.ui.Modal, title="Передача смены"):
    target_input = discord.ui.TextInput(label="ID нового сотрудника", placeholder="Discord ID цифрами...", required=True, min_length=15, max_length=21)

    def __init__(self, shift_type, current_slot):
        super().__init__()
        self.shift_type = shift_type
        self.current_slot = current_slot

    async def on_submit(self, interaction: discord.Interaction):
        raw_id = self.target_input.value.strip()
        if not raw_id.isdigit():
            return await interaction.response.send_message("❌ Неверный формат ID.", ephemeral=True)
        
        target_id = int(raw_id)
        target_member = interaction.guild.get_member(target_id)

        if not target_member:
            return await interaction.response.send_message("❌ Пользователь не найден.", ephemeral=True)

        required_role = CONFIG[self.shift_type]["role_id"]
        if not discord.utils.get(target_member.roles, id=required_role):
            return await interaction.response.send_message("❌ У сотрудника нет роли этого отдела.", ephemeral=True)

        target_date_str = await fetch_date_by_msg(interaction.message.id)
        t_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()

        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute("SELECT 1 FROM shifts WHERE date = ? AND department = ? AND user_id = ?", (target_date_str, self.shift_type, target_id))
            if await cursor.fetchone():
                return await interaction.response.send_message("❌ У него уже есть смена на этот день.", ephemeral=True)

            await db.execute("UPDATE shifts SET user_id = ? WHERE date = ? AND department = ? AND slot = ?", (target_id, target_date_str, self.shift_type, self.current_slot))
            await db.commit()

        embed, view = await get_shift_interface(self.shift_type, interaction.guild, target_date=t_date)
        await interaction.message.edit(embed=embed, view=view)
        await interaction.response.send_message(f"✅ Смена передана сотруднику <@{target_id}>.", ephemeral=True)


# ==================== ГЛАВНЫЙ VIEW ====================
class ShiftView(discord.ui.View):
    def __init__(self, shift_type: str, occupied_slots: dict = None, register_all: bool = False):
        super().__init__(timeout=None)
        self.shift_type = shift_type
        occupied = occupied_slots or {}
        slots = CONFIG[shift_type]["slots"]

        free_slots = [s for s in slots if s not in occupied]
        self.add_item(ShiftSelect(shift_type, free_slots, register_all))
        
        self.add_item(discord.ui.Button(style=discord.ButtonStyle.red, label="Отменить смену", custom_id=f"p_ctrl_cancel_{shift_type}", row=1))
        self.add_item(discord.ui.Button(style=discord.ButtonStyle.blurple, label="Передать смену", custom_id=f"p_ctrl_transfer_{shift_type}", row=1))
        self.add_item(discord.ui.Button(style=discord.ButtonStyle.secondary, label="⚙️ Панель куратора", custom_id=f"p_ctrl_curator_{shift_type}", row=1))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        custom_id = interaction.data.get("custom_id", "")
        target_date_str = await fetch_date_by_msg(interaction.message.id)
        t_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        
        if "p_ctrl_curator" in custom_id:
            curator_role_id = CONFIG[self.shift_type]["curator_role_id"]
            if not discord.utils.get(interaction.user.roles, id=curator_role_id):
                await interaction.response.send_message("❌ Доступ только для кураторов отдела.", ephemeral=True)
                return False
            
            # Собираем словарь занятых смен для вывода описаний в списке куратора
            async with aiosqlite.connect(DB_NAME) as db:
                cursor = await db.execute(
                    "SELECT slot, user_id FROM shifts WHERE date = ? AND department = ?", 
                    (target_date_str, self.shift_type)
                )
                occupied_dict = {row[0]: row[1] for row in await cursor.fetchall()}
            
            # Открываем панель
            await interaction.response.send_message(
                "🛠️ **Панель куратора:**", 
                view=CuratorActionView(self.shift_type, interaction.message, occupied_dict), 
                ephemeral=True
            )
            return False

        if "p_ctrl_cancel" in custom_id or "p_ctrl_transfer" in custom_id:
            async with aiosqlite.connect(DB_NAME) as db:
                cursor = await db.execute("SELECT slot FROM shifts WHERE date = ? AND department = ? AND user_id = ?", (target_date_str, self.shift_type, interaction.user.id))
                row = await cursor.fetchone()

            if not row:
                await interaction.response.send_message("❌ У вас нет активной смены в этом отделе на этот день.", ephemeral=True)
                return False

            user_slot = row[0]

            if "p_ctrl_cancel" in custom_id:
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("DELETE FROM shifts WHERE date = ? AND department = ? AND slot = ?", (target_date_str, self.shift_type, user_slot))
                    await db.commit()
                
                embed, view = await get_shift_interface(self.shift_type, interaction.guild, target_date=t_date)
                await interaction.response.edit_message(embed=embed, view=view)
                await interaction.followup.send(f"❌ Смена {user_slot} отменена.", ephemeral=True)
                return False

            elif "p_ctrl_transfer" in custom_id:
                await interaction.response.send_modal(TransferModal(self.shift_type, user_slot))
                return False

        return True


class ShiftCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS shifts (
                    date TEXT,
                    department TEXT,
                    slot TEXT,
                    user_id INTEGER
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS panels (
                    message_id INTEGER PRIMARY KEY,
                    date TEXT,
                    department TEXT
                )
            """)
            await db.commit()

        for s_type in CONFIG.keys():
            self.bot.add_view(ShiftView(s_type, register_all=True))

    @commands.command()
    async def director(self, ctx):
        current_date_str = get_moscow_date().strftime("%d.%m")
        embed = discord.Embed(
            title=f"📆 Расписание смен — {current_date_str}", 
            description="Бронирование на воскресенье недоступно, день директора.", 
            color=0xB26CFE
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def start_shifts(self, ctx, shift_type: str, day_offset: int = 0):
        if shift_type not in CONFIG:
            return  
        target_date = get_moscow_date() + timedelta(days=day_offset)
        embed, view = await get_shift_interface(shift_type, ctx.guild, target_date=target_date)
        
        msg = await ctx.send(embed=embed, view=view)
        
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "INSERT OR REPLACE INTO panels (message_id, date, department) VALUES (?, ?, ?)",
                (msg.id, str(target_date), shift_type)
            )
            await db.commit()


async def setup(bot):
    await bot.add_cog(ShiftCog(bot))
