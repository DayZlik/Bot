import discord
from discord.ext import commands
import aiosqlite
from datetime import date

# ==================== БЛОК НАСТРОЕК СМЕН ====================
CONFIG = {
    "bm": {
        "role_id": 101010101010101010,        # Роль сотрудника BM
        "curator_role_id": 111222333444555   # Роль КУРАТОРА BM
    },    
    "ad": {
        "role_id": 888888888888888888,        # Роль сотрудника AD
        "curator_role_id": 555666777888999   # Роль КУРАТОРА AD
    },    
    "24ad": {
        "role_id": 111222333444555666,       # Роль сотрудника 24AD
        "curator_role_id": 999888777666555   # Роль КУРАТОРА 24AD
    }
}
DB_NAME = "shifts.db"                         
SLOTS = ["07:00", "15:00", "23:00"]           
# ============================================================

async def get_shift_interface(shift_type: str, guild: discord.Guild):
    """Генерирует актуальный Embed и View на основе состояния Базы Данных"""
    today = str(date.today())
    
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
    
    description_lines = []
    for slot in SLOTS:
        if slot in occupied_slots:
            description_lines.append(f"⏰ **{slot}** — Занял: <@{occupied_slots[slot]}>")
        else:
            description_lines.append(f"⏰ **{slot}** — 🟢 *Свободно*")
            
    if shift_type == "24ad" and date.today().weekday() == 6:
        embed.description = "🔒 **Бронирование на воскресенье недоступно, день директора.**"
        embed.color = 0xE74C3C
        view = ShiftView(shift_type, occupied_slots={s: 0 for s in SLOTS})
    else:
        embed.description = "\n".join(description_lines)
        embed.add_field(
            name="Управление сменной", 
            value="• Нажмите на свободное время, чтобы занять его.\n• Для отмены или передачи используйте кнопки ниже.", 
            inline=False
        )
        view = ShiftView(shift_type, occupied_slots)

    return embed, view


# ==================== МОДАЛКА КУРАТОРА: СНЯТЬ С ОПРЕДЕЛЕННОГО ВРЕМЕНИ ====================
class CuratorRemoveModal(discord.ui.Modal, title="Принудительное снятие"):
    slot_input = discord.ui.TextInput(
        label="Укажите время смены",
        placeholder="Например: 07:00, 15:00, 23:00",
        required=True,
        min_length=5,
        max_length=5
    )

    def __init__(self, shift_type, parent_message):
        super().__init__()
        self.shift_type = shift_type
        self.parent_message = parent_message

    async def on_submit(self, interaction: discord.Interaction):
        target_slot = self.slot_input.value.strip()
        today = str(date.today())

        if target_slot not in SLOTS:
            return await interaction.response.send_message(f"❌ Неверное время. Допустимые слоты: {', '.join(SLOTS)}", ephemeral=True)

        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute(
                "SELECT user_id FROM shifts WHERE date = ? AND department = ? AND slot = ?",
                (today, self.shift_type, target_slot)
            )
            row = await cursor.fetchone()
            
            if not row:
                return await interaction.response.send_message(f"❌ Слот **{target_slot}** и так никем не занят.", ephemeral=True)

            old_user_id = row[0]
            await db.execute(
                "DELETE FROM shifts WHERE date = ? AND department = ? AND slot = ?",
                (today, self.shift_type, target_slot)
            )
            await db.commit()

        # Моментально обновляем публичный эмбед
        embed, view = await get_shift_interface(self.shift_type, interaction.guild)
        await self.parent_message.edit(embed=embed, view=view)
        
        await interaction.response.send_message(f"✅ Сотрудник <@{old_user_id}> принудительно снят со смены **{target_slot}**.", ephemeral=True)


