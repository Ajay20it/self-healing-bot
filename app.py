from flask import Flask, render_template, jsonify, request, Response
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException
from apscheduler.schedulers.background import BackgroundScheduler
import csv
import os
import time
import re
import sqlite3
import io
from datetime import datetime

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "history.db")
ALERT_LOG = os.path.join(BASE_DIR, "alerts.log")
CSV_PATH = os.path.join(BASE_DIR, "test_dataset.csv")

BY_MAP = {"id": By.ID, "css": By.CSS_SELECTOR, "xpath": By.XPATH}

# ---------- Database setup ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_name TEXT,
            status TEXT,
            reason TEXT,
            suggestion TEXT,
            auto_fix TEXT,
            screenshot TEXT,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_run(results):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    ts = datetime.now().isoformat()
    for r in results:
        c.execute(
            "INSERT INTO runs (test_name, status, reason, suggestion, auto_fix, screenshot, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (r["test"], r["status"], r["reason"], r["suggestion"], r.get("auto_fix"), r.get("screenshot"), ts)
        )
    conn.commit()
    conn.close()

def get_history():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT test_name,
               SUM(CASE WHEN status='PASS' THEN 1 ELSE 0 END) as passes,
               SUM(CASE WHEN status='SELF-HEALED' THEN 1 ELSE 0 END) as healed,
               SUM(CASE WHEN status='FAIL' THEN 1 ELSE 0 END) as fails,
               COUNT(*) as total,
               MAX(timestamp) as last_run
        FROM runs
        GROUP BY test_name
    """)
    rows = c.fetchall()
    conn.close()
    history = []
    for row in rows:
        history.append({
            "test": row[0], "passes": row[1], "healed": row[2],
            "fails": row[3], "total": row[4], "last_run": row[5]
        })
    return history

def log_alert(message):
    with open(ALERT_LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} - ALERT - {message}\n")

# ---------- Selector fix suggestion ----------
def guess_element_type(fallback_value):
    match = re.match(r"^(\w+)\[", fallback_value)
    return match.group(1) if match else None

def suggest_fix(driver, primary_value, fallback_value):
    tag = guess_element_type(fallback_value)
    if not tag:
        return None
    try:
        elements = driver.find_elements(By.TAG_NAME, tag)
    except Exception:
        return None
    candidates = [el.get_attribute("id") for el in elements if el.get_attribute("id")]
    if not candidates:
        return None
    old_prefix = re.split(r'[-_0-9]', primary_value)[0].lower()
    for cand in candidates:
        cand_prefix = re.split(r'[-_0-9]', cand)[0].lower()
        if cand_prefix == old_prefix:
            return cand
    return candidates[0]

# ---------- Core test runner ----------
def run_all_tests():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=options)

    html_path = "file://" + os.path.join(BASE_DIR, "test.html")
    driver.get(html_path)

    results = []
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row["test_name"]
            primary_by, primary_value = row["primary_by"], row["primary_value"]
            fallback_by, fallback_value = row["fallback_by"], row["fallback_value"]

            entry = {"test": name, "status": "", "reason": "", "suggestion": "",
                      "screenshot": None, "auto_fix": None}

            try:
                driver.find_element(BY_MAP[primary_by], primary_value)
                entry["status"] = "PASS"
                entry["reason"] = f"Primary selector ({primary_by}='{primary_value}') found the element."
                entry["suggestion"] = "No action needed."
            except NoSuchElementException:
                try:
                    driver.find_element(BY_MAP[fallback_by], fallback_value)
                    entry["status"] = "SELF-HEALED"
                    entry["reason"] = (
                        f"Primary selector ({primary_by}='{primary_value}') failed. "
                        f"Fallback selector ({fallback_by}='{fallback_value}') recovered it."
                    )
                    fix = suggest_fix(driver, primary_value, fallback_value)
                    entry["auto_fix"] = fix
                    entry["suggestion"] = (
                        f"Detected likely new id='{fix}'. Click Apply Fix to update test_dataset.csv."
                        if fix else "Update test_dataset.csv primary selector manually."
                    )
                    log_alert(f"{name} SELF-HEALED (primary selector broke, fallback recovered)")
                except NoSuchElementException:
                    entry["status"] = "FAIL"
                    entry["reason"] = (
                        f"Both primary ({primary_by}='{primary_value}') and fallback "
                        f"({fallback_by}='{fallback_value}') selectors failed."
                    )
                    fix = suggest_fix(driver, primary_value, fallback_value)
                    entry["auto_fix"] = fix
                    entry["suggestion"] = (
                        f"Auto-detected possible match id='{fix}'. Click Apply Fix to update test_dataset.csv."
                        if fix else "No similar element found. Manual inspection needed."
                    )
                    screenshot_dir = os.path.join(BASE_DIR, "static", "screenshots")
                    os.makedirs(screenshot_dir, exist_ok=True)
                    filename = f"{name.replace(' ', '_')}_{int(time.time())}.png"
                    driver.save_screenshot(os.path.join(screenshot_dir, filename))
                    entry["screenshot"] = f"screenshots/{filename}"
                    log_alert(f"{name} FAILED - both selectors broken")

            results.append(entry)

    driver.quit()
    save_run(results)
    return results

# ---------- Apply Fix ----------
def apply_fix_to_csv(test_name, new_value):
    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if row["test_name"] == test_name:
                row["primary_value"] = new_value
            rows.append(row)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

# ---------- Routes ----------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/run-tests")
def run_tests():
    return jsonify(run_all_tests())

@app.route("/apply-fix", methods=["POST"])
def apply_fix():
    data = request.get_json()
    apply_fix_to_csv(data["test_name"], data["new_value"])
    return jsonify({"status": "updated", "test": data["test_name"], "new_value": data["new_value"]})

@app.route("/history")
def history():
    return jsonify(get_history())

@app.route("/export")
def export():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT test_name, status, reason, suggestion, auto_fix, timestamp FROM runs ORDER BY id DESC LIMIT 100")
    rows = c.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Test", "Status", "Reason", "Suggestion", "Auto Fix", "Timestamp"])
    writer.writerows(rows)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=test_report.csv"}
    )

# ---------- Scheduler ----------
scheduler = BackgroundScheduler()
scheduler.add_job(func=run_all_tests, trigger="interval", minutes=30, id="auto_run_job")
scheduler.start()

if __name__ == "__main__":
    init_db()
    app.run(debug=True, use_reloader=False)
