import json
import logging
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_PATH = BASE_DIR / 'data' / 'user_logs.json'

# Гарантируем существование директории и файла
LOGS_PATH.parent.mkdir(parents=True, exist_ok=True)
if not LOGS_PATH.exists():
    with LOGS_PATH.open('w', encoding='utf-8') as f:
        json.dump([], f)

def log_action(user_id: int, step: str, user_input: str = "", bot_reply: str = "", metadata: dict = None):
    try:
        timestamp = datetime.now().isoformat()
        entry = {
            "timestamp": timestamp,
            "user_id": user_id,
            "step": step,
            "user_input": user_input,
            "bot_reply": bot_reply,
            "metadata": metadata or {}
        }

        with LOGS_PATH.open(encoding='utf-8') as f:
            logs = json.load(f)

        logs.append(entry)

        with LOGS_PATH.open('w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)

        logging.info(f"[LOG] Записано действие: {entry}")

    except Exception as e:
        logging.error(f"[LOG] Ошибка записи лога: {e}")
