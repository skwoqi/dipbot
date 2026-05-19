import asyncio
import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, List, Optional

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, 
    InlineKeyboardButton, Message, CallbackQuery, FSInputFile
)
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Конфигурация
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ==================== БАЗА ДАННЫХ ====================

def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect("equipment_bot.db")
    cursor = conn.cursor()
    
    # Таблица заявок
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_name TEXT,
            user_phone TEXT,
            equipment_type TEXT,
            attachments TEXT,
            hours INTEGER,
            date TEXT,
            status TEXT DEFAULT 'new',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Таблица пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Таблица для админ-лога
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            action TEXT,
            order_id INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()

def save_user(user_id: int, username: str = None, full_name: str = None):
    """Сохранить пользователя в БД"""
    conn = sqlite3.connect("equipment_bot.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO users (user_id, username, full_name)
        VALUES (?, ?, ?)
    """, (user_id, username, full_name))
    conn.commit()
    conn.close()

def save_order(user_id: int, user_name: str, user_phone: str, equipment_type: str, 
               attachments: List[str], hours: int, date: str) -> int:
    """Сохранить заявку и вернуть ID"""
    conn = sqlite3.connect("equipment_bot.db")
    cursor = conn.cursor()
    
    attachments_json = json.dumps(attachments) if attachments else None
    
    cursor.execute("""
        INSERT INTO orders (user_id, user_name, user_phone, equipment_type, attachments, hours, date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, user_name, user_phone, equipment_type, attachments_json, hours, date))
    
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return order_id

