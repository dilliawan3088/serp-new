import re
import time
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def normalize_url(raw: str) -> str:
    raw = raw.strip()
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    raw = raw.split("#", 1)[0]
    return raw

def wait_for_page_ready(driver, timeout=20):
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") in ("complete", "interactive")
    )
    WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((By.TAG_NAME, "body"))
    )

def auto_scroll(driver, pause=0.8, max_scrolls=20):
    last_height = driver.execute_script("return document.body.scrollHeight || 0")
    for _ in range(max_scrolls):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause)
        new_height = driver.execute_script("return document.body.scrollHeight || 0")
        if new_height <= last_height:
            break
        last_height = new_height

def get_visible_text(driver) -> str:
    body = driver.find_element(By.TAG_NAME, "body")
    text = body.text or ""
    text = re.sub(r"\r?\n\s*\n+", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()

def scrape_landing_page(url: str):
    url = normalize_url(url)
    chrome_opts = Options()
    chrome_opts.add_argument("--headless=new")
    chrome_opts.add_argument("--no-sandbox")
    chrome_opts.add_argument("--disable-gpu")
    chrome_opts.add_argument("--window-size=1920,1080")
    chrome_opts.add_argument("user-agent=Mozilla/5.0 (Landing-Page-Scraper)")

    driver = webdriver.Chrome(options=chrome_opts)
    try:
        driver.get(url)
        wait_for_page_ready(driver, timeout=25)

        for sel in [
            "button[aria-label='Accept all']",
            "button[aria-label='Accept All']",
            "button#onetrust-accept-btn-handler",
            "[data-testid='uc-accept-all-button']",
        ]:
            try:
                elems = driver.find_elements(By.CSS_SELECTOR, sel)
                if elems:
                    elems[0].click()
                    time.sleep(0.5)
            except:
                pass

        auto_scroll(driver, pause=0.8, max_scrolls=25)
        text = get_visible_text(driver)
        return {url: text}
    finally:
        driver.quit()