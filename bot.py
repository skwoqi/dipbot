import asyncio
import json
import logging
import os
import re
from datetime import datetime
from typing import Any

from vkbottle import Bot, CtxStorage, Keyboard, KeyboardButtonColor, PhotoMessageUploader, Text

from config import ADMIN_PEER_ID, DB_PATH, GROUP_ID, VK_BOT_TOKEN
from db import Database

logging.basicConfig(level=logging.INFO)

db = Database(DB_PATH)
bot = Bot(token=VK_BOT_TOKEN)
uploader = PhotoMessageUploader(bot.api)
storage = CtxStorage()

PHONE_RE = re.compile(r"^[+]?[0-9()\-\s]{10,20}$")
ATTACHMENTS = [("bucket", "Ковш"), ("hammer", "Гидромолот"), ("drill", "Ямобур")]
ATTACHMENT_LABELS = dict(ATTACHMENTS)


class State:
    MAIN = "main"
    ORDER_NAME = "order_name"
    ORDER_PHONE = "order_phone"
    ORDER_HOURS = "order_hours"
    ORDER_DATE = "order_date"
    ORDER_ATTACHMENTS = "order_attachments"
    CALC = "calc"
    ADMIN_ADD_TITLE = "admin_add_title"
    ADMIN_ADD_DESC = "admin_add_desc"
    ADMIN_ADD_PRICE = "admin_add_price"
    ADMIN_ADD_PHOTO = "admin_add_photo"
    ADMIN_ADD_ATTACHMENTS = "admin_add_attachments"


def is_admin(user_id: int) -> bool:
    return ADMIN_PEER_ID != 0 and user_id == ADMIN_PEER_ID


def get_state(user_id: int) -> str:
    return storage.get(f"state:{user_id}") or State.MAIN


def set_state(user_id: int, state: str) -> None:
    storage.set(f"state:{user_id}", state)


def get_data(user_id: int) -> dict[str, Any]:
    return storage.get(f"data:{user_id}") or {}


def update_data(user_id: int, **kwargs: Any) -> dict[str, Any]:
    data = get_data(user_id)
    data.update(kwargs)
    storage.set(f"data:{user_id}", data)
    return data


def clear_data(user_id: int) -> None:
    storage.set(f"data:{user_id}", {})


def payload(raw_payload: str | None) -> dict[str, Any]:
    if not raw_payload:
        return {}
    try:
        return json.loads(raw_payload)
    except json.JSONDecodeError:
        return {}


def is_start(text: str) -> bool:
    return text.strip().lower() in {"/start", "start", "начать", "старт"}


def main_menu_kb() -> str:
    kb = Keyboard(one_time=False, inline=False)
    kb.add(Text("🚜 Каталог"))
    kb.add(Text("💰 Цены"))
    kb.row()
    kb.add(Text("📝 Оставить заявку"))
    kb.add(Text("📞 Контакты"))
    return kb.get_json()


