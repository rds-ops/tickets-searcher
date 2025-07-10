import json
import logging
from datetime import datetime, date
from pathlib import Path

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from states.search import Search
from utils.localization import get_iata, city_by_iata
from utils.logger import log_action  # action-логи в JSON

logger = logging.getLogger(__name__)
router = Router()

# ─────────────────────────────────────────────
#                 Константы
# ─────────────────────────────────────────────
YEARS = [2025, 2026]
MONTHS_RU = [
    "Янв", "Фев", "Мар", "Апр", "Май", "Июн",
    "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек",
]
MONTHS_UZ = [
    "Yan", "Fev", "Mar", "Apr", "May", "Iyn",
    "Iyl", "Avg", "Sen", "Okt", "Noy", "Dek",
]

LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "user_logs.json"
LOG_PATH.touch(exist_ok=True)


def save_flow_log(user_id: int, step: str, payload: dict):
    """Бросаем клик в файл-лог (каждая строка — JSON)."""
    with LOG_PATH.open("a", encoding="utf-8") as f:
        json.dump(
            {
                "user_id": user_id,
                "ts": datetime.utcnow().isoformat(),
                "step": step,
                "payload": payload,
            },
            f,
            ensure_ascii=False,
        )
        f.write("\n")

# ─────────────────────────────────────────────
#          Inline-клавиатуры-конструкторы
# ─────────────────────────────────────────────
def build_lang_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🇷🇺 Русский", callback_data="lang_ru")
    kb.button(text="🇺🇿 Oʻzbek",  callback_data="lang_uz")
    kb.adjust(2)
    return kb.as_markup()


def build_year_kb(lang: str, return_flow: bool = False) -> InlineKeyboardMarkup:
    """Года не фильтруем (проще) – ведь list уже ‘будущее’."""
    kb = InlineKeyboardBuilder()
    for y in YEARS:
        kb.button(text=str(y), callback_data=f"y_{y}{'_ret' if return_flow else ''}")
    if return_flow:
        kb.row(
            InlineKeyboardButton(
                text="❌ Без обратного" if lang == "ru" else "❌ Qaytishsiz",
                callback_data="no_ret",
            )
        )
    kb.adjust(2)
    return kb.as_markup()


def build_month_kb(
    year: int,
    lang: str,
    return_flow: bool = False,
    min_date: date | None = None,
) -> InlineKeyboardMarkup:
    """
    month-kbd с фильтром:
    • если min_date = 2025-07-03, то в 2025 показываем Jul…Dec,
      а в 2026 – Jan…Dec (всё норм).
    """
    names = MONTHS_RU if lang == "ru" else MONTHS_UZ
    kb = InlineKeyboardBuilder()

    min_date = min_date or date.today()
    for idx, name in enumerate(names, start=1):
        if date(year, idx, 1) < min_date.replace(day=1):
            continue  # месяц в прошлом – пропускаем
        kb.button(
            text=name,
            callback_data=f"m_{year}_{idx}{'_ret' if return_flow else ''}",
        )

    kb.adjust(3, 3, 3, 3)
    kb.row(
        InlineKeyboardButton(
            text="⬅ Назад" if lang == "ru" else "⬅ Orqaga",
            callback_data=f"back_year{'_ret' if return_flow else ''}",
        )
    )
    return kb.as_markup()


def build_day_kb(
    year: int,
    month: int,
    lang: str,
    return_flow: bool = False,
    min_date: date | None = None,
) -> InlineKeyboardMarkup:
    """
    В «живом» месяце скрываем прошлые дни.
    Для возврата min_date = departure_date (+1 день опционально).
    """
    import calendar

    min_date = min_date or date.today()
    days_cnt = calendar.monthrange(year, month)[1]
    kb = InlineKeyboardBuilder()

    for d in range(1, days_cnt + 1):
        cand = date(year, month, d)
        if cand < min_date:
            continue  # скрываем прошедший день
        kb.button(
            text=str(d),
            callback_data=f"d_{year}_{month}_{d}{'_ret' if return_flow else ''}",
        )

    kb.adjust(7)
    kb.row(
        InlineKeyboardButton(
            text="⬅ Назад" if lang == "ru" else "⬅ Orqaga",
            callback_data=f"back_month_{year}{'_ret' if return_flow else ''}",
        )
    )
    return kb.as_markup()


