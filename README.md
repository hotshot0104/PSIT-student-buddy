# 🤖 PSIT ERP Discord Bot

A powerful Discord bot designed to automate your PSIT ERP life. Get your timetable, check your attendance, and calculate your "bunk budget" directly from Discord.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Discord.js](https://img.shields.io/badge/Discord.py-2.0+-5865F2?style=for-the-badge&logo=discord&logoColor=white)

---

## ✨ Features

- 🌅 **Morning Briefing:** Automatically sends your daily timetable and current attendance every morning at 7:00 AM IST.
- 🔔 **Smart Reminders:** Pings you exactly 15 minutes before each class starts so you're never late.
- 📊 **Attendance Tracking:** Real-time overall attendance fetching from the ERP.
- 📉 **Bunk Budget:** Calculates exactly how many classes you can skip while staying above 75%, or how many you need to attend to recover.
- ⚡ **Session Caching:** Optimized login logic to avoid repeated authentication and potential ERP lockouts.

---

## 🛠️ Commands

Everything you need is just a slash-less command away:

| Command | Description |
| :--- | :--- |
| `!today` | Displays today's schedule. |
| `!tomorrow` | Sneak peek into tomorrow's classes. |
| `!attendance` | Shows your overall attendance percentage. |
| `!bunk` | Your current "skip allowance" or "recovery path". |
| `!help` | Shows the command list. |

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10 or higher.
- A Discord Bot Token (Get it from the [Discord Developer Portal](https://discord.com/developers/applications)).
- Your PSIT ERP Credentials.

### 2. Local Setup
1. Clone the repository:
   ```bash
   git clone https://github.com/Sameer010405/psitbot.git
   cd psitbot
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the root directory and add your credentials:
   ```env
   ERP_USER="your_roll_number"
   ERP_PASSWORD="your_erp_password"
   DISCORD_TOKEN="your_bot_token"
   DISCORD_USER_ID="your_discord_id"
   ```
4. Run the bot:
   ```bash
   python bot2.0.py
   ```

---

## 📱 Run on Mobile (Termux)

Check the [SETUP.md](./SETUP.md) for a detailed guide on how to keep the bot running 24/7 on your Android device using Termux.

---

## ⚠️ Disclaimer

This bot is an unofficial tool and is not affiliated with PSIT in any way. It is intended for educational purposes and personal use. Use it responsibly and do not share your credentials with anyone.

---

<p align="center">Made with ❤️ for PSITians</p>
