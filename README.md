# 🎟️ Tickets Searcher Telegram Bot

A Telegram bot for searching airline tickets using the Travelpayouts API. Built with `aiogram`, FSM-based architecture, multilingual support (`ru`, `uz`), alias resolution, and inline navigation — designed to feel like a real product.

---

## 🚀 Features

- 🔎 City & date search using natural input
- 🌐 Multilingual (`ru`, `uz`) support
- 🧠 FSM-based flow with inline keyboards
- ✈️ Integration with Travelpayouts API
- 🗂️ Custom aliases for user city names
- 📊 Logging of user behavior and selections
- ⚠️ Validations (passenger limit, roundtrip check)
- 📦 Pure Python, no DB — JSON-based storage

---

## 🧰 Technologies

- `Python 3.11+`
- `aiogram 3.x`
- `Travelpayouts API`
- `dotenv`
- `JSON`

---

## ⚙️ Setup

1. Clone the repository:
```bash
git clone https://github.com/your-username/tickets-searcher.git
cd tickets-searcher
```

2. Create `.env` file based on `.env.example`:
```bash
cp .env.example .env
```

3. Activate virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # or .\venv\Scripts\activate on Windows
pip install -r requirements.txt
```

4. Run the bot:
```bash
python bot.py
```

---

## 📄 .env Example

```env
TELEGRAM_TOKEN=your_telegram_bot_token
TRAVELPAYOUTS_API_KEY=your_travelpayouts_api_key
```

---

## 🧠 Notes

- You can add your own aliases in `data/user_aliases.json`
- Logs are saved to `data/user_logs.json`
- All states and flow logic are located in `handlers/user_flow.py`

---

## 📬 Author

Maintained by [rds-ops](https://github.com/rds-ops)