# ==================== СКРЫТОЕ МЕНЮ ДЛЯ КУРАТОРА (EPHEMERAL VIEW) ====================
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

        # Моментально обновляем публичный эмбед
        embed, view = await get_shift_interface(self.shift_type, interaction.guild)
        await self.parent_message.edit(embed=embed, view=view)
        
        await interaction.response.send_message("🧹 Все активные смены отдела на сегодня успешно аннулированы!", ephemeral=True)

    @discord.ui.button(label="🚫 Снять сотрудника", style=discord.ButtonStyle.secondary)
    async def remove_someone(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Открываем модалку для ввода конкретного времени
        modal = CuratorRemoveModal(self.shift_type, self.parent_message)
        await interaction.response.send_modal(modal)


# ==================== МОДАЛЬНОЕ ОКНО ПЕРЕДАЧИ ДЛЯ ОБЫЧНЫХ ЮЗЕРОВ ====================
class TransferModal(discord.ui.Modal, title="Передача смены"):
    target_input = discord.ui.TextInput(
        label="ID нового сотрудника",
        placeholder="Вставьте Discord ID сотрудника сюда...",
        required=True,
        min_length=15,
        max_length=21
    )

    def __init__(self, shift_type, current_slot):
        super().__init__()
        self.shift_type = shift_type
        self.current_slot = current_slot

    async def on_submit(self, interaction: discord.Interaction):
        today = str(date.today())
        raw_id = self.target_input.value.strip()

        if not raw_id.isdigit():
            return await interaction.response.send_message("❌ Неверный формат ID. Должны быть только цифры.", ephemeral=True)
        
        target_id = int(raw_id)
        target_member = interaction.guild.get_member(target_id)

        if not target_member:
            return await interaction.response.send_message("❌ Пользователь не найден на этом сервере.", ephemeral=True)

        required_role = CONFIG[self.shift_type]["role_id"]
        if not discord.utils.get(target_member.roles, id=required_role):
            return await interaction.response.send_message("❌ У этого сотрудника нет роли данного отдела.", ephemeral=True)

        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute(
                "SELECT 1 FROM shifts WHERE date = ? AND department = ? AND user_id = ?", 
                (today, self.shift_type, target_id)
            )
            if await cursor.fetchone():
                return await interaction.response.send_message("❌ У этого сотрудника уже есть занятая смена на сегодня.", ephemeral=True)

            await db.execute(
                "UPDATE shifts SET user_id = ? WHERE date = ? AND department = ? AND slot = ?",
                (target_id, today, self.shift_type, self.current_slot)
            )
            await db.commit()

        embed, view = await get_shift_interface(self.shift_type, interaction.guild)
        await interaction.message.edit(embed=embed, view=view)
        await interaction.response.send_message(f"✅ Смена передана сотруднику <@{target_id}>.", ephemeral=True)


# ==================== ДИНАМИЧЕСКИЕ КНОПКИ ВРЕМЕНИ ====================
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
        today = str(date.today())

        if self.shift_type == "24ad" and date.today().weekday() == 6:
            return await interaction.response.send_message("Бронирование на воскресенье недоступно, день директора.", ephemeral=True)

        required_role = CONFIG[self.shift_type]["role_id"]
        if not discord.utils.get(interaction.user.roles, id=required_role):
            return await interaction.response.send_message("❌ У вас нет нужной роли для работы в этом отделе.", ephemeral=True)

        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute(
                "SELECT 1 FROM shifts WHERE date = ? AND department = ? AND user_id = ?",
                (today, self.shift_type, interaction.user.id)
            )
            if await cursor.fetchone():
                return await interaction.response.send_message("❌ Вы уже заняли одну смену на сегодня в этом отделе!", ephemeral=True)

            cursor = await db.execute(
                "SELECT 1 FROM shifts WHERE date = ? AND department = ? AND slot = ?",
                (today, self.shift_type, self.slot_time)
            )
            if await cursor.fetchone():
                return await interaction.response.send_message("❌ Этот слот уже успел занять кто-то другой.", ephemeral=True)

            await db.execute(
                "INSERT INTO shifts (date, department, slot, user_id) VALUES (?, ?, ?, ?)",
                (today, self.shift_type, self.slot_time, interaction.user.id)
            )
            await db.commit()

        embed, view = await get_shift_interface(self.shift_type, interaction.guild)
        await interaction.response.edit_message(embed=embed, view=view)


# ==================== ГЛАВНЫЙ ПЕРСИСТЕНТНЫЙ VIEW ====================
class ShiftView(discord.ui.View):
    def __init__(self, shift_type: str, occupied_slots: dict = None, register_all: bool = False):
        super().__init__(timeout=None)
        self.shift_type = shift_type
        occupied = occupied_slots or {}

        if register_all:
            for slot in SLOTS:
                self.add_item(ShiftButton(slot, self.shift_type))
        else:
            for slot in SLOTS:
                if slot not in occupied:
                    self.add_item(ShiftButton(slot, self.shift_type))

        # Постоянные кнопки управления (row 1)
        self.add_item(discord.ui.Button(style=discord.ButtonStyle.red, label="Отменить смену", custom_id=f"p_ctrl_cancel_{shift_type}", row=1))
        self.add_item(discord.ui.Button(style=discord.ButtonStyle.blurple, label="Передать смену", custom_id=f"p_ctrl_transfer_{shift_type}", row=1))
        
        # СЕКРЕТНАЯ КНОПКА КУРАТОРА
        self.add_item(discord.ui.Button(style=discord.ButtonStyle.secondary, label="⚙️ Панель куратора", custom_id=f"p_ctrl_curator_{shift_type}", row=1))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        custom_id = interaction.data.get("custom_id", "")
        
        # ПРОВЕРКА КНОПКИ КУРАТОРА
        if "p_ctrl_curator" in custom_id:
            curator_role_id = CONFIG[self.shift_type]["curator_role_id"]
            if not discord.utils.get(interaction.user.roles, id=curator_role_id):
                await interaction.response.send_message("❌ Доступ заблокирован. Эта панель доступна только кураторам данного отдела.", ephemeral=True)
                return False
            
            # Отправляем куратору его личное скрытое меню управления
            curator_view = CuratorActionView(self.shift_type, parent_message=interaction.message)
            await interaction.response.send_message("🛠️ **Управление отделом:** Выберите административное действие:", view=curator_view, ephemeral=True)
            return False

        # Обычные кнопки управления (Отмена / Передача)
        if "p_ctrl_cancel" in custom_id or "p_ctrl_transfer" in custom_id:
            today = str(date.today())
            
            async with aiosqlite.connect(DB_NAME) as db:
                cursor = await db.execute(
                    "SELECT slot FROM shifts WHERE date = ? AND department = ? AND user_id = ?",
                    (today, self.shift_type, interaction.user.id)
                )
                row = await cursor.fetchone()

            if not row:
                await interaction.response.send_message("❌ У вас нет активной смены в этом отделе для управления.", ephemeral=True)
                return False

            user_slot = row[0]

            if "p_ctrl_cancel" in custom_id:
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("DELETE FROM shifts WHERE date = ? AND department = ? AND slot = ?", (today, self.shift_type, user_slot))
                    await db.commit()
                
                embed, view = await get_shift_interface(self.shift_type, interaction.guild)
                await interaction.response.edit_message(embed=embed, view=view)
                await interaction.followup.send(f"❌ Вы отменили свою смену на {user_slot}.", ephemeral=True)
                return False

            elif "p_ctrl_transfer" in custom_id:
                modal = TransferModal(self.shift_type, user_slot)
                await interaction.response.send_modal(modal)
                return False

        return True


# ==================== КОГ СИСТЕМЫ СМЕН ====================
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
        embed = discord.Embed(
            title="👑 День Директора | 24AD",
            description="Бронирование на воскресенье недоступно, день директора.",
            color=0xF1C40F
        )
        embed.set_footer(text="Автоматическая система контроля")
        await ctx.send(embed=embed)

    @commands.command()
    async def start_shifts(self, ctx, shift_type: str):
        if shift_type not in CONFIG:
            return  
            
        embed, view = await get_shift_interface(shift_type, ctx.guild)
        await ctx.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(ShiftCog(bot))
