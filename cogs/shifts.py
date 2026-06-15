import discord
from discord.ext import commands
import aiosqlite
from datetime import date

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

async def get_shift_interface(shift_type: str, guild: discord.Guild):
    """Генерирует актуальный Embed и View на основе состояния Базы Данных"""
    today = str(date.today())
    slots = CONFIG[shift_type]["slots"]
    
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT slot, user_id FROM shifts WHERE date = ? AND department = ?",
            (today, shift_type)
        )
        occupied_slots = {row[0]: row[1] for row in await cursor.fetchall()}

    embed = discord.Embed(
        title=f"📅 Расписание смен — Отдел {shift_type.upper()}",
        color=0x3498DB if shift_type != "24ad" else 0xF1C40F
    )
    
    # ИЗМЕНЕНИЕ: Новый формат вывода строк расписания
    description_lines = []
    for slot in slots:
        if slot in occupied_slots:
            description_lines.append(f"🔴 `{slot}` — <@{occupied_slots[slot]}>")
        else:
            description_lines.append(f"⚪️ `{slot}` — 🟢 *Свободно*")
            
    if shift_type == "24ad" and date.today().weekday() == 6:
        embed.description = "🔒 **Бронирование на воскресенье недоступно, день директора.**"
        embed.color = 0xE74C3C
        view = ShiftView(shift_type, occupied_slots={s: 0 for s in slots})
    else:
        embed.description = "\n".join(description_lines)
        embed.add_field(
            name="Управление сменной", 
            value="• Выберите свободное время, чтобы занять его.\n• Для отмены или передачи используйте кнопки ниже.", 
            inline=False
        )
        view = ShiftView(shift_type, occupied_slots)

    return embed, view


# ==================== ОБЩАЯ ФУНКЦИЯ КЛИКА/ВЫБОРА СМЕНЫ ====================
async def process_booking(interaction: discord.Interaction, shift_type: str, slot_time: str):
    today = str(date.today())

    if shift_type == "24ad" and date.today().weekday() == 6:
        return await interaction.response.send_message("Бронирование на воскресенье недоступно, день директора.", ephemeral=True)

    required_role = CONFIG[shift_type]["role_id"]
    if not discord.utils.get(interaction.user.roles, id=required_role):
        return await interaction.response.send_message("❌ У вас нет нужной роли для работы в этом отделе.", ephemeral=True)

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT 1 FROM shifts WHERE date = ? AND department = ? AND user_id = ?",
            (today, shift_type, interaction.user.id)
        )
        if await cursor.fetchone():
            return await interaction.response.send_message("❌ Вы уже заняли одну смену на сегодня в этом отделе!", ephemeral=True)

        cursor = await db.execute(
            "SELECT 1 FROM shifts WHERE date = ? AND department = ? AND slot = ?",
            (today, shift_type, slot_time)
        )
        if await cursor.fetchone():
            return await interaction.response.send_message("❌ Этот слот уже успел занять кто-то другой.", ephemeral=True)

        await db.execute(
            "INSERT INTO shifts (date, department, slot, user_id) VALUES (?, ?, ?, ?)",
            (today, shift_type, slot_time, interaction.user.id)
        )
        await db.commit()

    embed, view = await get_shift_interface(shift_type, interaction.guild)
    await interaction.response.edit_message(embed=embed, view=view)


# ==================== ВЫПАДАЮЩЕЕ МЕНЮ ДЛЯ 24AD ====================
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
        await process_booking(interaction, self.shift_type, self.values[0])


# ==================== ОБЫЧНЫЕ КНОПКИ ДЛЯ AD И BM ====================
class ShiftButton(discord.ui.Button):
    def __init__(self, slot_time, shift_type):
        super().__init__(
            style=discord.ButtonStyle.green, 
            label=slot_time, 
            custom_id=f"p_btn_{shift_type}_{slot_time}"
        )
        self.slot_time = slot_time
        self.shift_type = shift_type

    async def callback(self, interaction: discord.Interaction):
        await process_booking(interaction, self.shift_type, self.slot_time)


# ==================== МОДАЛКА КУРАТОРА ====================
class CuratorRemoveModal(discord.ui.Modal, title="Принудительное снятие"):
    slot_input = discord.ui.TextInput(
        label="Укажите время смены точь-в-точь",
        placeholder="Например: 14:00 - 14:59 или 15:00",
        required=True,
        min_length=5,
        max_length=20
    )

    def __init__(self, shift_type, parent_message):
        super().__init__()
        self.shift_type = shift_type
        self.parent_message = parent_message

    async def on_submit(self, interaction: discord.Interaction):
        raw_slot = self.slot_input.value.strip()
        today = str(date.today())
        slots = CONFIG[self.shift_type]["slots"]

        target_slot = None
        for s in slots:
            if raw_slot in s:
                target_slot = s
                break

        if not target_slot:
            return await interaction.response.send_message("❌ Слот с таким временем не найден в сетке этого отдела.", ephemeral=True)

        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute(
                "SELECT user_id FROM shifts WHERE date = ? AND department = ? AND slot = ?",
                (today, self.shift_type, target_slot)
            )
            row = await cursor.fetchone()
            
            if not row:
                return await interaction.response.send_message(f"❌ Слот **{target_slot}** не занят.", ephemeral=True)

            old_user_id = row[0]
            await db.execute(
                "DELETE FROM shifts WHERE date = ? AND department = ? AND slot = ?",
                (today, self.shift_type, target_slot)
            )
            await db.commit()

        embed, view = await get_shift_interface(self.shift_type, interaction.guild)
        await self.parent_message.edit(embed=embed, view=view)
        await interaction.response.send_message(f"✅ Сотрудник <@{old_user_id}> снят со смены **{target_slot}**.", ephemeral=True)


