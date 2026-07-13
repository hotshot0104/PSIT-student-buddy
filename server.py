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

        # Re-fetch and update the cache file immediately with the new credentials
        session, err = erp.get_session()
        if not err:
            erp.fetch_and_cache_all(session)

        print(f"📝 Credentials updated and cache refreshed via Web Settings: User={erp_user}")
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
    """Fetch data from local cache, or scrape once if cache is missing or stale."""
    cache = erp.load_cache()
    is_today = False
    if cache and cache.get("student", {}).get("roll") == erp.ERP_USER:
        last_updated_str = cache.get("last_updated")
        if last_updated_str:
            try:
                from datetime import datetime
                last_updated = datetime.fromisoformat(last_updated_str).astimezone(erp.IST)
                if last_updated.date() == datetime.now(tz=erp.IST).date():
                    is_today = True
            except Exception:
                pass
        if is_today:
            print("💾 Serving dashboard data from local cache.")
            return jsonify(cache)

    print("🔄 Cache missing or outdated/stale. Scraping from ERP...")
    session, err = erp.get_session()
    if err:
        if cache and cache.get("student", {}).get("roll") == erp.ERP_USER:
            print("⚠️ Scraping failed, serving stale cache as fallback.")
            return jsonify(cache)
        return jsonify({"error": err}), 500

    data = erp.fetch_and_cache_all(session)
    if data is None:
        if cache and cache.get("student", {}).get("roll") == erp.ERP_USER:
            print("⚠️ Scraping failed, serving stale cache as fallback.")
            return jsonify(cache)
        return jsonify({"error": "Failed to scrape data."}), 500

    return jsonify(data)

if __name__ == '__main__':
    port = 5000
    print(f"🚀 Dashboard Server starting on http://localhost:{port}")
    app.run(host='127.0.0.1', port=port, debug=True)
