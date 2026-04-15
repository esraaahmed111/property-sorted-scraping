# Import libraries
import time
import re
import os
import json
import random
import sys
import requests
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Configuration & Utilities
BASE = "https://www.propertysorted.com"
OUTPUT = "propertysorted.csv"
URLS_CACHE = "propertysorted_urls.json"
PROGRESS_FILE = "propertysorted_progress.json"

# Column Names
COL_ORDER = [
    "Link", 
    "Bedrooms", 
    "Bathrooms", 
    "Area_m2", 
    "Price_per_meter", 
    "Address", 
    "City", 
    "Location_1", 
    "Location_2", 
    "Unit", 
    "Type", 
    "Rent_Sale"
]

CITY_MAP = {
    "new cairo": "Cairo", "madinaty": "Cairo", "al rehab": "Cairo",
    "sheikh zayed": "Giza", "6th october": "Giza", "october": "Giza",
    "north coast": "Alexandria", "new alamein": "Alexandria",
    "ras al hekma": "Matrouh", "el gouna": "Red Sea", "ain sokhna": "Suez"
}

def get_city(l1, l2=""):
    combined = f"{l1} {l2}".lower()
    for key, city in CITY_MAP.items():
        if key in combined: return city
    return "Egypt"

def atomic_save(current_data):
    if not current_data: return
    tmp = OUTPUT + ".tmp"
    pd.DataFrame(current_data, columns=COL_ORDER).to_csv(tmp, index=False, encoding="utf-8-sig")
    os.replace(tmp, OUTPUT)

def human_delay(min_s=1, max_s=3):
    time.sleep(random.uniform(min_s, max_s))

# Phase 1: Discovery (Selenium)
all_urls = json.load(open(URLS_CACHE)) if os.path.exists(URLS_CACHE) else {}
done_paths = set(json.load(open(PROGRESS_FILE))) if os.path.exists(PROGRESS_FILE) else set()

print("STARTING PHASE 1: Browser Discovery")
options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option('useAutomationExtension', False)
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
wait = WebDriverWait(driver, 15)

try:
    for mode in ["buy", "rent"]:
        driver.get(f"{BASE}/{mode}")
        human_delay(3, 5)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        location_paths = [a['href'] for a in soup.find_all("a", href=True) if re.match(rf'^/{mode}/[a-z0-9-]+$', a['href'])]
        
        for path in location_paths:
            if path in done_paths: continue
            print(f"Scanning location: {path}")
            driver.get(BASE + path)
            human_delay(4, 6)
            
            page_soup = BeautifulSoup(driver.page_source, "html.parser")
            nums = [int(t.get_text()) for t in page_soup.find_all(["button", "a"]) if t.get_text().isdigit()]
            total_pages = max(nums) if nums else 1
            
            for pg in range(1, total_pages + 1):
                if pg > 1:
                    try:
                        btn = wait.until(EC.element_to_be_clickable((By.XPATH, f"//*[text()='{pg}']")))
                        driver.execute_script("arguments[0].click();", btn)
                        human_delay(2, 4)
                    except: break
                
                current_soup = BeautifulSoup(driver.page_source, "html.parser")
                for a in current_soup.select("a[href*='/listing/']"):
                    link = (BASE + a['href']).split('?')[0]
                    if link not in all_urls:
                        all_urls[link] = "Sale" if "buy" in mode else "Rent"

            done_paths.add(path)
            with open(URLS_CACHE, "w") as f: json.dump(all_urls, f)
            with open(PROGRESS_FILE, "w") as f: json.dump(list(done_paths), f)
finally:
    driver.quit()
    print(f"Phase 1 Complete. Unique URLs found: {len(all_urls)}")

# Phase 2: Data Extraction (Requests)
data = pd.read_csv(OUTPUT).to_dict("records") if os.path.exists(OUTPUT) else []
already_done = {row['Link'] for row in data}

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"})

print(f"Phase 2: Processing {len(already_done)} existing / {len(all_urls)} total")

try:
    for url, ltype in all_urls.items():
        if url in already_done: continue
        try:
            res = session.get(url, timeout=15)
            if res.status_code != 200: continue
            
            soup = BeautifulSoup(res.text, "html.parser")
            text = (soup.find("main") or soup).get_text(" ", strip=True)

            # Extraction
            beds = re.search(r'(\d+)\s*(?:Bed|BR)', text, re.I)
            baths = re.search(r'(\d+)\s*(?:Bath|Toilet)', text, re.I)
            area_m = re.search(r'(\d[\d,]*)\s*(?:sqm|sq\.m|m²)', text, re.I)
            
            crumbs = [a.text.strip() for a in soup.select("ol li a") if a.text.strip() not in ["Home", "Buy", "Rent"]]
            l1, l2 = (crumbs[0], crumbs[1]) if len(crumbs) > 1 else (crumbs[0] if len(crumbs)>0 else "N/A", "N/A")

            ppm = "N/A"
            price_match = re.search(r'EGP\s*([\d,]+)', text)
            if price_match and area_m:
                total_price = float(price_match.group(1).replace(",", ""))
                sqm_val = float(area_m.group(1).replace(",", ""))
                if sqm_val > 0: ppm = round(total_price / sqm_val, 2)

            data.append({
                "Link": url, 
                "Bedrooms": beds.group(1) if beds else "N/A", 
                "Bathrooms": baths.group(1) if baths else "N/A",
                "Area_m2": area_m.group(1).replace(",", "") if area_m else "N/A", 
                "Price_per_meter": ppm,
                "Address": f"{l2}, {l1}, Egypt" if l2 != "N/A" else f"{l1}, Egypt", 
                "City": get_city(l1, l2),
                "Location_1": l1, 
                "Location_2": l2, 
                "Unit": "Apartment", 
                "Type": "Residential", 
                "Rent_Sale": ltype
            })

            atomic_save(data)
            if len(data) % 10 == 0: 
                print(f"Current Progress: {len(data)} properties saved to {OUTPUT}")
            
            human_delay(0.8, 2.0)
            
        except Exception as e:
            print(f"Error processing {url}: {e}")

except KeyboardInterrupt:
    print("\nManual stop detected. Progress saved safely.")

print(f"Finished. Final output file: {OUTPUT}")
