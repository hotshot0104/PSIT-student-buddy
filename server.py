"""
server.py — PSIT Student Buddy Local Web Server
Serves the dashboard static files and provides a local API endpoint to fetch live ERP data.
"""
import os
import sys
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
from dotenv import load_dotenv

import erp

# Force UTF-8 output
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

app = Flask(__name__, static_folder='dashboard')
CORS(app)  # Enable CORS for local testing

@app.route('/api/settings', methods=['POST'])
def save_settings():
    """Update settings in .env file and reload runtime config."""
    try:
        req_data = request.json
        erp_user = req_data.get("erp_user", "").strip()
        erp_pass = req_data.get("erp_pass", "").strip()
        tg_id = req_data.get("telegram_id", "").strip()
        tg_token = req_data.get("telegram_token", "").strip()

        # Read existing .env lines
        lines = []
        if os.path.exists(".env"):
            with open(".env", "r", encoding="utf-8") as f:
                lines = f.readlines()

        # Update or add credentials
        env_dict = {
            "ERP_USER": erp_user,
            "ERP_PASSWORD": erp_pass,
            "TELEGRAM_BOT_TOKEN": tg_token,
            "TELEGRAM_USER_ID": tg_id
        }

        new_lines = []
        keys_written = set()

        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, _ = stripped.split("=", 1)
                key = key.strip()
                if key in env_dict:
                    new_lines.append(f"{key}={env_dict[key]}\n")
                    keys_written.add(key)
                    continue
            new_lines.append(line)

        # Write any new keys that weren't in the .env originally
        for key, val in env_dict.items():
            if key not in keys_written:
                # Add grouping comments if needed
                if key == "ERP_USER" and not new_lines:
                    new_lines.append("# ERP Credentials\n")
                elif key == "TELEGRAM_BOT_TOKEN":
                    new_lines.append("\n# Telegram Bot Credentials\n")
                new_lines.append(f"{key}={val}\n")

        with open(".env", "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        # Re-apply to environmental variables
        for key, val in env_dict.items():
            os.environ[key] = val

        # Refresh config in module erp
        erp.ERP_USER = erp_user
        erp.ERP_PASSWORD = erp_pass
        
        # Clear ERP cache to force new login with the new credentials
        erp._cached_session = None
        erp._session_last_check = None

        print(f"📝 Credentials updated via Web Settings: User={erp_user}")
        return jsonify({"status": "success", "message": "Settings updated successfully."})
    except Exception as e:
        print(f"❌ Failed to save settings: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

@app.route('/api/data')
def get_live_data():
    """Fetch live data from the ERP."""
    print("🔄 Live dashboard request received. Fetching from ERP...")
    session, err = erp.get_session()
    if err:
        return jsonify({"error": err}), 500

    # 1. Fetch attendance
    attendance = erp.get_attendance(session)
    if isinstance(attendance, str):
        return jsonify({"error": attendance}), 500

    # 2. Fetch today's classes
    day_name, classes = erp.get_today_classes(session)
    
    # 3. Fetch weekly timetable
    week_tt = erp.get_week_timetable(session)

    # 4. Fetch daily attendance (if available)
    daily_attendance = erp.get_daily_attendance(session)

    # 5. Format weekly timetable for frontend
    formatted_week = {}
    if isinstance(week_tt, list):
        for day, cls_list in week_tt:
            if isinstance(cls_list, list):
                formatted_week[day] = [
                    {"time": c["time_label"], "subject": c["subject"]} for c in cls_list
                ]

    # Calculate overall budget
    bunk_budget = erp.calc_bunk_budget(attendance)

    student_name = erp.ERP_USER
    
    # Pack everything
    data = {
        "student": {
            "name": student_name,
            "roll": erp.ERP_USER,
            "branch": "PSIT Student"
        },
        "attendance": {
            "overall": attendance.get("percent_val", 0.0),
            "percent": attendance.get("percent", "0.0%"),
            "present": attendance.get("present", 0),
            "total": attendance.get("total", 0),
            "subjects": [
                {
                    "name": s["subject"],
                    "percent": float(s["percent"].replace("%", "")) if s["percent"] else 0.0,
                    "present": int(s["present"]) if s["present"] else 0,
                    "total": int(s["total"]) if s["total"] else 0
                }
                for s in attendance.get("subjects", [])
            ]
        },
        "timetable": formatted_week,
        "today_classes": [
            {"time": c["time_label"], "subject": c["subject"]}
            for c in classes
        ] if isinstance(classes, list) else [],
        "absentToday": [
            r["subject"] for r in daily_attendance if "absent" in r.get("status", "").lower()
        ] if daily_attendance else []
    }

    return jsonify(data)

if __name__ == '__main__':
    port = 5000
    print(f"🚀 Dashboard Server starting on http://localhost:{port}")
    app.run(host='127.0.0.1', port=port, debug=True)
