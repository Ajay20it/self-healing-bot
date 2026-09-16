# Self-Healing Automation Bot

A Selenium-based automation script that demonstrates "self-healing" behavior —
when a primary element selector breaks (e.g. due to a changed HTML id),
the bot automatically falls back to a more resilient selector strategy
instead of crashing.

## How it works
1. Attempts to click a button using a hardcoded, fragile selector (id='btn-1234')
2. If that fails, falls back to a flexible CSS selector matching any id starting with btn-
3. If that also fails, falls back further to matching the button by its visible text
4. All steps are logged with timestamps to automation_log.txt
5. If all selector strategies fail, captures and saves a browser screenshot to failure_screenshot.png

## How to run
1. Install dependencies: pip install selenium
2. Run: python selfheal.py
3. Check automation_log.txt for the execution log
4. If a test fails completely, inspect failure_screenshot.png for visual debugging

## Demo scenario
- Open test.html, change the button's id value, save
- Re-run the script - it will show the primary selector failing
  and the fallback selector succeeding, proving self-healing behavior