def admin_kb() -> str:
    kb = Keyboard(one_time=False, inline=True)
    kb.add(Text("📊 Статистика", payload={"cmd": "admin_stats"}))
    kb.row()
    kb.add(Text("📋 Заявки", payload={"cmd": "admin_orders"}))
    kb.row()
    kb.add(Text("🚜 Каталог", payload={"cmd": "admin_catalog"}))
    kb.row()
    kb.add(Text("➕ Добавить технику", payload={"cmd": "admin_add", "type": "equipment"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Text("➕ Добавить услугу", payload={"cmd": "admin_add", "type": "service"}), color=KeyboardButtonColor.POSITIVE)
    return kb.get_json()


def catalog_kb(items: list[dict[str, Any]]) -> str:
    kb = Keyboard(one_time=False, inline=True)
    for item in items:
        label = f"{'🚜' if item['item_type'] == 'equipment' else '🛠'} {item['title']}"
        kb.add(Text(label, payload={"cmd": "catalog_item", "id": item["id"]}))
        kb.row()
    kb.add(Text("📝 Оставить заявку", payload={"cmd": "order"}), color=KeyboardButtonColor.POSITIVE)
    return kb.get_json()


def catalog_order_kb(items: list[dict[str, Any]]) -> str:
    kb = Keyboard(one_time=False, inline=True)
    for item in items:
        kb.add(Text(item["title"], payload={"cmd": "order_item", "id": item["id"]}))
        kb.row()
    return kb.get_json()


def item_order_kb(item_id: int) -> str:
    kb = Keyboard(one_time=False, inline=True)
    kb.add(Text("🔧 Заказать", payload={"cmd": "order_item", "id": item_id}), color=KeyboardButtonColor.POSITIVE)
    return kb.get_json()


def attachment_kb(selected: list[str], prefix: str) -> str:
    kb = Keyboard(one_time=False, inline=True)
    for key, title in ATTACHMENTS:
        mark = "✅" if key in selected else "⬜"
        kb.add(Text(f"{mark} {title}", payload={"cmd": prefix, "action": "toggle", "value": key}))
        kb.row()
    kb.add(Text("✅ Готово", payload={"cmd": prefix, "action": "done"}), color=KeyboardButtonColor.POSITIVE)
    return kb.get_json()


def confirm_kb() -> str:
    kb = Keyboard(one_time=False, inline=True)
    kb.add(Text("✅ Да", payload={"cmd": "order_confirm"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Text("❌ Нет", payload={"cmd": "order_cancel"}), color=KeyboardButtonColor.NEGATIVE)
    kb.row()
    kb.add(Text("✏️ Редактировать", payload={"cmd": "order_edit"}))
    return kb.get_json()


def admin_catalog_kb(items: list[dict[str, Any]]) -> str:
    kb = Keyboard(one_time=False, inline=True)
    for item in items:
        kb.add(Text(f"🗑 {item['id']}. {item['title']}", payload={"cmd": "admin_delete_item", "id": item["id"]}), color=KeyboardButtonColor.NEGATIVE)
        kb.row()
    kb.add(Text("➕ Добавить технику", payload={"cmd": "admin_add", "type": "equipment"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Text("➕ Добавить услугу", payload={"cmd": "admin_add", "type": "service"}), color=KeyboardButtonColor.POSITIVE)
    return kb.get_json()


async def send(peer_id: int, message: str, keyboard: str | None = None, attachment: str | None = None) -> None:
    params = {"peer_id": peer_id, "random_id": 0, "message": message}
    if keyboard:
        params["keyboard"] = keyboard
    if attachment:
        params["attachment"] = attachment
    await bot.api.messages.send(**params)


async def upload_photo(photo: str | None) -> tuple[str | None, str | None]:
    if not photo:
        return None, None
    photo = photo.strip()
    if os.path.exists(photo):
        try:
            return await uploader.upload(photo), None
        except Exception as exc:
            logging.warning("Cannot upload photo %s: %s", photo, exc)
            return None, None
    if photo.startswith("photo"):
        return photo, None
    if photo.startswith(("http://", "https://")):
        return None, f"\nФото: {photo}"
    return None, None


def price_text(item: dict[str, Any]) -> str:
    price = item.get("price_per_hour")
    return f"{price} руб/час" if price else "по договоренности"


def attachments_text(keys: list[str] | None) -> str:
    if not keys:
        return "не требуется"
    return ", ".join(ATTACHMENT_LABELS.get(key, key) for key in keys)


def order_summary(data: dict[str, Any]) -> str:
    return (
        "📋 ВАША ЗАЯВКА:\n"
        f"Имя: {data.get('user_name', '-')}\n"
        f"Телефон: {data.get('user_phone', '-')}\n"
        f"Позиция: {data.get('equipment_type', '-')}\n"
        f"Навесное: {attachments_text(data.get('attachments'))}\n"
        f"Часов: {data.get('hours', '-')}\n"
        f"Дата: {data.get('date', '-')}\n\n"
        "Подтверждаете заявку?"
    )


async def main_menu(peer_id: int, user_id: int) -> None:
    set_state(user_id, State.MAIN)
    await send(peer_id, "Добро пожаловать! 🚜 Аренда спецтехники и услуги.", main_menu_kb())


async def show_catalog(peer_id: int) -> None:
    items = db.list_catalog_items(active_only=True)
    if not items:
        await send(peer_id, "Каталог пока пуст.")
        return
    await send(peer_id, "Выберите технику или услугу:", catalog_kb(items))


async def show_item(peer_id: int, item_id: int) -> None:
    item = db.get_catalog_item(item_id)
    if not item or not item.get("is_active"):
        await send(peer_id, "Позиция не найдена.")
        return
    attachment, photo_note = await upload_photo(item.get("photo"))
    text = (
        f"{item['title']}\n\n"
        f"{item.get('description') or 'Описание пока не добавлено.'}\n\n"
        f"Цена: {price_text(item)}"
        f"{photo_note or ''}"
    )
    if item.get("attachments_enabled"):
        text += "\nМожно выбрать навесное оборудование."
    await send(peer_id, text, item_order_kb(item_id), attachment)


async def show_prices(peer_id: int) -> None:
    items = db.list_catalog_items(active_only=True)
    if not items:
        await send(peer_id, "Цены пока не добавлены.")
        return
    lines = ["💰 Цены:"]
    for item in items:
        lines.append(f"- {item['title']}: {price_text(item)}")
    kb = Keyboard(one_time=False, inline=True)
    kb.add(Text("🧮 Рассчитать стоимость", payload={"cmd": "calc"}))
    kb.row()
    kb.add(Text("📝 Заказать", payload={"cmd": "order"}), color=KeyboardButtonColor.POSITIVE)
    await send(peer_id, "\n".join(lines), kb.get_json())


async def start_order(peer_id: int, user_id: int, item: dict[str, Any] | None = None) -> None:
    clear_data(user_id)
    data = {"customer_user_id": user_id, "attachments": []}
    if item:
        data.update(
            {
                "catalog_item_id": item["id"],
                "equipment_type": item["title"],
                "attachments_enabled": bool(item.get("attachments_enabled")),
            }
        )
    update_data(user_id, **data)
    set_state(user_id, State.ORDER_NAME)
    await send(peer_id, "Введите ваше имя:")


async def ask_item_for_order(peer_id: int, user_id: int) -> None:
    items = db.list_catalog_items(active_only=True)
    if not items:
        await send(peer_id, "Каталог пуст. Пока нечего заказать.")
        return
    set_state(user_id, State.MAIN)
    await send(peer_id, "Что хотите заказать?", catalog_order_kb(items))


async def choose_order_item(peer_id: int, user_id: int, item_id: int) -> None:
    item = db.get_catalog_item(item_id)
    if not item or not item.get("is_active"):
        await send(peer_id, "Позиция не найдена.")
        return
    update_data(
        user_id,
        catalog_item_id=item["id"],
        equipment_type=item["title"],
        attachments_enabled=bool(item.get("attachments_enabled")),
        attachments=[],
    )
    if item.get("attachments_enabled"):
        set_state(user_id, State.ORDER_ATTACHMENTS)
        await send(peer_id, "Какое навесное оборудование нужно? Можно выбрать несколько.", attachment_kb([], "order_attach"))
        return
    set_state(user_id, State.ORDER_HOURS)
    await send(peer_id, "На сколько часов нужна техника или услуга?")


async def admin_panel(peer_id: int, user_id: int) -> None:
    if not is_admin(user_id):
        await send(peer_id, "Нет доступа к админ-панели.")
        return
    await send(peer_id, "Админ-панель:", admin_kb())


async def admin_catalog(peer_id: int) -> None:
    items = db.list_catalog_items(active_only=True)
    if not items:
        await send(peer_id, "Каталог пуст.", admin_catalog_kb([]))
        return
    lines = ["Каталог:"]
    for item in items:
        kind = "техника" if item["item_type"] == "equipment" else "услуга"
        lines.append(f"{item['id']}. {item['title']} ({kind}) - {price_text(item)}")
    await send(peer_id, "\n".join(lines), admin_catalog_kb(items))


async def admin_orders(peer_id: int) -> None:
    orders = db.list_orders()
    if not orders:
        await send(peer_id, "Заявок пока нет.")
        return
    lines = ["Последние заявки:"]
    for order in orders:
        lines.append(f"#{order['id']} | {order['user_name']} | {order['equipment_type']} | {order['status']}")
    await send(peer_id, "\n".join(lines))


async def admin_stats(peer_id: int) -> None:
    stats = db.orders_stats()
    await send(
        peer_id,
        "📊 Статистика заявок:\n"
        f"Новых: {stats['new']}\n"
        f"Подтвержденных: {stats['confirmed']}\n"
        f"Выполненных: {stats['completed']}\n"
        f"Отмененных: {stats['cancelled']}\n"
        f"Всего: {stats['total']}",
    )


async def start_admin_add(peer_id: int, user_id: int, item_type: str) -> None:
    clear_data(user_id)
    update_data(user_id, admin_item_type=item_type)
    set_state(user_id, State.ADMIN_ADD_TITLE)
    label = "техники" if item_type == "equipment" else "услуги"
    await send(peer_id, f"Введите название {label}:")


async def handle_admin_add_text(peer_id: int, user_id: int, text: str, state: str) -> bool:
    if state == State.ADMIN_ADD_TITLE:
        update_data(user_id, admin_title=text)
        set_state(user_id, State.ADMIN_ADD_DESC)
        await send(peer_id, "Введите описание:")
        return True
    if state == State.ADMIN_ADD_DESC:
        update_data(user_id, admin_description=text)
        set_state(user_id, State.ADMIN_ADD_PRICE)
        await send(peer_id, "Введите цену за час числом. Если цена договорная, отправьте 0:")
        return True
    if state == State.ADMIN_ADD_PRICE:
        if not text.isdigit():
            await send(peer_id, "Введите число, например 3500 или 0.")
            return True
        update_data(user_id, admin_price=int(text))
        set_state(user_id, State.ADMIN_ADD_PHOTO)
        await send(peer_id, "Введите путь к фото/URL или отправьте '-' без фото:")
        return True
    if state == State.ADMIN_ADD_PHOTO:
        photo = "" if text == "-" else text
        data = update_data(user_id, admin_photo=photo)
        if data.get("admin_item_type") == "service":
            item_id = db.create_catalog_item(
                {
                    "item_type": "service",
                    "title": data["admin_title"],
                    "description": data["admin_description"],
                    "price_per_hour": data["admin_price"],
                    "photo": photo,
                    "attachments_enabled": False,
                }
            )
            clear_data(user_id)
            set_state(user_id, State.MAIN)
            await send(peer_id, f"Услуга добавлена в каталог. ID: {item_id}", admin_kb())
            return True
        set_state(user_id, State.ADMIN_ADD_ATTACHMENTS)
        kb = Keyboard(one_time=False, inline=True)
        kb.add(Text("Да", payload={"cmd": "admin_add_attach", "value": 1}), color=KeyboardButtonColor.POSITIVE)
        kb.row()
        kb.add(Text("Нет", payload={"cmd": "admin_add_attach", "value": 0}), color=KeyboardButtonColor.NEGATIVE)
        await send(peer_id, "Нужен выбор навесного оборудования?", kb.get_json())
        return True
    return False


async def finish_admin_equipment(peer_id: int, user_id: int, attachments_enabled: bool) -> None:
    data = get_data(user_id)
    item_id = db.create_catalog_item(
        {
            "item_type": "equipment",
            "title": data["admin_title"],
            "description": data["admin_description"],
            "price_per_hour": data["admin_price"],
            "photo": data.get("admin_photo", ""),
            "attachments_enabled": attachments_enabled,
        }
    )
    clear_data(user_id)
    set_state(user_id, State.MAIN)
    await send(peer_id, f"Техника добавлена в каталог. ID: {item_id}", admin_kb())


@bot.on.private_message()
async def handle_message(message) -> None:
    if not message.from_id or message.from_id < 0:
        return
    user_id = message.from_id
    peer_id = message.peer_id
    text = (message.text or "").strip()
    data = payload(message.payload)
    cmd = data.get("cmd")
    state = get_state(user_id)
    logging.info("INCOMING user=%s text=%r payload=%r", user_id, text, message.payload)

    db.save_user(user_id, None, f"id{user_id}")

    if is_start(text) or cmd == "start":
        await main_menu(peer_id, user_id)
        return
    if text == "🚜 Каталог":
        await show_catalog(peer_id)
        return
    if text == "💰 Цены":
        await show_prices(peer_id)
        return
    if text == "📝 Оставить заявку" or cmd == "order":
        await ask_item_for_order(peer_id, user_id)
        return
    if text == "📞 Контакты":
        await send(
            peer_id,
            "📞 КОНТАКТЫ:\n"
            "Телефон: +7 (XXX) XXX-XX-XX\n"
            "Telegram: @manager\n"
            "Адрес: ул. Строителей, 15\n\n"
            "Режим работы: 24/7",
        )
        return

    if text.startswith("/admin"):
        if text.startswith("/admin_stats"):
            if is_admin(user_id):
                await admin_stats(peer_id)
            return
        if text.startswith("/admin_list"):
            if is_admin(user_id):
                await admin_orders(peer_id)
            return
        if text.startswith("/admin_view"):
            parts = text.split(maxsplit=1)
            if not is_admin(user_id) or len(parts) < 2 or not parts[1].isdigit():
                return
            order = db.get_order(int(parts[1]))
            await send(peer_id, json.dumps(order, ensure_ascii=False, indent=2) if order else "Заявка не найдена.")
            return
        if text.startswith("/admin_confirm") or text.startswith("/admin_done") or text.startswith("/admin_delete"):
            if not is_admin(user_id):
                return
            parts = text.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].isdigit():
                await send(peer_id, "Укажите id заявки.")
                return
            order_id = int(parts[1])
            if text.startswith("/admin_delete"):
                ok = db.delete_order(order_id)
                action = "удалена"
            else:
                status = "confirmed" if text.startswith("/admin_confirm") else "completed"
                ok = db.update_order_status(order_id, status)
                action = f"статус изменен на {status}"
            await send(peer_id, f"Заявка #{order_id}: {action}" if ok else "Заявка не найдена.")
            return
        await admin_panel(peer_id, user_id)
        return

    if cmd == "catalog_item":
        await show_item(peer_id, int(data["id"]))
        return
    if cmd == "order_item":
        await start_order(peer_id, user_id, db.get_catalog_item(int(data["id"])))
        return
    if cmd == "calc":
        set_state(user_id, State.CALC)
        await send(peer_id, 'Какая позиция и на сколько часов? Например: "Экскаватор 5 часов"')
        return

    if is_admin(user_id):
        if cmd == "admin_stats":
            await admin_stats(peer_id)
            return
        if cmd == "admin_orders":
            await admin_orders(peer_id)
            return
        if cmd == "admin_catalog":
            await admin_catalog(peer_id)
            return
        if cmd == "admin_add":
            await start_admin_add(peer_id, user_id, data.get("type", "equipment"))
            return
        if cmd == "admin_delete_item":
            ok = db.delete_catalog_item(int(data["id"]))
            await send(peer_id, "Позиция удалена." if ok else "Позиция не найдена.", admin_kb())
            return
        if cmd == "admin_add_attach":
            await finish_admin_equipment(peer_id, user_id, bool(data.get("value")))
            return

    if cmd == "order_attach":
        selected = get_data(user_id).get("attachments", [])
        action = data.get("action")
        value = data.get("value")
        if action == "toggle" and value:
            selected.remove(value) if value in selected else selected.append(value)
            update_data(user_id, attachments=selected)
            await send(peer_id, f"Выбрано: {attachments_text(selected)}", attachment_kb(selected, "order_attach"))
            return
        if action == "done":
            set_state(user_id, State.ORDER_HOURS)
            await send(peer_id, "На сколько часов нужна техника или услуга?")
            return
    if cmd == "order_confirm":
        order_data = get_data(user_id)
        order_id = db.create_order(order_data)
        await send(
            peer_id,
            f"✅ ЗАЯВКА №{order_id} ПРИНЯТА!\n\n"
            "Мы свяжемся с вами в течение 15 минут.\n\n"
            f"Проверить статус: /status {order_id}",
        )
        if ADMIN_PEER_ID:
            try:
                await send(ADMIN_PEER_ID, f"Новая заявка №{order_id}\n\n{order_summary(order_data)}")
            except Exception as exc:
                logging.warning("Cannot notify admin: %s", exc)
        await asyncio.sleep(3)
        clear_data(user_id)
        await main_menu(peer_id, user_id)
        return
    if cmd == "order_cancel":
        clear_data(user_id)
        await main_menu(peer_id, user_id)
        return
    if cmd == "order_edit":
        await ask_item_for_order(peer_id, user_id)
        return

    if text.startswith("/status"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].isdigit():
            await send(peer_id, "Укажите номер заявки: /status 123")
            return
        order = db.get_order(int(parts[1]))
        if not order:
            await send(peer_id, "Заявка не найдена.")
            return
        await send(peer_id, f"Заявка №{order['id']}\nСтатус: {order['status']}\nПозиция: {order['equipment_type']}\nДата: {order['date']}")
        return
    if text.startswith("/help"):
        await send(peer_id, "/start - главное меню\n/status <id> - статус заявки\n/admin - админ-панель")
        return

    if await handle_admin_add_text(peer_id, user_id, text, state):
        return

    if state == State.CALC:
        lower = text.lower()
        hours_match = re.search(r"(\d+)", lower)
        hours = int(hours_match.group(1)) if hours_match else 1
        items = db.list_catalog_items(active_only=True)
        found = next((item for item in items if item["title"].lower().split()[0] in lower), None)
        if not found:
            found = items[0] if items else None
        if found and found.get("price_per_hour"):
            total = int(found["price_per_hour"]) * hours
            await send(peer_id, f"Примерная стоимость: {total} руб.", catalog_order_kb(items))
        else:
            await send(peer_id, "Стоимость по договоренности. Оставьте заявку, и менеджер уточнит цену.", catalog_order_kb(items))
        set_state(user_id, State.MAIN)
        return

    if state == State.ORDER_NAME:
        update_data(user_id, user_name=text)
        set_state(user_id, State.ORDER_PHONE)
        await send(peer_id, "Введите номер телефона для связи:")
        return
    if state == State.ORDER_PHONE:
        if not PHONE_RE.match(text):
            await send(peer_id, "Похоже на неверный формат. Введите номер еще раз.")
            return
        order_data = update_data(user_id, user_phone=text)
        if not order_data.get("equipment_type"):
            await ask_item_for_order(peer_id, user_id)
            return
        if order_data.get("attachments_enabled"):
            set_state(user_id, State.ORDER_ATTACHMENTS)
            await send(peer_id, "Какое навесное оборудование нужно? Можно выбрать несколько.", attachment_kb([], "order_attach"))
            return
        set_state(user_id, State.ORDER_HOURS)
        await send(peer_id, "На сколько часов нужна техника или услуга?")
        return
    if state == State.ORDER_HOURS:
        hours_match = re.search(r"\d+", text)
        if not hours_match:
            await send(peer_id, "Введите число часов, например: 8")
            return
        update_data(user_id, hours=int(hours_match.group(0)))
        set_state(user_id, State.ORDER_DATE)
        await send(peer_id, "Укажите желаемую дату и время, например: 25.05.2026 14:00")
        return
    if state == State.ORDER_DATE:
        try:
            datetime.strptime(text, "%d.%m.%Y %H:%M")
        except ValueError:
            await send(peer_id, "Формат даты: ДД.ММ.ГГГГ ЧЧ:ММ, например: 25.05.2026 14:00")
            return
        order_data = update_data(user_id, date=text)
        await send(peer_id, order_summary(order_data), confirm_kb())
        return

    await send(peer_id, "Используйте /start для главного меню.")


def validate_config() -> None:
    if not VK_BOT_TOKEN:
        raise RuntimeError("Укажите VK_BOT_TOKEN в переменных окружения Bothost.")
    if GROUP_ID == 0:
        logging.warning("GROUP_ID не задан. Для VK Long Poll обычно нужен ID сообщества.")
