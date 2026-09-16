from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
import csv
import logging
import os
import time

logging.basicConfig(filename='automation_log.txt', level=logging.INFO,
                     format='%(asctime)s - %(levelname)s - %(message)s')

BY_MAP = {
    "id": By.ID,
    "css": By.CSS_SELECTOR,
    "xpath": By.XPATH
}

def run_test(driver, test_name, primary_by, primary_value, fallback_by, fallback_value, description):
    logging.info(f"---- Starting test: {test_name} ({description}) ----")
    try:
        element = driver.find_element(BY_MAP[primary_by], primary_value)
        logging.info(f"[{test_name}] PASS - Primary selector worked ({primary_by}='{primary_value}')")
        return "PASS"
    except NoSuchElementException:
        logging.warning(f"[{test_name}] Primary selector failed ({primary_by}='{primary_value}'). Trying fallback...")
        try:
            element = driver.find_element(BY_MAP[fallback_by], fallback_value)
            logging.info(f"[{test_name}] SELF-HEALED - Fallback selector worked ({fallback_by}='{fallback_value}')")
            return "SELF-HEALED"
        except NoSuchElementException:
            logging.error(f"[{test_name}] FAIL - Both primary and fallback selectors failed")
            logging.error(f"[{test_name}] Self-healing process failed")
            screenshot_path = "failure_screenshot.png"
            try:
                driver.save_screenshot(screenshot_path)
                logging.info(f"[{test_name}] Failure screenshot captured: {screenshot_path}")
            except Exception as e:
                logging.error(f"[{test_name}] Failed to capture screenshot: {e}")
            return "FAIL"

def main():
    driver = webdriver.Chrome()
    test_path = "file:///C:/Users/Ajaykumar/OneDrive/Desktop/SelfHealingBot/test.html"
    if not os.path.exists("C:/Users/Ajaykumar/OneDrive/Desktop/SelfHealingBot/test.html"):
        test_path = "file:///" + os.path.abspath("test.html").replace("\\", "/")
    driver.get(test_path)
    time.sleep(2)

    results = []

    with open("test_dataset.csv", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            result = run_test(
                driver,
                row["test_name"],
                row["primary_by"],
                row["primary_value"],
                row["fallback_by"],
                row["fallback_value"],
                row["description"]
            )
            results.append((row["test_name"], result))

    print("\n---- TEST SUMMARY ----")
    for name, result in results:
        print(f"{name}: {result}")

    passed = sum(1 for _, r in results if r in ("PASS", "SELF-HEALED"))
    print(f"\n{passed}/{len(results)} tests passed (including self-healed)")

    time.sleep(2)
    driver.quit()

if __name__ == "__main__":
    main()