def build_pax_kb(ad: int, ch: int, inf: int, lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    def add_row(kind, icon, qty):
        kb.row(
            InlineKeyboardButton(text="➖", callback_data=f"{kind}_-"),
            InlineKeyboardButton(text=f"{icon} {qty}", callback_data="noop"),
            InlineKeyboardButton(text="➕", callback_data=f"{kind}_+"),
        )

    add_row("a", "👤", ad)
    add_row("c", "🧒", ch)
    add_row("i", "👶", inf)

    kb.row(InlineKeyboardButton(text="✅ OK", callback_data="pax_ok"))
    return kb.as_markup()

# ─────────────────────────────────────────────
#            Служебные функции
# ─────────────────────────────────────────────
def build_aviasales_url(
    origin: str,
    dest: str,
    dep: str,
    ret: str,
    adults: int,
    children: int,
    infants: int,
    lang: str,
) -> str:
    trim = lambda d: datetime.strptime(d, "%Y-%m-%d").strftime("%d%m")
    dep_part = trim(dep)
    ret_part = trim(ret) if ret else ""
    path = f"{origin}{dep_part}{dest}{ret_part}{adults}"
    return (
        f"https://aviasales.uz/search/{path}"
        f"?adults={adults}&children={children}&infants={infants}&language={lang}"
    )

def _city_label(iata: str, lang: str) -> str:
    """
    Возвращает «Город (IATA)», но не дублирует код,
    если city_by_iata уже вернул его в скобках.
    """
    raw = city_by_iata(iata, lang)
    if f"({iata})" in raw.upper():      # код уже присутствует
        return raw
    return f"{raw} ({iata})"

# ─────────────────────────────────────────────
#                   Хэндлеры
# ─────────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    await state.set_state(Search.lang)
    await msg.answer("Выберите язык / Tilni tanlang", reply_markup=build_lang_kb())
    save_flow_log(msg.from_user.id, "start", {})

# 1️⃣ язык
@router.callback_query(lambda c: c.data.startswith("lang_"), Search.lang)
async def choose_lang(callback: CallbackQuery, state: FSMContext):
    lang = "ru" if callback.data == "lang_ru" else "uz"
    await state.update_data(lang=lang)
    await state.set_state(Search.origin)

    await callback.message.edit_reply_markup(reply_markup=None)
    prompt = "Введите город вылета:" if lang == "ru" else "Qayerdan uchasiz?"
    await callback.message.answer(prompt, reply_markup=ReplyKeyboardRemove())

    save_flow_log(callback.from_user.id, "lang", {"lang": lang})
    await callback.answer()

# 2️⃣ origin
@router.message(Search.origin)
async def set_origin(msg: Message, state: FSMContext):
    data = await state.get_data()
    lang = data["lang"]
    iata = get_iata(msg.text)
    if not iata:
        await msg.answer(
            "Введите корректный город." if lang == "ru" else "Shahar nomini to'g'ri kiriting."
        )
        return
    await state.update_data(origin=iata)
    await state.set_state(Search.destination)
    await msg.answer("Введите город прилёта:" if lang == "ru" else "Qayerga uchasiz?")

    save_flow_log(msg.from_user.id, "origin", {"iata": iata})

# 3️⃣ destination
@router.message(Search.destination)
async def set_destination(msg: Message, state: FSMContext):
    data = await state.get_data()
    lang = data["lang"]
    iata = get_iata(msg.text)
    if not iata:
        await msg.answer(
            "Город не найден, попробуйте ещё." if lang == "ru" else "Shahar topilmadi, qayta kiriting."
        )
        return
    await state.update_data(destination=iata)
    await state.set_state(Search.departure_date)

    await msg.answer(
        "Выберите год вылета:" if lang == "ru" else "Jo'nab ketish yili:",
        reply_markup=build_year_kb(lang),
    )
    save_flow_log(msg.from_user.id, "destination", {"iata": iata})

# ─────────────────────────────────────────────
#        4-6: год / мес / день + BACK
# ─────────────────────────────────────────────
@router.callback_query(lambda c: c.data.startswith(("y_", "m_", "d_", "back_", "no_ret")))
async def date_nav(callback: CallbackQuery, state: FSMContext):
    cd = callback.data
    st_data = await state.get_data()
    lang = st_data.get("lang", "ru")
    is_ret = cd.endswith("_ret") or cd == "no_ret"

    # вычисляем «минимально допустимую» дату для текущего потока
    dep_date_obj = (
        date.fromisoformat(st_data["departure_date"])
        if st_data.get("departure_date")
        else date.today()
    )
    min_date = dep_date_obj if is_ret else date.today()

    # ───── год ─────
    if cd.startswith("y_"):
        _, y, *_ = cd.split("_")
        y = int(y)
        await state.update_data(**({"dep_year": y} if not is_ret else {"ret_year": y}))
        await callback.message.edit_reply_markup(
            reply_markup=build_month_kb(y, lang, is_ret, min_date)
        )
        save_flow_log(callback.from_user.id, "year", {"y": y, "ret": is_ret})
        return await callback.answer()

    # ───── месяц ─────
    if cd.startswith("m_"):
        _, y, m, *_ = cd.split("_")
        y, m = int(y), int(m)
        await state.update_data(**({"dep_month": m} if not is_ret else {"ret_month": m}))
        await callback.message.edit_reply_markup(
            reply_markup=build_day_kb(y, m, lang, is_ret, min_date)
        )
        save_flow_log(callback.from_user.id, "month", {"y": y, "m": m, "ret": is_ret})
        return await callback.answer()

    # ───── день ─────
    if cd.startswith("d_"):
        _, y, m, d, *_ = cd.split("_")
        y, m, d = int(y), int(m), int(d)
        date_str = f"{y}-{m:02}-{d:02}"

        if not is_ret:
            await state.update_data(departure_date=date_str)
            await state.set_state(Search.return_date)
            await callback.message.answer(
                "Выберите год обратного рейса или ❌ если он не нужен:"
                if lang == "ru"
                else "Qaytish yili yoki ❌ kerak bo'lmasa:",
                reply_markup=build_year_kb(lang, return_flow=True),
            )
        else:
            await state.update_data(return_date=date_str)
            await ask_passengers(callback.message, state)

        save_flow_log(callback.from_user.id, "day", {"date": date_str, "ret": is_ret})
        return await callback.answer()

    # ───── BACK (к годам) ─────
    if cd.startswith("back_year"):
        await callback.message.edit_reply_markup(
            reply_markup=build_year_kb(lang, "_ret" in cd)
        )
        return await callback.answer()

    # ───── BACK (к месяцам) ─────
    if cd.startswith("back_month_"):
        parts = cd.split("_")
        y = int(parts[2])
        await callback.message.edit_reply_markup(
            reply_markup=build_month_kb(y, lang, "_ret" in cd, min_date)
        )
        return await callback.answer()

    # ───── без возврата ─────
    if cd == "no_ret":
        await state.update_data(return_date="")
        await ask_passengers(callback.message, state)
        save_flow_log(callback.from_user.id, "no_ret", {})
        return await callback.answer()

# ─────────────────────────────────────────────
#        7: пассажиры
# ─────────────────────────────────────────────
async def send_review(msg: Message, state: FSMContext):
    """
    Отправляет красивое превью перед подтверждением:
      • маршрут
      • даты (туда / обратно)
      • состав пассажиров
      • кнопка «Подтвердить»
    """
    data = await state.get_data()
    lang = data["lang"]

    # — текст —
    head = (
        "🔍 <b>Проверьте данные перед переходом</b>\n"
        "и убедитесь, что они верны на сайте.\n"
        if lang == "ru"
        else
        "🔍 <b>Saytga o‘tishdan oldin ma’lumotlarni tekshiring</b>\n"
        "va ularning to‘g‘riligiga ishonch hosil qiling.\n"
    )

    route = (
        f"📍 {city_by_iata(data['origin'], lang)} → "
        f"{city_by_iata(data['destination'], lang)}\n"
    )

    dates = f"🛫 {data['departure_date']}"
    if data.get("return_date"):
        dates += f"  🛬 {data['return_date']}"
    dates += "\n"

    pax = f"👤 {data['adults']}  🧒 {data['children']}  👶 {data['infants']}"

    text = head + route + dates + pax

    # — клавиатура —
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ Подтвердить" if lang == "ru" else "✅ Tasdiqlash",
        callback_data="confirm",
    )

    await msg.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")