def get_order(order_id: int):
    """Получить заявку по ID"""
    conn = sqlite3.connect("equipment_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    conn.close()
    return order

def get_all_orders():
    """Получить все заявки"""
    conn = sqlite3.connect("equipment_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders ORDER BY created_at DESC")
    orders = cursor.fetchall()
    conn.close()
    return orders

def get_orders_stats():
    """Получить статистику заявок"""
    conn = sqlite3.connect("equipment_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT status, COUNT(*) FROM orders GROUP BY status")
    stats = dict(cursor.fetchall())
    conn.close()
    return stats

def update_order_status(order_id: int, status: str):
    """Обновить статус заявки"""
    conn = sqlite3.connect("equipment_bot.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    conn.commit()
    conn.close()

def log_admin_action(admin_id: int, action: str, order_id: int = None):
    """Логирование действий админа"""
    conn = sqlite3.connect("equipment_bot.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO admin_log (admin_id, action, order_id)
        VALUES (?, ?, ?)
    """, (admin_id, action, order_id))
    conn.commit()
    conn.close()

# ==================== FSM СОСТОЯНИЯ ====================

class OrderForm(StatesGroup):
    """Состояния для оформления заказа"""
    name = State()
    phone = State()
    equipment_type = State()
    excavator_attachment = State()
    hours = State()
    date = State()
    final = State()

class CalcForm(StatesGroup):
    """Состояния для расчета стоимости"""
    details = State()

# ==================== КЛАВИАТУРЫ ====================

def get_main_keyboard():
    """Главное меню (reply keyboard)"""
    buttons = [
        [KeyboardButton(text="🚜 Каталог техники")],
        [KeyboardButton(text="💰 Цены и тарифы")],
        [KeyboardButton(text="📝 Оставить заявку")],
        [KeyboardButton(text="📞 Контакты")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_catalog_keyboard():
    """Каталог (инлайн)"""
    buttons = [
        [InlineKeyboardButton(text="🚧 Экскаваторы-погрузчики", callback_data="catalog_excavator")],
        [InlineKeyboardButton(text="🏭 Автокраны", callback_data="catalog_crane")],
        [InlineKeyboardButton(text="🚛 Самосвалы", callback_data="catalog_dump")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_attachment_keyboard(selected: List[str] = None):
    """Клавиатура выбора навесного оборудования"""
    if selected is None:
        selected = []
    
    buttons = []
    attachments = ["ковш", "гидромолот", "ямобур"]
    
    for att in attachments:
        status = "✅ " if att in selected else "⬜️ "
        buttons.append([InlineKeyboardButton(
            text=f"{status}{att.capitalize()}", 
            callback_data=f"att_{att}"
        )])
    
    buttons.append([InlineKeyboardButton(text="✅ Готово", callback_data="att_done")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_equipment_keyboard():
    """Выбор техники для заказа"""
    buttons = [
        [InlineKeyboardButton(text="🚧 Экскаватор-погрузчик", callback_data="eq_excavator")],
        [InlineKeyboardButton(text="🏭 Автокран", callback_data="eq_crane")],
        [InlineKeyboardButton(text="🚛 Самосвал", callback_data="eq_dump")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_prices_keyboard():
    """Клавиатура для цен"""
    buttons = [
        [InlineKeyboardButton(text="🧮 Рассчитать стоимость", callback_data="calc_start")],
        [InlineKeyboardButton(text="📝 Заказать", callback_data="order_start")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_final_keyboard():
    """Клавиатура подтверждения заказа"""
    buttons = [
        [InlineKeyboardButton(text="✅ Да", callback_data="final_yes")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="final_no")],
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data="final_edit")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_keyboard():
    """Кнопка назад"""
    buttons = [[InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ==================== ХЕНДЛЕРЫ КОМАНД ====================

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    await state.clear()
    save_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    
    welcome_text = (
        "🏗 Добро пожаловать в бот аренды спецтехники!\n\n"
        "Мы предоставляем:\n"
        "🚧 Экскаваторы-погрузчики (с навесным оборудованием)\n"
        "🏭 Автокраны грузоподъемностью до 25 тонн\n"
        "🚛 Самосвалы объемом до 30 тонн\n\n"
        "Выберите действие в меню ниже:"
    )
    
    await message.answer(welcome_text, reply_markup=get_main_keyboard())

@dp.message(Command("status"))
async def cmd_status(message: Message):
    """Проверка статуса заявки"""
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: /status <номер заявки>\nПример: /status 123")
        return
    
    try:
        order_id = int(args[1])
        order = get_order(order_id)
        
        if not order:
            await message.answer(f"❌ Заявка с номером {order_id} не найдена")
            return
        
        status_map = {
            "new": "🟡 Новая (ожидает обработки)",
            "confirmed": "🟢 Подтверждена",
            "completed": "🔵 Выполнена",
            "cancelled": "🔴 Отменена"
        }
        
        status_text = status_map.get(order[8], "Неизвестно")
        
        await message.answer(
            f"📋 ЗАЯВКА №{order_id}\n"
            f"Статус: {status_text}\n"
            f"Техника: {order[5]}\n"
            f"Дата: {order[7]}"
        )
    except ValueError:
        await message.answer("❌ Номер заявки должен быть числом")

@dp.message(Command("help"))
async def cmd_help(message: Message):
    """Помощь"""
    help_text = (
        "📖 Справка по командам:\n\n"
        "/start - Главное меню\n"
        "/status <номер> - Проверить статус заявки\n"
        "/help - Эта справка\n\n"
        "Также вы можете использовать кнопки в меню для навигации."
    )
    await message.answer(help_text, reply_markup=get_main_keyboard())

# ==================== АДМИН-КОМАНДЫ ====================

def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь админом"""
    return user_id in ADMIN_IDS

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    """Админ-панель"""
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к этой команде")
        return
    
    buttons = [
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📋 Список заявок", callback_data="admin_list")],
        [InlineKeyboardButton(text="📈 Все заявки", callback_data="admin_all")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await message.answer("👨‍💼 Админ-панель:", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("admin_"))
async def admin_callbacks(callback: CallbackQuery):
    """Обработка админ-колбэков"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    action = callback.data.split("_")[1]
    
    if action == "stats":
        stats = get_orders_stats()
        stats_text = "📊 СТАТИСТИКА ЗАЯВОК:\n\n"
        for status, count in stats.items():
            status_name = {"new": "🟡 Новые", "confirmed": "🟢 Подтвержденные", 
                          "completed": "🔵 Выполненные", "cancelled": "🔴 Отмененные"}.get(status, status)
            stats_text += f"{status_name}: {count}\n"
        
        await callback.message.edit_text(stats_text)
        await callback.answer()
        
    elif action == "list":
        orders = get_all_orders()
        if not orders:
            await callback.message.edit_text("📭 Заявок пока нет")
            await callback.answer()
            return
        
        text = "📋 ПОСЛЕДНИЕ ЗАЯВКИ:\n\n"
        for order in orders[:10]:
            text += f"#{order[0]} | {order[5]} | {order[3]} | {order[8]}\n"
        
        buttons = [[InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_list")]]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()
        
    elif action == "all":
        orders = get_all_orders()
        if not orders:
            await callback.message.edit_text("📭 Заявок пока нет")
            await callback.answer()
            return
        
        text = "📋 ВСЕ ЗАЯВКИ:\n\n"
        for order in orders:
            text += f"#{order[0]} | {order[5]} | {order[3]} | {order[8]} | {order[9]}\n"
        
        await callback.message.edit_text(text[:4000])  # Telegram limit
        await callback.answer()

# ==================== ОСНОВНЫЕ ХЕНДЛЕРЫ ====================

@dp.message(F.text == "🚜 Каталог техники")
async def catalog_handler(message: Message):
    """Обработчик кнопки каталога"""
    await message.answer("Выберите тип техники:", reply_markup=get_catalog_keyboard())

@dp.message(F.text == "💰 Цены и тарифы")
async def prices_handler(message: Message):
    """Обработчик кнопки цен"""
    text = (
        "💰 ЦЕНЫ (почасовая оплата):\n\n"
        "🚧 Экскаватор-погрузчик: 3 500 руб/час\n"
        "🏭 Автокран: 3 500 руб/час\n"
        "🚛 Самосвал: 3 000 руб/час\n\n"
        "💡 Минимальный заказ - 2 часа\n"
        "🌟 Скидка 10% при аренде от 20 часов"
    )
    await message.answer(text, reply_markup=get_prices_keyboard())

@dp.message(F.text == "📝 Оставить заявку")
async def order_start(message: Message, state: FSMContext):
    """Начало оформления заявки"""
    await state.set_state(OrderForm.name)
    await message.answer("📝 Оформление заявки\n\nВведите ваше имя:", reply_markup=types.ReplyKeyboardRemove())

@dp.message(F.text == "📞 Контакты")
async def contacts_handler(message: Message):
    """Контакты"""
    text = (
        "📞 КОНТАКТЫ:\n\n"
        "Телефон: +7 (917) 712-73-37\n"
        "Telegram: @Ochetov\n"
        "Email: ochetov01@mail.ru\n\n"
        "📍 Адрес: РМЭ посёлок Новый садовый массив № 1, 1\n\n"
        "⏰ Режим работы: 24/7\n"
        "🚚 Доставка техники бесплатная"
    )
    await message.answer(text, reply_markup=get_main_keyboard())

# ==================== КАТАЛОГ (ПОКАЗ ТЕХНИКИ) ====================

@dp.callback_query(F.data == "catalog_excavator")
async def catalog_excavator(callback: CallbackQuery, state: FSMContext):
    """Показ экскаватора-погрузчика"""
    # Здесь можно добавить реальное фото
    photo_url = "https://psv4.userapi.com/s/v1/d2/RwmCvz6PFqPEXPuv_CcKAru0geVuEL1lNOzRjSAMV-pNQDZ96JSV77v62PsDLR9hwGKHVWNfgdHLNSntNwfL1q0Fa5PtF_LUXRzDF0NYTu7YDKQb66dHrCBl-3zDFmFir9o8arqeu2Zr/traktor.jpg"
    text = (
        "🚧 ЭКСКАВАТОР-ПОГРУЗЧИК Hidromek HMK 102S\n\n"
        "Характеристики:\n"
        "• Мощность: 100 л.с.\n"
        "• Грузоподъемность: 3.2 т\n"
        "• Год выпуска: 2019-2020\n\n"
        "💡 Можно установить различное навесное оборудование:\n"
        "- Ковш\n"
        "- Гидромолот\n"
        "- Ямобур\n\n"
        "💰 Стоимость: 3 500 руб/час"
    )
    
    button = [[InlineKeyboardButton(text="🔧 Заказать эту технику", callback_data="order_excavator")]]
    keyboard = InlineKeyboardMarkup(inline_keyboard=button)
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "catalog_crane")
async def catalog_crane(callback: CallbackQuery):
    """Показ автокрана"""
    text = (
        "🏭 Автокран вездеход «Клинцы» 25 т. 28 м.\n\n"
        "Характеристики:\n"
        "• Грузоподъемность: 25 т\n"
        "• Вылет стрелы: 28 м\n"
        "• Год выпуска: 2024\n\n"
        "💰 Стоимость: 3 500 руб/час"
    )
    
    button = [[InlineKeyboardButton(text="🔧 Заказать эту технику", callback_data="order_crane")]]
    keyboard = InlineKeyboardMarkup(inline_keyboard=button)
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "catalog_dump")
async def catalog_dump(callback: CallbackQuery):
    """Показ самосвала"""
    text = (
        "🚛 Самосвал Shacman X3000 30 тонн \n\n"
        "Характеристики:\n"
        "• Грузоподъемность: 30 т\n"
        "• Объем кузова: 20 м³\n"
        "• Год выпуска: 2024\n\n"
        "💰 Стоимость: 3 000 руб/час"
    )
    
    button = [[InlineKeyboardButton(text="🔧 Заказать эту технику", callback_data="order_dump")]]
    keyboard = InlineKeyboardMarkup(inline_keyboard=button)
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

# ==================== ОФОРМЛЕНИЕ ЗАЯВКИ (FSM) ====================

@dp.callback_query(F.data.startswith("order_"))
async def order_from_catalog(callback: CallbackQuery, state: FSMContext):
    """Заказ из каталога"""
    if callback.data == "order_excavator":
        await state.update_data(equipment_type="Экскаватор-погрузчик")
    elif callback.data == "order_crane":
        await state.update_data(equipment_type="Автокран")
    elif callback.data == "order_dump":
        await state.update_data(equipment_type="Самосвал")
    elif callback.data == "order_start":
        pass  # просто переход к заявке
    
    await state.set_state(OrderForm.name)
    await callback.message.answer("📝 Оформление заявки\n\nВведите ваше имя:", reply_markup=types.ReplyKeyboardRemove())
    await callback.answer()

@dp.message(OrderForm.name)
async def order_name(message: Message, state: FSMContext):
    """Шаг 1: Получение имени"""
    if not message.text:
        await message.answer("Пожалуйста, введите имя текстом")
        return
    
    await state.update_data(user_name=message.text)
    await state.set_state(OrderForm.phone)
    await message.answer("📱 Введите номер телефона для связи:\n(Пример: +7 999 123-45-67)")

@dp.message(OrderForm.phone)
async def order_phone(message: Message, state: FSMContext):
    """Шаг 2: Получение телефона"""
    if not message.text:
        await message.answer("Пожалуйста, введите номер телефона")
        return
    
    await state.update_data(user_phone=message.text)
    await state.set_state(OrderForm.equipment_type)
    
    await message.answer("🔧 Какую технику нужно арендовать?", reply_markup=get_equipment_keyboard())

@dp.callback_query(OrderForm.equipment_type, F.data.startswith("eq_"))
async def order_equipment_type(callback: CallbackQuery, state: FSMContext):
    """Шаг 3: Выбор техники"""
    eq_map = {
        "eq_excavator": "Экскаватор-погрузчик",
        "eq_crane": "Автокран",
        "eq_dump": "Самосвал"
    }
    
    eq_type = eq_map.get(callback.data)
    await state.update_data(equipment_type=eq_type)
    
    # Если экскаватор - спрашиваем про навесное
    if eq_type == "Экскаватор-погрузчик":
        await state.set_state(OrderForm.excavator_attachment)
        await state.update_data(attachments=[])
        await callback.message.edit_text(
            "🔧 Какое навесное оборудование нужно?\n(можно выбрать несколько)",
            reply_markup=get_attachment_keyboard()
        )
    else:
        await state.update_data(attachments=[])
        await state.set_state(OrderForm.hours)
        await callback.message.edit_text("⏰ На сколько часов нужна техника?\n(Введите число)")
    
    await callback.answer()

@dp.callback_query(OrderForm.excavator_attachment, F.data.startswith("att_"))
async def order_attachment(callback: CallbackQuery, state: FSMContext):
    """Выбор навесного оборудования для экскаватора"""
    data = await state.get_data()
    attachments = data.get("attachments", [])
    
    if callback.data == "att_done":
        await state.update_data(attachments=attachments)
        await state.set_state(OrderForm.hours)
        att_text = ", ".join(attachments) if attachments else "без навесного"
        await callback.message.edit_text(f"✅ Выбрано: {att_text}\n\n⏰ На сколько часов нужна техника?\n(Введите число)")
        await callback.answer()
        return
    
    # Добавление/удаление оборудования
    att_name = callback.data.replace("att_", "")
    
    if att_name in attachments:
        attachments.remove(att_name)
    else:
        attachments.append(att_name)
    
    await state.update_data(attachments=attachments)
    await callback.message.edit_reply_markup(reply_markup=get_attachment_keyboard(attachments))
    await callback.answer()

@dp.message(OrderForm.hours)
async def order_hours(message: Message, state: FSMContext):
    """Шаг 4: Получение количества часов"""
    try:
        hours = int(message.text)
        if hours <= 0:
            raise ValueError
        if hours > 1000:
            await message.answer("❌ Слишком много часов. Максимум - 1000 часов")
            return
        
        await state.update_data(hours=hours)
        await state.set_state(OrderForm.date)
        await message.answer("📅 Укажите желаемую дату и время\nПример: 25.05.2026 14:00")
    except ValueError:
        await message.answer("❌ Пожалуйста, введите целое положительное число (часы)")

@dp.message(OrderForm.date)
async def order_date(message: Message, state: FSMContext):
    """Шаг 5: Получение даты"""
    if not message.text:
        await message.answer("Пожалуйста, введите дату")
        return
    
    await state.update_data(date=message.text)
    
    # Показываем подтверждение
    data = await state.get_data()
    attachments = data.get("attachments", [])
    att_text = ", ".join(attachments) if attachments else "не требуется"
    
    text = (
        f"📋 ВАША ЗАЯВКА:\n\n"
        f"👤 Имя: {data['user_name']}\n"
        f"📱 Телефон: {data['user_phone']}\n"
        f"🔧 Техника: {data['equipment_type']}\n"
        f"🧰 Навесное: {att_text}\n"
        f"⏰ Часов: {data['hours']}\n"
        f"📅 Дата: {data['date']}\n\n"
        f"✅ Подтверждаете заявку?"
    )
    
    await state.set_state(OrderForm.final)
    await message.answer(text, reply_markup=get_final_keyboard())

@dp.callback_query(OrderForm.final, F.data == "final_yes")
async def order_final_yes(callback: CallbackQuery, state: FSMContext):
    """Подтверждение заявки"""
    data = await state.get_data()
    
    # Сохраняем в БД
    order_id = save_order(
        user_id=callback.from_user.id,
        user_name=data['user_name'],
        user_phone=data['user_phone'],
        equipment_type=data['equipment_type'],
        attachments=data.get('attachments', []),
        hours=data['hours'],
        date=data['date']
    )
    
    # Отправляем админам уведомление
    for admin_id in ADMIN_IDS:
        try:
            admin_text = (
                f"🆕 НОВАЯ ЗАЯВКА #{order_id}!\n\n"
                f"👤 Клиент: {data['user_name']}\n"
                f"📱 Телефон: {data['user_phone']}\n"
                f"🔧 Техника: {data['equipment_type']}\n"
                f"🧰 Навесное: {', '.join(data.get('attachments', [])) or 'нет'}\n"
                f"⏰ Часов: {data['hours']}\n"
                f"📅 Дата: {data['date']}"
            )
            await bot.send_message(admin_id, admin_text)
        except:
            pass
    
    # Ответ пользователю
    await callback.message.edit_text(
        f"✅ ЗАЯВКА №{order_id} ПРИНЯТА!\n\n"
        f"Мы свяжемся с вами в течение 15 минут\n\n"
        f"Проверить статус: /status {order_id}"
    )
    
    await callback.answer()
    
    # Возврат в главное меню через 5 секунд
    await asyncio.sleep(5)
    await callback.message.answer("Возвращаемся в главное меню...", reply_markup=get_main_keyboard())
    await state.clear()

@dp.callback_query(OrderForm.final, F.data == "final_no")
async def order_final_no(callback: CallbackQuery, state: FSMContext):
    """Отмена заявки"""
    await state.clear()
    await callback.message.edit_text("❌ Заявка отменена")
    await callback.answer()
    await callback.message.answer("Главное меню:", reply_markup=get_main_keyboard())

@dp.callback_query(OrderForm.final, F.data == "final_edit")
async def order_final_edit(callback: CallbackQuery, state: FSMContext):
    """Редактирование заявки"""
    await state.set_state(OrderForm.name)
    await callback.message.edit_text("✏️ Давайте начнем заново.\nВведите ваше имя:")
    await callback.answer()

# ==================== РАСЧЕТ СТОИМОСТИ ====================

@dp.callback_query(F.data == "calc_start")
async def calc_start(callback: CallbackQuery, state: FSMContext):
    """Начало расчета стоимости"""
    await state.set_state(CalcForm.details)
    await callback.message.edit_text(
        "🧮 РАСЧЕТ СТОИМОСТИ\n\n"
        "Напишите, какая техника и на сколько часов вам нужна\n"
        "Пример: Экскаватор 5 часов"
    )
    await callback.answer()

@dp.message(CalcForm.details)
async def calc_details(message: Message, state: FSMContext):
    """Расчет стоимости"""
    text = message.text.lower()
    
    prices = {
        "экскаватор": 3500,
        "автокран": 3500,
        "самосвал": 3000
    }
    
    # Простой парсинг
    equipment = None
    hours = None
    
    for eq_name in prices.keys():
        if eq_name in text:
            equipment = eq_name
            break
    
    # Поиск часов в тексте
    words = text.split()
    for word in words:
        if word.isdigit():
            hours = int(word)
            break
    
    if not equipment or not hours:
        await message.answer(
            "❌ Не удалось распознать запрос.\n"
            "Напишите в формате: Техника часы\n"
            "Пример: Экскаватор 5 часов"
        )
        return
    
    total = prices[equipment] * hours
    discount = 0
    if hours >= 20:
        discount = total * 0.1
        total_with_discount = total - discount
        response = (
            f"🧮 РАСЧЕТ СТОИМОСТИ:\n\n"
            f"Техника: {equipment.capitalize()}\n"
            f"Часов: {hours}\n"
            f"Цена/час: {prices[equipment]} руб\n\n"
            f"💰 Итого: {total} руб\n"
            f"🎉 Скидка 10% за аренду от 20ч: -{int(discount)} руб\n"
            f"✅ К оплате: {int(total_with_discount)} руб"
        )
    else:
        response = (
            f"🧮 РАСЧЕТ СТОИМОСТИ:\n\n"
            f"Техника: {equipment.capitalize()}\n"
            f"Часов: {hours}\n"
            f"Цена/час: {prices[equipment]} руб\n\n"
            f"💰 Итого: {total} руб\n\n"
            f"💡 Совет: при аренде от 20 часов скидка 10%"
        )
    
    buttons = [[InlineKeyboardButton(text="📝 Заказать сейчас", callback_data="order_start")]]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await message.answer(response, reply_markup=keyboard)
    await state.clear()

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()
    await callback.message.edit_text("Главное меню:")
    await callback.message.answer("Выберите действие:", reply_markup=get_main_keyboard())
    await callback.answer()

# ==================== ЗАПУСК БОТА ====================

async def main():
    """Запуск бота"""
    # Инициализируем БД
    init_db()
    
    # Запускаем бота
    print("🤖 Бот запущен!")
    print(f"👨‍💼 Админы: {ADMIN_IDS}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())