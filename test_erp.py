import erp
import time
from dotenv import load_dotenv

load_dotenv()

print(f"DEBUG: ERP_USER is: '{erp.ERP_USER}'")
print(f"DEBUG: ERP_PASSWORD is: '{erp.ERP_PASSWORD[:3]}***' (length: {len(erp.ERP_PASSWORD)})")

print("Starting ERP login test...")
session, err = erp.erp_login()
if err:
    print(f"Login failed: {err}")
    exit(1)

print("Login successful! Session established.")

print("Fetching today's classes...")
t0 = time.time()
day_name, classes = erp.get_today_classes(session)
print(f"Finished in {time.time() - t0:.2f} seconds.")
print(f"Day: {day_name}")
print(f"Classes: {classes}")

print("Fetching attendance...")
t0 = time.time()
attendance = erp.get_attendance(session)
print(f"Finished in {time.time() - t0:.2f} seconds.")
print(f"Attendance: {attendance}")
