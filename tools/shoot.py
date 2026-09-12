"""Photograph the live site and report what it is actually serving.

Written for a GitHub runner: the development sandbox cannot reach the open
web, so anything to be seen has to be fetched somewhere that can and carried
back into the repository.
"""
import json, os, sys
from playwright.sync_api import sync_playwright

URL = (sys.argv[1] if len(sys.argv) > 1 else "https://heritle.org/").rstrip("/") + "/"
OUT = sys.argv[2] if len(sys.argv) > 2 else "screens"
os.makedirs(OUT, exist_ok=True)

SHOTS = [
    ("phone", {"width": 390, "height": 844}, True),
    ("desktop", {"width": 1280, "height": 900}, False),
]

report = {"url": URL, "shots": [], "problems": []}

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    for name, vp, mobile in SHOTS:
        ctx = browser.new_context(viewport=vp, has_touch=mobile, is_mobile=mobile,
                                  device_scale_factor=2, locale="en-GB")
        page = ctx.new_page()
        errors, bad = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("response", lambda r: bad.append(f"{r.status} {r.url}")
                if r.status >= 400 else None)
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_function("typeof POOL !== 'undefined' && POOL.length > 0",
                               timeout=60000)
        # The first thing a new player sees is the field notes over the board.
        page.wait_for_timeout(1500)
        page.screenshot(path=f"{OUT}/{name}-first.png", full_page=False)
        page.evaluate("document.getElementById('fnClose')?.click()")
        page.wait_for_timeout(1200)
        page.screenshot(path=f"{OUT}/{name}-board.png", full_page=False)
        page.screenshot(path=f"{OUT}/{name}-full.png", full_page=True)
        # And the state a player is in halfway through a round.
        page.evaluate("""
          () => {
            const tg = targets[0];
            const near = COUNTRIES.filter(c => c.names.en !== tg.country.en)
              .sort((a, b) => haversineKm(a.lat, a.lng, tg.lat, tg.lng)
                            - haversineKm(b.lat, b.lng, tg.lat, tg.lng))[0];
            submitGuess(near);
          }
        """)
        page.wait_for_timeout(900)
        page.screenshot(path=f"{OUT}/{name}-guessed.png", full_page=False)
        facts = page.evaluate("""
          () => ({
            pool: POOL.length, day: dayIndex, lang,
            title: document.title,
            pitch: (document.getElementById('pitch') || {}).textContent,
            photo: (document.getElementById('siteImg') || {}).currentSrc || '',
            mark: !!document.querySelector('.mark img'),
            timing: (() => {
              const n = performance.getEntriesByType('navigation')[0] || {};
              return { loaded: Math.round(n.loadEventEnd || 0),
                       transferred: performance.getEntriesByType('resource')
                         .reduce((a, r) => a + (r.transferSize || 0), 0) };
            })()
          })
        """)
        report["shots"].append({"name": name, "facts": facts,
                                "errors": errors, "bad": sorted(set(bad))[:10]})
        if errors: report["problems"].append(f"{name}: page errors {errors[:2]}")
        if bad: report["problems"].append(f"{name}: failed requests {sorted(set(bad))[:3]}")
        ctx.close()
    browser.close()

open(f"{OUT}/report.json", "w").write(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
