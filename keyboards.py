from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


ATTACHMENTS = [("bucket", "Ковш"), ("hammer", "Гидромолот"), ("drill", "Ямобур")]


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚜 Каталог техники"), KeyboardButton(text="💰 Цены и тарифы")],
            [KeyboardButton(text="📝 Оставить заявку"), KeyboardButton(text="📞 Контакты")],
        ],
        resize_keyboard=True,
    )


def catalog_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🚧 Экскаваторы-погрузчики", callback_data="cat_excavator")
    builder.button(text="🏭 Автокраны", callback_data="cat_crane")
    builder.button(text="🚛 Самосвалы", callback_data="cat_dump")
    builder.adjust(1)
    return builder.as_markup()


def attachment_checkbox_kb(selected: list[str], prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, label in ATTACHMENTS:
        mark = "✅" if key in selected else "⬜"
        builder.button(text=f"{mark} {label}", callback_data=f"{prefix}:toggle:{key}")
    builder.button(text="✅ Готово", callback_data=f"{prefix}:done")
    builder.adjust(1)
    return builder.as_markup()


def equipment_order_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔧 Заказать эту технику", callback_data="order_this")
    return builder.as_markup()


def prices_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🧮 Рассчитать стоимость", callback_data="calc")
    builder.button(text="📝 Заказать", callback_data="order")
    builder.adjust(1)
    return builder.as_markup()


def equipment_choice_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🚧 Экскаватор-погрузчик", callback_data="order_eq_excavator")
    builder.button(text="🏭 Автокран", callback_data="order_eq_crane")
    builder.button(text="🚛 Самосвал", callback_data="order_eq_dump")
    builder.adjust(1)
    return builder.as_markup()


def order_final_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да", callback_data="order_confirm")
    builder.button(text="❌ Нет", callback_data="order_cancel")
    builder.button(text="✏️ Редактировать", callback_data="order_edit")
    builder.adjust(1)
    return builder.as_markup()


def contacts_back_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data="back_main")
    return builder.as_markup()


def order_from_calc_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Заказать", callback_data="from_calc_order")
    return builder.as_markup()