# ─────────────────────────────────────────────
async def ask_passengers(msg: Message | CallbackQuery, state: FSMContext):
    # стартовые значения
    await state.update_data(adults=1, children=0, infants=0)

    lang = (await state.get_data())["lang"]
    text = (
        "<b>Укажите количество пассажиров</b>\n"
        "👤 <i>Взрослые (12 +)</i>\n"
        "🧒 <i>Дети (2 – 11)</i>\n"
        "👶 <i>Младенцы (0 – 1)</i>"
        if lang == "ru"
        else
        "<b>Yo‘lovchilar sonini tanlang</b>\n"
        "👤 <i>Kattalar (12 +)</i>\n"
        "🧒 <i>Bola (2 – 11)</i>\n"
        "👶 <i>Go‘dak (0 – 1)</i>"
    )

    kb   = build_pax_kb(1, 0, 0, lang)
    send = msg.edit_text if isinstance(msg, CallbackQuery) else msg.answer
    await send(text, reply_markup=kb, parse_mode="HTML")

    await state.set_state(Search.adults)


@router.callback_query(
    lambda c: c.data in {"a_+", "a_-", "c_+", "c_-", "i_+", "i_-", "pax_ok"},
    Search.adults,
)
async def pax_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data["lang"]
    act  = callback.data

    # ───── подтверждение ─────
    if act == "pax_ok":
        total = data["adults"] + data["children"] + data["infants"]
        if total > 9 or data["infants"] > data["adults"]:
            await callback.answer(
                "Максимум 9 пассажиров и 👶 ≤ 👤" if lang == "ru"
                else "Maks 9 yo'lovchi va 👶 ≤ 👤",
                show_alert=True,
            )
            return
        await state.set_state(Search.confirm)
        await send_review(callback.message, state)
        return await callback.answer()

    # ───── инкременты / декременты ─────
    key   = {"a": "adults", "c": "children", "i": "infants"}[act[0]]
    delta = 1 if "+" in act else -1
    new   = max(0 if key != "adults" else 1, data[key] + delta)

    # прогноз после изменения
    totals = data.copy()
    totals[key] = new
    total_after = totals["adults"] + totals["children"] + totals["infants"]

    if total_after > 9:
        return await callback.answer(
            "Максимум 9 пассажиров" if lang == "ru" else "Maks 9 yo'lovchi",
            show_alert=True,
        )
    if totals["infants"] > totals["adults"]:
        return await callback.answer("👶 ≤ 👤", show_alert=True)

    # всё ок – сохраняем и перерисовываем клаву
    await state.update_data(**{key: new})
    await callback.message.edit_reply_markup(
        reply_markup=build_pax_kb(
            totals["adults"], totals["children"], totals["infants"], lang
        )
    )
    await callback.answer()

