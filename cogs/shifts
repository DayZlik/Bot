import discord
from discord.ext import commands
import aiosqlite
from datetime import date

# ==================== БЛОК НАСТРОЕК СМЕН ====================
CONFIG = {
    "bm": {"role_id": 101010101010101010},    # ID роли отдела BM
    "ad": {"role_id": 888888888888888888},    # ID роли отдела AD
    "24ad": {"role_id": 111222333444555666}   # ID роли отдела 24AD
}
DB_NAME = "shifts.db"                         # Та же общая база данных
SLOTS = ["07:00", "15:00", "23:00"]           # Временная сетка смен
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

    # 1. Формирование Эмбеда со списками сотрудников
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
        view = ShiftView(shift_type, occupied_slots={s: 0 for s in SLOTS}) # Кнопки времени исчезнут
    else:
        embed.description = "\n".join(description_lines)
        embed.add_field(
            name="Управление сменной", 
            value="• Нажмите на свободное время, чтобы занять его.\n• Для отмены или передачи используйте кнопки ниже.", 
            inline=False
        )
        view = ShiftView(shift_type, occupied_slots)

    return embed, view


# ==================== МОДАЛЬНОЕ ОКНО ПЕРЕДАЧИ ====================
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

        # Проверка роли у нового сотрудника
        required_role = CONFIG[self.shift_type]["role_id"]
        if not discord.utils.get(target_member.roles, id=required_role):
            return await interaction.response.send_message("❌ У этого сотрудника нет роли данного отдела.", ephemeral=True)

        async with aiosqlite.connect(DB_NAME) as db:
            # Проверка, нет ли у него уже активной смены на сегодня в этом отделе
            cursor = await db.execute(
                "SELECT 1 FROM shifts WHERE date = ? AND department = ? AND user_id = ?", 
                (today, self.shift_type, target_id)
            )
            if await cursor.fetchone():
                return await interaction.response.send_message("❌ У этого сотрудника уже есть занятая смена на сегодня.", ephemeral=True)

            # Перезапись владельца смены
            await db.execute(
                "UPDATE shifts SET user_id = ? WHERE date = ? AND department = ? AND slot = ?",
                (target_id, today, self.shift_type, self.current_slot)
            )
            await db.commit()

        # Глобальное обновление интерфейса
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

        # Защита: День директора для 24ad
        if self.shift_type == "24ad" and date.today().weekday() == 6:
            return await interaction.response.send_message("Бронирование на воскресенье недоступно, день директора.", ephemeral=True)

        # Защита: Проверка роли
        required_role = CONFIG[self.shift_type]["role_id"]
        if not discord.utils.get(interaction.user.roles, id=required_role):
            return await interaction.response.send_message("❌ У вас нет нужной роли для работы в этом отделе.", ephemeral=True)

        async with aiosqlite.connect(DB_NAME) as db:
            # Проверка на дубликат (одна смена в одни руки в день)
            cursor = await db.execute(
                "SELECT 1 FROM shifts WHERE date = ? AND department = ? AND user_id = ?",
                (today, self.shift_type, interaction.user.id)
            )
            if await cursor.fetchone():
                return await interaction.response.send_message("❌ Вы уже заняли одну смену на сегодня в этом отделе!", ephemeral=True)

            # Проверка на конкуренцию (если кто-то нажал одновременно с тобой)
            cursor = await db.execute(
                "SELECT 1 FROM shifts WHERE date = ? AND department = ? AND slot = ?",
                (today, self.shift_type, self.slot_time)
            )
            if await cursor.fetchone():
                return await interaction.response.send_message("❌ Этот слот уже успел занять кто-то другой.", ephemeral=True)

            # Регистрация смены
            await db.execute(
                "INSERT INTO shifts (date, department, slot, user_id) VALUES (?, ?, ?, ?)",
                (today, self.shift_type, self.slot_time, interaction.user.id)
            )
            await db.commit()

        embed, view = await get_shift_interface(self.shift_type, interaction.guild)
        await interaction.response.edit_message(embed=embed, view=view)
        await interaction.followup.send(f"✅ Вы успешно заняли смену на **{self.slot_time}**.", ephemeral=True)


# ==================== ГЛАВНЫЙ ПЕРСИСТЕНТНЫЙ VIEW ====================
class ShiftView(discord.ui.View):
    def __init__(self, shift_type: str, occupied_slots: dict = None, register_all: bool = False):
        super().__init__(timeout=None)
        self.shift_type = shift_type
        occupied = occupied_slots or {}

        # Режим регистрации (для cog_load): резервируем ID всех возможных кнопок времени
        if register_all:
            for slot in SLOTS:
                self.add_item(ShiftButton(slot, self.shift_type))
        else:
            # Рабочий режим: выводим кнопки только для СВОБОДНЫХ смен
            for slot in SLOTS:
                if slot not in occupied:
                    self.add_item(ShiftButton(slot, self.shift_type))

        # Постоянные кнопки управления (всегда на row=1)
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.red, 
            label="Отменить смену", 
            custom_id=f"p_ctrl_cancel_{shift_type}",
            row=1
        ))
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.blurple, 
            label="Передать смену", 
            custom_id=f"p_ctrl_transfer_{shift_type}",
            row=1
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        custom_id = interaction.data.get("custom_id", "")
        
        # Перехватываем нажатия на кнопки управления
        if "p_ctrl_cancel" in custom_id or "p_ctrl_transfer" in custom_id:
            today = str(date.today())
            
            # Ищем, закреплена ли за нажавшим хоть одна смена сегодня
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

            # Действие: ОТМЕНА
            if "p_ctrl_cancel" in custom_id:
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute(
                        "DELETE FROM shifts WHERE date = ? AND department = ? AND slot = ?",
                        (today, self.shift_type, user_slot)
                    )
                    await db.commit()
                
                embed, view = await get_shift_interface(self.shift_type, interaction.guild)
                await interaction.response.edit_message(embed=embed, view=view)
                await interaction.followup.send(f"❌ Вы отменили свою смену на {user_slot}. Кнопка снова доступна для всех.", ephemeral=True)
                return False

            # Действие: ПЕРЕДАЧА
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
        # Автоматическое создание таблицы смен, если её нет
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

        # Регистрируем View в памяти бота для поддержки вечной работы кнопок (даже после перезагрузок)
        for s_type in CONFIG.keys():
            self.bot.add_view(ShiftView(s_type, register_all=True))

    @commands.command()
    async def director(self, ctx):
        """Информационный пост про День Директора"""
        embed = discord.Embed(
            title="👑 День Директора | 24AD",
            description="Бронирование на воскресенье недоступно, день директора.",
            color=0xF1C40F
        )
        embed.set_footer(text="Автоматическая система контроля")
        await ctx.send(embed=embed)

    @commands.command()
    async def start_shifts(self, ctx, shift_type: str):
        """Создает интерактивное расписание для конкретного отдела"""
        if shift_type not in CONFIG:
            return  # Игнорируем неверные кодовые названия отделов
            
        embed, view = await get_shift_interface(shift_type, ctx.guild)
        await ctx.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(ShiftCog(bot))