# ==================== СКРЫТОЕ МЕНЮ КУРАТОРА ====================
class CuratorActionView(discord.ui.View):
    def __init__(self, shift_type: str, parent_message: discord.Message):
        super().__init__(timeout=60)
        self.shift_type = shift_type
        self.parent_message = parent_message

    @discord.ui.button(label="🧹 Сбросить все смены", style=discord.ButtonStyle.danger)
    async def reset_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        today = str(date.today())
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("DELETE FROM shifts WHERE date = ? AND department = ?", (today, self.shift_type))
            await db.commit()

        embed, view = await get_shift_interface(self.shift_type, interaction.guild)
        await self.parent_message.edit(embed=embed, view=view)
        await interaction.response.send_message("🧹 Расписание отдела очищено!", ephemeral=True)

    @discord.ui.button(label="🚫 Снять сотрудника", style=discord.ButtonStyle.secondary)
    async def remove_someone(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CuratorRemoveModal(self.shift_type, self.parent_message))


# ==================== МОДАЛКА ПЕРЕДАЧИ ====================
class TransferModal(discord.ui.Modal, title="Передача смены"):
    target_input = discord.ui.TextInput(label="ID нового сотрудника", placeholder="Discord ID цифрами...", required=True, min_length=15, max_length=21)

    def __init__(self, shift_type, current_slot):
        super().__init__()
        self.shift_type = shift_type
        self.current_slot = current_slot

    async def on_submit(self, interaction: discord.Interaction):
        today = str(date.today())
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

        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute("SELECT 1 FROM shifts WHERE date = ? AND department = ? AND user_id = ?", (today, self.shift_type, target_id))
            if await cursor.fetchone():
                return await interaction.response.send_message("❌ У него уже есть смена на сегодня.", ephemeral=True)

            await db.execute("UPDATE shifts SET user_id = ? WHERE date = ? AND department = ? AND slot = ?", (target_id, today, self.shift_type, self.current_slot))
            await db.commit()

        embed, view = await get_shift_interface(self.shift_type, interaction.guild)
        await interaction.message.edit(embed=embed, view=view)
        await interaction.response.send_message(f"✅ Смена передана сотруднику <@{target_id}>.", ephemeral=True)


# ==================== ГЛАВНЫЙ VIEW ====================
class ShiftView(discord.ui.View):
    def __init__(self, shift_type: str, occupied_slots: dict = None, register_all: bool = False):
        super().__init__(timeout=None)
        self.shift_type = shift_type
        occupied = occupied_slots or {}
        slots = CONFIG[shift_type]["slots"]

        if shift_type == "24ad":
            free_slots = [s for s in slots if s not in occupied]
            self.add_item(ShiftSelect(shift_type, free_slots, register_all))
            row_idx = 1
        else:
            row_idx = 3 
            if register_all:
                for slot in slots:
                    self.add_item(ShiftButton(slot, self.shift_type))
            else:
                for slot in slots:
                    if slot not in occupied:
                        self.add_item(ShiftButton(slot, self.shift_type))

        # Кнопки управления
        self.add_item(discord.ui.Button(style=discord.ButtonStyle.red, label="Отменить смену", custom_id=f"p_ctrl_cancel_{shift_type}", row=row_idx))
        self.add_item(discord.ui.Button(style=discord.ButtonStyle.blurple, label="Передать смену", custom_id=f"p_ctrl_transfer_{shift_type}", row=row_idx))
        self.add_item(discord.ui.Button(style=discord.ButtonStyle.secondary, label="⚙️ Панель куратора", custom_id=f"p_ctrl_curator_{shift_type}", row=row_idx))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        custom_id = interaction.data.get("custom_id", "")
        
        if "p_ctrl_curator" in custom_id:
            curator_role_id = CONFIG[self.shift_type]["curator_role_id"]
            if not discord.utils.get(interaction.user.roles, id=curator_role_id):
                await interaction.response.send_message("❌ Доступ только для кураторов отдела.", ephemeral=True)
                return False
            
            await interaction.response.send_message("🛠️ **Панель куратора:**", view=CuratorActionView(self.shift_type, interaction.message), ephemeral=True)
            return False

        if "p_ctrl_cancel" in custom_id or "p_ctrl_transfer" in custom_id:
            today = str(date.today())
            async with aiosqlite.connect(DB_NAME) as db:
                cursor = await db.execute("SELECT slot FROM shifts WHERE date = ? AND department = ? AND user_id = ?", (today, self.shift_type, interaction.user.id))
                row = await cursor.fetchone()

            if not row:
                await interaction.response.send_message("❌ У вас нет активной смены в этом отделе.", ephemeral=True)
                return False

            user_slot = row[0]

            if "p_ctrl_cancel" in custom_id:
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("DELETE FROM shifts WHERE date = ? AND department = ? AND slot = ?", (today, self.shift_type, user_slot))
                    await db.commit()
                
                embed, view = await get_shift_interface(self.shift_type, interaction.guild)
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
            await db.commit()

        for s_type in CONFIG.keys():
            self.bot.add_view(ShiftView(s_type, register_all=True))

    @commands.command()
    async def director(self, ctx):
        embed = discord.Embed(title="👑 День Директора | 24AD", description="Бронирование на воскресенье недоступно, день директора.", color=0xF1C40F)
        await ctx.send(embed=embed)

    @commands.command()
    async def start_shifts(self, ctx, shift_type: str):
        if shift_type not in CONFIG:
            return  
        embed, view = await get_shift_interface(shift_type, ctx.guild)
        await ctx.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(ShiftCog(bot))
