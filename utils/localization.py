import json
import logging
from pathlib import Path
from typing import List, Optional
from difflib import get_close_matches
import requests
from transliterate import translit

logger = logging.getLogger(__name__)

# Пути к JSON-файлам
BASE_DIR = Path(__file__).resolve().parent.parent
CITIES_PATH = BASE_DIR / 'data' / 'cities.json'
ALIASES_PATH = BASE_DIR / 'data' / 'user_aliases.json'

# Aviasales API
AVIASALES_API_KEY = '773c5f598a965aeea0b4c63f2d30d45a'
AVIASALES_API_URL = 'https://api.travelpayouts.com/data/ru/cities.json'

# Загрузка cities.json
with CITIES_PATH.open(encoding='utf-8') as f:
    _CITIES = json.load(f)

# Убедимся, что файл user_aliases.json существует и валиден
if not ALIASES_PATH.exists() or ALIASES_PATH.stat().st_size == 0:
    with ALIASES_PATH.open('w', encoding='utf-8') as f:
        json.dump({}, f)

with ALIASES_PATH.open(encoding='utf-8') as f:
    try:
        _RAW_ALIASES = json.load(f)
        _ALIASES = {k.lower(): v for k, v in _RAW_ALIASES.items()}
    except json.JSONDecodeError:
        _ALIASES = {}
        with ALIASES_PATH.open('w', encoding='utf-8') as fw:
            json.dump(_ALIASES, fw)

def save_alias(alias: str, iata: str):
    _ALIASES[alias.lower()] = iata
    with ALIASES_PATH.open('w', encoding='utf-8') as f:
        json.dump(_ALIASES, f, ensure_ascii=False, indent=2)
    logger.info(f"[IATA] Сохранено в user_aliases: {alias} → {iata}")

def get_iata(user_input: str) -> Optional[str]:
    name = user_input.strip().lower()
    logger.info(f"[IATA] Пользователь ввёл: {name}")

    if name in _ALIASES:
        logger.info(f"[IATA] Найден в alias: {_ALIASES[name]}")
        return _ALIASES[name]

    for city in _CITIES:
        if city.get("code", "").lower() == name:
            logger.info(f"[IATA] Совпадение по коду: {city['code']}")
            return city["code"]
        if city.get("name", "").lower() == name:
            logger.info(f"[IATA] Совпадение по имени: {city['code']}")
            return city["code"]
        if name in [v.lower() for v in city.get("name_translations", {}).values()]:
            logger.info(f"[IATA] Совпадение по переводу: {city['code']}")
            return city["code"]
        if name in [v.lower() for v in city.get("cases", {}).values()]:
            logger.info(f"[IATA] Совпадение по падежу: {city['code']}")
            return city["code"]

    translit_name = translit(name, 'ru')
    logger.info(f"[IATA] Пробую транслитерацию: {name} → {translit_name}")

    for city in _CITIES:
        city_names = [city.get("name", "").lower()]
        translations = city.get("name_translations", {})
        city_names += [v.lower() for v in translations.values() if isinstance(v, str)]

        if translit_name in city_names:
            code = city["code"]
            logger.info(f"[IATA] Найден по транслитерации в локальном списке: {name} → {code}")
            save_alias(name, code)
            return code

    all_names = {}
    for city in _CITIES:
        names = [city.get("name", "")]
        names += list(city.get("name_translations", {}).values())
        names += list(city.get("cases", {}).values())
        names += [city.get("code", "")]
        for n in names:
            if n:
                all_names[n.lower()] = city["code"]

    matches = get_close_matches(name, all_names.keys(), n=1, cutoff=0.8)
    if matches:
        found = all_names[matches[0]]
        logger.info(f"[IATA] Fuzzy match: {name} ≈ {matches[0]} → {found}")
        save_alias(name, found)
        return found

    logger.info(f"[IATA] Не найден локально, обращаюсь к API…")
    try:
        response = requests.get(AVIASALES_API_URL, headers={"X-Access-Token": AVIASALES_API_KEY})
        if response.status_code == 200:
            cities_api = response.json()

            for city in cities_api:
                city_names = [city.get("name", "").lower()]
                translations = city.get("name_translations", {})
                city_names += [v.lower() for v in translations.values() if isinstance(v, str)]

                if name in city_names or translit_name in city_names:
                    code = city["code"]
                    logger.info(f"[IATA] Найден через API: {name} → {code}")
                    save_alias(name, code)
                    return code

            logger.warning(f"[IATA] Не найден в API")
        else:
            logger.warning(f"[IATA] Ошибка ответа от API: {response.status_code}")
    except Exception as e:
        logger.error(f"[IATA] Ошибка API: {e}")

    logger.warning(f"[IATA] Не найден: {name}")
    return None

def city_by_iata(iata: str, lang: str = 'ru') -> Optional[str]:
    """
    Возвращает название города по IATA-коду в формате 'Город (XXX)',
    учитывая выбранный язык (ru/uz). Если не найден, возвращает просто IATA.
    """
    iata = iata.upper()
    for city in _CITIES:
        if city.get("code") == iata:
            if lang == 'uz':
                return f"{city.get('name_translations', {}).get('uz', city.get('name'))} ({iata})"
            return f"{city.get('name')} ({iata})"
    return iata