# ─────────────────────────────────────────────
#           Confirm / Review (обновлённый)
# ─────────────────────────────────────────────
MONTHS_RU_GEN = [
    "января", "февраля", "марта", "апреля",
    "мая", "июня", "июля", "августа",
    "сентября", "октября", "ноября", "декабря",
]
MONTHS_UZ = [
    "yanvar", "fevral", "mart", "aprel",
    "may", "iyun", "iyul", "avgust",
    "sentyabr", "oktyabr", "noyabr", "dekabr",
]


def _fmt_date(d_str: str, lang: str) -> str:
    """'2025-10-24' → '24 октября' | '24-oktyabr'"""
    dt = datetime.strptime(d_str, "%Y-%m-%d")
    if lang == "ru":
        return f"{dt.day} {MONTHS_RU_GEN[dt.month - 1]}"
    return f"{dt.day}-{MONTHS_UZ[dt.month - 1]}"

def _city_label(iata: str, lang: str) -> str:
    """
    «Город (IATA)» — без удвоения кода,
    если city_by_iata уже вернул его в скобках.
    """
    raw = city_by_iata(iata, lang)
    return raw if f"({iata})" in raw.upper() else f"{raw} ({iata})"


async def send_review(msg: Message, state: FSMContext):
    data = await state.get_data()
    lang = data["lang"]

    # 🔻 маршрут
    orig_lbl = _city_label(data["origin"], lang)
    dest_lbl = _city_label(data["destination"], lang)
    route_line = (
        f"{orig_lbl} → {dest_lbl} → {orig_lbl}"
        if data.get("return_date")
        else f"{orig_lbl} → {dest_lbl}"
    )

    # 🔻 даты
    dep_human = _fmt_date(data["departure_date"], lang)
    date_line = (
        f"{dep_human} — {_fmt_date(data['return_date'], lang)}"
        if data.get("return_date")
        else dep_human
    )

    # 🔻 пассажиры
    pax_ru = (
        f"• взрослые: {data['adults']}\n"
        f"• дети: {data['children']}\n"
        f"• младенцы: {data['infants']}"
    )
    pax_uz = (
        f"• kattalar: {data['adults']}\n"
        f"• bola: {data['children']}\n"
        f"• go‘dak: {data['infants']}"
    )

    # ───────── текст + подписи кнопок ─────────
    if lang == "ru":
        text = (
            "🔍 <b>Проверьте данные перед переходом</b>\n"
            "и убедитесь, что они верны на сайте.\n"
            f"📍 <b>Ваш маршрут:</b> {route_line}\n"
            f"📅 <b>Даты:</b> {date_line}\n"
            f"🧑‍💼 <b>Пассажиры:</b>\n{pax_ru}\n\n"
            "Всё верно?"
        )
        btn_confirm, btn_restart = "✅ Подтвердить", "🔄 Начать заново"
    else:
        text = (
            "🔍 <b>Saytga o‘tishdan oldin ma’lumotlarni tekshiring</b>\n"
            "va ularning to‘g‘riligiga ishonch hosil qiling.\n"
            f"📍 <b>Yo‘nalish:</b> {route_line}\n"
            f"📅 <b>Sana(lar):</b> {date_line}\n"
            f"🧑‍💼 <b>Yo‘lovchilar:</b>\n{pax_uz}\n\n"
            "Hammasi to‘g‘rimi?"
        )
        btn_confirm, btn_restart = "✅ Tasdiqlash", "🔄 Qaytadan"

    # ───────── клавиатура (две кнопки в ряду) ─────────
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=btn_confirm, callback_data="confirm"),
                InlineKeyboardButton(text=btn_restart, callback_data="restart"),
            ]
        ]
    )

    # ───────── отправляем сообщение ─────────
    await msg.answer(text, reply_markup=kb, parse_mode="HTML")

