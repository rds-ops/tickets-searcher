import logging
from datetime import datetime
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove
from keyboards.default import language_keyboard
from states.search import Search
from utils.localization import get_iata

logger = logging.getLogger(__name__)
router = Router()

def build_aviasales_url(origin: str, destination: str, departure: str, return_date: str,
                        adults: int, children: int, infants: int, lang: str) -> str:
    def trim(date_str):
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return dt.strftime('%d%m')

    departure_trimmed = trim(departure)
    return_trimmed = trim(return_date) if return_date else ''

    # ❗ В path добавляем только количество взрослых
    if return_trimmed:
        path = f"{origin}{departure_trimmed}{destination}{return_trimmed}{adults}"
    else:
        path = f"{origin}{departure_trimmed}{destination}{adults}"

    return (
        f"https://aviasales.uz/search/{path}"
        f"?adults={adults}&children={children}&infants={infants}&language={lang}"
    )

@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Search.lang)
    await message.answer("Выберите язык / Tilni tanlang", reply_markup=language_keyboard)

@router.message(Search.lang)
async def choose_language(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    ru_text = language_keyboard.keyboard[0][0].text
    uz_text = language_keyboard.keyboard[0][1].text

    if text == ru_text:
        lang = 'ru'
    elif text == uz_text:
        lang = 'uz'
    else:
        await message.answer("Пожалуйста, выберите язык с клавиатуры.")
        return

    await state.update_data(lang=lang)
    await state.set_state(Search.origin)
    prompt = 'Введите город вылета:' if lang == 'ru' else 'Qayerdan uchasiz?'
    await message.answer(prompt, reply_markup=ReplyKeyboardRemove())

@router.message(Search.origin)
async def origin(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get('lang', 'ru')
    iata = get_iata(message.text)
    if not iata:
        await message.answer('Город не найден, попробуйте ещё раз:' if lang == 'ru' else 'Shahar topilmadi, qayta kiriting:')
        return
    await state.update_data(origin=iata)
    await state.set_state(Search.destination)
    prompt = 'Введите город прилёта:' if lang == 'ru' else 'Qayerga uchasiz?'
    await message.answer(prompt)

@router.message(Search.destination)
async def destination(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get('lang', 'ru')
    iata = get_iata(message.text)
    if not iata:
        await message.answer('Город не найден, попробуйте ещё раз:' if lang == 'ru' else 'Shahar topilmadi, qayta kiriting:')
        return
    await state.update_data(destination=iata)
    await state.set_state(Search.departure_date)
    prompt = 'Введите дату вылета (например, 2025-08-12):' if lang == 'ru' else 'Jo\'nab ketish sanasini kiriting (masalan, 2025-08-12):'
    await message.answer(prompt)

@router.message(Search.departure_date)
async def depart_date(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get('lang', 'ru')
    try:
        depart = datetime.strptime(message.text, '%Y-%m-%d')
    except ValueError:
        await message.answer('Неверный формат даты, введите ещё раз (например, 2025-08-12):' if lang == 'ru' else 'Sana noto\'g\'ri formatda, qayta kiriting (masalan, 2025-08-12):')
        return
    await state.update_data(departure_date=depart.strftime('%Y-%m-%d'))
    await state.set_state(Search.return_date)
    prompt = 'Введите дату возвращения ("нет" или "-", если без обратного билета):' if lang == 'ru' else 'Qaytish sanasini kiriting ("-" yoki "yo\'q", agar yo\'q bo\'lsa):'
    await message.answer(prompt)

@router.message(Search.return_date)
async def return_date(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get('lang', 'ru')
    text = message.text.strip().lower()
    if text and text not in ['-', 'нет', "yo'q", 'yoq']:
        try:
            ret = datetime.strptime(text, '%Y-%m-%d')
            await state.update_data(return_date=ret.strftime('%Y-%m-%d'))
        except ValueError:
            await message.answer('Неверный формат даты, введите ещё раз или - :' if lang == 'ru' else 'Sana noto\'g\'ri formatda, qayta kiriting yoki - :')
            return
    else:
        await state.update_data(return_date='')
    await state.set_state(Search.adults)
    await message.answer('Количество взрослых (старше 12 лет):' if lang == 'ru' else 'Kattalar soni (12 yoshdan katta):')

@router.message(Search.adults)
async def adults(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get('lang', 'ru')
    if not message.text.isdigit() or int(message.text) < 1:
        await message.answer('Введите число больше 0:' if lang == 'ru' else '0 dan katta son kiriting:')
        return
    await state.update_data(adults=int(message.text))
    await state.set_state(Search.children)
    await message.answer('Количество детей (от 2 до 11 лет):' if lang == 'ru' else 'Bolalar soni (2 yoshdan 11 yoshgacha):')

@router.message(Search.children)
async def children(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get('lang', 'ru')

    if not message.text.isdigit() or int(message.text) < 0:
        await message.answer('Введите неотрицательное число:' if lang == 'ru' else 'Musbat son kiriting:')
        return

    children_count = int(message.text)
    await state.update_data(children=children_count)
    await state.set_state(Search.infants)
    await message.answer('Количество младенцев (до 2 лет):' if lang == 'ru' else 'Chaqaloqlar soni (2 yoshgacha):')

@router.message(Search.infants)
async def infants(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get('lang', 'ru')

    if not message.text.isdigit() or int(message.text) < 0:
        await message.answer('Введите неотрицательное число:' if lang == 'ru' else 'Musbat son kiriting:')
        return

    await state.update_data(infants=int(message.text))
    data = await state.get_data()

    logger.info(f"FINAL STATE before building URL: {data}")

    if data['adults'] < 1:
        await message.answer(
            "Нужен хотя бы один взрослый пассажир." if lang == 'ru' else "Kamida bitta katta yo'lovchi kerak."
        )
        return

    # 🧠 Проверка даты возврата
    departure_date = datetime.strptime(data['departure_date'], "%Y-%m-%d")
    if data['return_date']:
        return_date = datetime.strptime(data['return_date'], "%Y-%m-%d")
        if return_date < departure_date:
            await message.answer(
                "Дата возврата не может быть раньше даты вылета. Пожалуйста, введите заново."
                if lang == 'ru' else
                "Qaytish sanasi jo'nash sanasidan oldin bo'lishi mumkin emas. Iltimos, qayta kiriting."
            )
            await state.set_state(Search.return_date)
            return

    url = build_aviasales_url(
        origin=data['origin'],
        destination=data['destination'],
        departure=data['departure_date'],
        return_date=data['return_date'],
        adults=data['adults'],
        children=data['children'],
        infants=data['infants'],
        lang=lang
    )

    await message.answer(('Вот ваша ссылка:' if lang == 'ru' else 'Sizning havolangiz:') + f"\n{url}")
    await state.clear()
