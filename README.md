# 🎓 PSIT Student Buddy

A full-featured academic assistant for PSIT students — delivered through a **Telegram bot** and a beautiful **web dashboard**.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)

---

## ✨ Features

| Feature | Description |
|---|---|
| ☀️ **Morning Briefing** | Sends your daily timetable + attendance automatically at **7:00 AM IST** |
| 🔔 **Smart Reminders** | Pings you **15 minutes** before each class starts |
| ⚠️ **Absent Warning** | Checks at **8:00 PM IST** if you were marked absent in any lecture and alerts you |
| 📊 **Attendance Tracking** | Overall + subject-wise attendance fetched live from ERP |
| 📉 **Bunk Budget** | Calculates exactly how many classes you can skip while staying above 75% |
| 🗓️ **Full Timetable** | View your entire week's schedule at a glance |
| ⚡ **Session Caching** | Smart login logic — re-authenticates only when needed |
| 🌐 **Web Dashboard** | Beautiful dark-mode UI showing attendance gauge, timeline, and weekly schedule |
| 🔄 **Relocation Detection**| Automatically detects rescheduled, swapped, or added classes and lists them in the morning briefing |
| 🔮 **Attendance Simulator**| Predicts future attendance based on 'what-if' (attended/skipped) scenarios in Telegram (via `/simulate`) and the web dashboard |


---

## 🤖 Telegram Bot Commands

The bot uses a **persistent reply keyboard** — no typing needed, just tap buttons!

| Button | What it does |
|---|---|
| 📅 Today | Today's class schedule |
| 📆 Tomorrow | Tomorrow's classes |
| 📊 Attendance | Overall + subject-wise attendance |
| 📉 Bunk Budget | Classes you can skip / need to attend |
| 🗓️ This Week | Full weekly timetable |
| ⚙️ Settings | View current bot configuration |
| ❓ Help | Command reference |
| 📜 Logs | Today's reminder activity log |

---

## 🚀 Getting Started

### Step 1 — Prerequisites
- Python 3.10 or higher
- A Telegram account
- Your PSIT ERP credentials

### Step 2 — Install dependencies
```bash
pip install -r requirements.txt
```

### Step 3 — Create a Telegram Bot
1. Open Telegram and message **[@BotFather](https://t.me/BotFather)**
2. Send `/newbot` and follow the prompts
3. Copy your **bot token**

### Step 4 — Get your Telegram User ID
1. Message **[@userinfobot](https://t.me/userinfobot)** on Telegram
2. It will reply with your numeric User ID

### Step 5 — Set up your `.env` file
Create a `.env` file in the project root:
```env
ERP_USER=your_roll_number
ERP_PASSWORD=your_erp_password
TELEGRAM_BOT_TOKEN=123456:ABCdef...
TELEGRAM_USER_ID=987654321
```

### Step 6 — Run the bot
```bash
python telegram_bot.py
```
You'll see `✅ Bot started. Listening for messages...`  
Then open Telegram, find your bot, and send `/start`.

---

## 🌐 Web Dashboard

Open `dashboard/index.html` in any browser — no server required.

The dashboard shows:
- **Radial attendance gauge** — color-coded (green / amber / red)
- **Today's class timeline** — with past / current / upcoming indicators
- **Bunk budget** — at a glance
- **Absent alert banner** — shown when the bot detects an absence
- **Weekly timetable** — grid view for all 6 days
- **Subject-wise attendance** — progress bars per subject
- **Settings** — store credentials locally

---

## 📱 Run 24/7 on Termux (Android)

See [SETUP.md](./SETUP.md) for a complete guide to keeping the bot running on your Android phone using Termux.

---

## 🗂️ Project Structure

```
students-best-buddy/
├── erp.py              ← ERP scraper core (login, timetable, attendance)
├── telegram_bot.py     ← Telegram bot with scheduled jobs
├── dashboard/
│   ├── index.html      ← Web dashboard
│   ├── style.css       ← Dark glassmorphism styles
│   └── app.js          ← Dashboard logic & data
├── requirements.txt
├── README.md
├── SETUP.md
└── .env                ← Your credentials (gitignored)
```

---

## ⚠️ Disclaimer

This is an unofficial tool, not affiliated with PSIT. Intended for personal academic use only. Never share your ERP credentials with anyone.

---

<p align="center">Made with ❤️ for PSITians</p>
