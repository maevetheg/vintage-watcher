#!/usr/bin/env python3
"""
Vintage watcher: checks eBay, The RealReal, Poshmark, Mercari, Depop and
Vestiaire for new listings and pushes them to your phone via ntfy.

Run once:        python watcher.py
Run every 10 min: python watcher.py --loop 600
"""
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
import yaml

HERE = Path(__file__).parent
CONFIG = yaml.safe_load((HERE / "config.yaml").read_text())
SEEN_FILE = HERE / "seen.json"
TOPIC = os.environ.get("NTFY_TOPIC") or CONFIG.get("ntfy_topic")


# ---------- storage ----------

def load_seen():
    if SEEN_FILE.exists():
        return json.loads(SEEN_FILE.read_text())
    return {}


def save_seen(seen):
    trimmed = {k: v[-3000:] for k, v in seen.items()}  # keep the file small
    SEEN_FILE.write_text(json.dumps(trimmed, indent=1))


# ---------- notifications ----------

def notify(source, item):
    message = item["title"]
    if item.get("price"):
        message += f"\n{item['price']}"
    payload = {
        "topic": TOPIC,
        "title": f"New on {source}",
        "message": message,
        "click": item["url"],  # tapping the notification opens the listing
        "tags": ["shopping"],
    }
    if item.get("image"):
        payload["attach"] = item["image"]
    try:
        requests.post("https://ntfy.sh", json=payload, timeout=15)
    except Exception as e:
        print(f"  notify failed: {e}")


# ---------- eBay (official API) ----------

def ebay_token():
    cid = os.environ.get("EBAY_CLIENT_ID")
    secret = os.environ.get("EBAY_CLIENT_SECRET")
    if not cid or not secret:
        return None
    r = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        auth=(cid, secret),
        data={"grant_type": "client_credentials",
              "scope": "https://api.ebay.com/oauth/api_scope"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def title_matches_size(title, size_keywords):
    if not size_keywords:
        return True
    t = title.lower()
    return any(k.lower() in t for k in size_keywords)


def check_ebay():
    cfg = CONFIG.get("ebay", {})
    if not cfg.get("enabled"):
        return None
    token = ebay_token()
    if not token:
        print("eBay: no EBAY_CLIENT_ID / EBAY_CLIENT_SECRET set, skipping")
        return None

    lo, hi = cfg.get("min_price", 0), cfg["max_price"]
    results = []
    for q in cfg["queries"]:
        r = requests.get(
            "https://api.ebay.com/buy/browse/v1/item_summary/search",
            headers={"Authorization": f"Bearer {token}",
                     "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"},
            params={"q": q, "sort": "newlyListed", "limit": 50,
                    "filter": f"price:[{lo}..{hi}],priceCurrency:USD"},
            timeout=20,
        )
        if r.status_code != 200:
            print(f"eBay error {r.status_code}: {r.text[:200]}")
            continue
        for it in r.json().get("itemSummaries", []):
            title = it.get("title", "")
            if not title_matches_size(title, cfg.get("size_keywords")):
                continue
            price = it.get("price", {})
            results.append({
                "id": it["itemId"],
                "title": title,
                "url": it["itemWebUrl"],
                "price": f"${price['value']}" if price.get("value") else None,
                "image": (it.get("image") or {}).get("imageUrl"),
            })
    return results


# ---------- other sites (your saved search pages) ----------

def active_sites():
    return [s for s in CONFIG.get("sites", [])
            if s.get("enabled", True) and s.get("url", "").startswith("http")]


def check_sites():
    from playwright.sync_api import sync_playwright

    out = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Safari/537.36"),
            viewport={"width": 1280, "height": 2000},
            locale="en-US",
        )
        page = ctx.new_page()
        for site in active_sites():
            name = site["name"]
            pattern = re.compile(site["pattern"])
            try:
                page.goto(site["url"], wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(6000)          # let listings load
                page.mouse.wheel(0, 3000)            # trigger lazy loading
                page.wait_for_timeout(2000)
                links = page.eval_on_selector_all(
                    "a[href]",
                    "els => els.map(e => [e.href, (e.innerText || e.getAttribute('aria-label') || '').trim()])",
                )
            except Exception as e:
                print(f"{name}: failed to load ({e})")
                continue

            items = {}
            for href, text in links:
                clean = href.split("?")[0].split("#")[0]
                if not pattern.search(clean):
                    continue
                label = " ".join(text.split())[:140]
                if clean not in items:
                    items[clean] = {"id": clean, "url": clean,
                                    "title": label or "New listing"}
                elif label and items[clean]["title"] == "New listing":
                    items[clean]["title"] = label

            if not items:
                print(f"{name}: 0 listings found (page may be blocking bots, "
                      f"or the URL/pattern needs updating)")
            out[name] = list(items.values())
        browser.close()
    return out


# ---------- main ----------

def run_once():
    seen = load_seen()
    batches = {}

    try:
        ebay = check_ebay()
        if ebay is not None:
            batches["eBay"] = ebay
    except Exception as e:
        print(f"eBay failed: {e}")

    if active_sites():
        try:
            batches.update(check_sites())
        except Exception as e:
            print(f"Browser checks failed: {e}")

    for source, items in batches.items():
        first_run = source not in seen
        known = set(seen.get(source, []))
        new_count = 0
        for item in items:
            if item["id"] in known:
                continue
            known.add(item["id"])
            seen.setdefault(source, []).append(item["id"])
            if not first_run:
                notify(source, item)
                new_count += 1
        if first_run and items:
            print(f"{source}: first run, saved {len(items)} existing listings without alerting")
        else:
            print(f"{source}: {len(items)} on page, {new_count} new")

    save_seen(seen)


if __name__ == "__main__":
    if not TOPIC or "change-me" in TOPIC:
        sys.exit("Set your ntfy topic in config.yaml or the NTFY_TOPIC env var first.")
    if len(sys.argv) == 3 and sys.argv[1] == "--loop":
        interval = int(sys.argv[2])
        while True:
            print(time.strftime("\n%Y-%m-%d %H:%M:%S"))
            run_once()
            time.sleep(interval)
    else:
        run_once()
