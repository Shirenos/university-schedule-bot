# 🎓 University Schedule Bot

A Telegram bot that keeps your university class schedule at hand: today, tomorrow, the whole
week, the next class, odd/even week handling and reminders before each lecture.
Built with **aiogram 3**, **SQLite (aiosqlite)** and a small dependency-free **asyncio scheduler**.
The bot's user interface is in Russian.

[![CI](https://github.com/Shirenos/university-schedule-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/Shirenos/university-schedule-bot/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)
![aiogram](https://img.shields.io/badge/aiogram-3.x-2CA5E0?logo=telegram&logoColor=white)
![SQLite](https://img.shields.io/badge/storage-SQLite-003B57?logo=sqlite&logoColor=white)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230?logo=ruff&logoColor=white)](https://docs.astral.sh/ruff/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/Shirenos/university-schedule-bot?style=social)](https://github.com/Shirenos/university-schedule-bot)

## ✨ Features

- **Personal schedules** — every Telegram user has their own isolated timetable.
- **Quick views** — `/today`, `/tomorrow`, `/week` (current week) and `/next` (next class with a countdown).
- **Odd/even weeks** — classes can run every week, on odd weeks only or on even weeks only;
  `/week_parity` shows which kind of week it is. The semester start date is configurable.
- **Guided `/add` dialog** — an aiogram FSM walks you through weekday → time → subject → type
  (lecture / seminar / lab) → room → teacher → week parity, with inline keyboards and validation.
- **CSV import** — `/import` accepts a CSV file; bad rows are reported, good rows are imported.
  Understands `,` and `;` delimiters, UTF-8 and Windows-1251, Russian and English values.
- **Reminders** — `/remind on|off|<minutes>` sends a message N minutes (default 15) before every
  class. The asyncio scheduler is restored from SQLite on startup, so nothing is lost on restart.
- **Timezone aware** — "today", "next class" and reminders follow the configured IANA timezone.
- **Safe output** — user input is HTML-escaped; limits on field length, file size and lessons per user.
- **Production ready** — Dockerfile, docker-compose with a persistent volume, CI with ruff + pytest
  on Python 3.11 / 3.12 / 3.13.

## 💬 Commands

| Command | Description |
| --- | --- |
| `/start`, `/help` | Welcome message and command reference |
| `/today`, `/tomorrow` | Classes for today / tomorrow (respects week parity) |
| `/week` | Schedule of the current week |
| `/next` | The next class and how long until it starts |
| `/add` | Add a class step by step (`/cancel` aborts any dialog) |
| `/list` | Entire weekly timetable with class ids |
| `/delete <id>` | Delete a class by its id from `/list` |
| `/import` | Upload a CSV file with the schedule |
| `/remind on` / `off` / `<minutes>` | Enable or disable reminders, or set the lead time, e.g. `/remind 30` |
| `/week_parity` | Is the current week odd or even? |

## 📄 CSV format

```csv
weekday,start,end,subject,type,room,teacher,parity
mon,09:00,10:30,Математический анализ,lecture,А-101,Иванов И. И.,every
mon,12:40,14:10,Физика,lecture,Б-301,Петрова А. С.,odd
```

| Column | Accepted values |
| --- | --- |
| `weekday` | `1`–`7` (Mon = 1), `mon`…`sun`, `пн`…`вс`, full Russian/English names |
| `start`, `end` | `HH:MM`; `end` must be later than `start` |
| `subject` | any text (required) |
| `type` | `lecture` / `seminar` / `lab` (also `лекция` / `семинар` / `лаб`) |
| `room`, `teacher` | optional |
| `parity` | `every` / `odd` / `even` (also `нечётная` / `чётная`); empty means `every` |

A ready-to-use sample lives in [`examples/schedule.csv`](examples/schedule.csv). Imported classes
are appended to the existing schedule.

## 🚀 Quickstart

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Configure the environment:

   ```bash
   cp .env.example .env
   # edit .env: set BOT_TOKEN, TIMEZONE and SEMESTER_START
   ```

### Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -e .
python -m schedule_bot          # or: schedule-bot
```

### Run with Docker

```bash
docker compose up -d --build
docker compose logs -f
```

The SQLite database lives in the `bot-data` volume, so data survives container rebuilds.

### Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `BOT_TOKEN` | — (required) | Telegram bot token from @BotFather |
| `DATABASE_PATH` | `data/schedule.db` | SQLite file location |
| `TIMEZONE` | `Europe/Moscow` | IANA timezone for "today", "next class" and reminders |
| `SEMESTER_START` | most recent 1 September | First day of the semester, `YYYY-MM-DD` |
| `LOG_LEVEL` | `INFO` | Python logging level |

> 🔐 Never commit `.env` — it is already in `.gitignore`.

### How week parity works

Week 1 is the Monday–Sunday week that **contains** `SEMESTER_START`; it is an **odd** week.
Week 2 is even, week 3 odd, and so on. With `SEMESTER_START=2026-09-01` (a Tuesday) the week of
31 Aug – 6 Sep is odd, 7–13 Sep is even.

## 🧪 Development

```bash
pip install -r requirements-dev.txt -e .
ruff check . && ruff format --check .
pytest
```

Tests cover the parity logic, next-class search, CSV import, the database layer, reminder
computation and the scheduler (driven by a fake clock), configuration, formatting, and the
`/add` and `/import` dialogs end-to-end through a real aiogram `Dispatcher` with a fake Telegram
session. CI runs the same checks on Python 3.11, 3.12 and 3.13.

## 🗂 Project structure

```
university-schedule-bot/
├── src/schedule_bot/
│   ├── config.py            # Settings from env / .env
│   ├── db.py                # aiosqlite repository + schema
│   ├── models.py            # Lesson / ReminderSettings dataclasses
│   ├── main.py              # Wiring: bot, dispatcher, scheduler
│   ├── __main__.py          # `python -m schedule_bot`
│   ├── handlers/            # aiogram routers
│   │   ├── basic.py         #   /start /help /cancel
│   │   ├── view.py          #   /today /tomorrow /week /next /week_parity /list
│   │   ├── add.py           #   /add FSM dialog
│   │   ├── manage.py        #   /delete
│   │   ├── importer.py      #   /import
│   │   ├── remind.py        #   /remind
│   │   ├── keyboards.py     #   inline keyboards
│   │   └── texts.py         #   static Russian texts
│   └── services/            # pure, easily testable logic
│       ├── parity.py        #   odd/even week arithmetic
│       ├── schedule.py      #   lessons per day, next class
│       ├── parsing.py       #   weekday / time / type / parity parsers
│       ├── csv_import.py    #   CSV → lessons
│       ├── formatting.py    #   HTML message rendering (Russian)
│       └── reminders.py     #   next-reminder logic + asyncio scheduler
├── tests/                   # pytest + pytest-asyncio
├── examples/schedule.csv    # sample schedule for /import
├── docs/                    # extended docs (placeholder)
├── .github/workflows/       # CI: ruff + pytest on 3.11 / 3.12 / 3.13
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

### Design notes

- **Layers**: handlers only parse Telegram input and format replies; `services/` holds the logic and
  is almost entirely pure functions; `db.py` is the only module that speaks SQL.
- **Router order**: plain command handlers are registered before the FSM step handlers, so commands
  like `/today` or `/cancel` keep working in the middle of a dialog.
- **Scheduler**: one asyncio task per user sleeping until the next "class start − N minutes" moment
  in the configured timezone. Reminder settings and lessons live in SQLite; tasks are recreated at
  startup and rescheduled whenever the schedule or settings change. The clock and `sleep` are
  injectable, which makes the scheduler fully testable without real waiting.
- **Parity**: a class repeats every two weeks at most, so searching two weeks ahead always finds the
  next occurrence.

## 🗺 Roadmap

- [ ] Edit an existing class (`/edit <id>`)
- [ ] Per-user timezone and semester start
- [ ] Export the schedule back to CSV / iCalendar (`/export`)
- [ ] Exams, deadlines and one-off (non-recurring) events
- [ ] Inline "snooze" button on reminders
- [ ] Shared group schedules (one schedule, many students)
- [ ] Webhook mode
- [ ] Localisation (English UI)

## 🤝 Contributing

Issues and PRs are welcome. Please run `ruff` and `pytest` before submitting.

## 📄 License

[MIT](LICENSE) © 2026 Shiren
