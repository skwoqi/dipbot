from aiogram.fsm.state import State, StatesGroup


class OrderStates(StatesGroup):
    main_menu = State()
    catalog_menu = State()
    excavator_attachment = State()
    show_equipment_excavator = State()
    show_equipment_crane = State()
    show_equipment_dump = State()
    show_prices = State()
    order_name = State()
    order_phone = State()
    order_equipment_type = State()
    order_excavator_attachment = State()
    order_hours = State()
    order_date = State()
    order_final = State()
    order_saved = State()
    waiting_for_calc_details = State()
    show_contacts = State()