# ─────────────────────────────────────────────
#               Confirm (кнопка ✅)
# ─────────────────────────────────────────────
@router.callback_query(lambda c: c.data == "confirm", Search.confirm)
async def confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data["lang"]

    url = build_aviasales_url(
        data["origin"],
        data["destination"],
        data["departure_date"],
        data.get("return_date", ""),
        data["adults"],
        data["children"],
        data["infants"],
        lang,
    )

    if lang == "ru":
        help_block = (
            "\n\nℹ️  <a href=\"https://www.aviasales.ru/faq/kak-rabotaet-sajt\">"
            "Как работает поиск и бронирование</a>"
        )
        lead = "🔗 Ваша ссылка:"
    else:
        help_block = (
            "\n\nℹ️  <a href=\"https://www.aviasales.uz/uz/faq/how-aviasales-works\">"
            "Qidiruv va bronlash yo‘riqnomasi</a>\n"
            "🎥  <a href=\"https://www.youtube.com/watch?v=y_kvHPgyhK0\">Video-ko‘rsatma</a>"
        )
        lead = "🔗 Sizning havola:"

    await callback.message.answer(
        f"{lead}\n{url}{help_block}",
        parse_mode="HTML",
        disable_web_page_preview=False,
    )

    save_flow_log(callback.from_user.id, "link_sent", {"url": url})
    await state.clear()
    await callback.answer()


# ─────────────────────────────────────────────
#            «Начать заново» хэндлер
# ─────────────────────────────────────────────
@router.callback_query(lambda c: c.data == "restart")
async def restart(callback: CallbackQuery, state: FSMContext):
    """Полностью сбрасываем шаги и запускаем сценарий заново."""
    await state.clear()
    await cmd_start(callback.message, state)
    await callback.answer()

