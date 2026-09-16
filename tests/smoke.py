"""Full-flow smoke test: one win, one deliberate loss, one solve.

Walks the exact path a player takes and asserts the end state, at both a
375px phone width and a desktop width, with the browser console watched
throughout. Uses ?day=N so the run is deterministic instead of depending on
what today happens to be.

    python tests/smoke.py                 # synthetic dataset (offline)
    python tests/smoke.py --real          # the committed data/dataset.json
    python tests/smoke.py --url https://…/  # a deployed build

Exit code is non-zero if anything fails.
"""
import argparse
import glob
import http.server
import os
import re
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading

from playwright.sync_api import sync_playwright

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILS = []
DAYS = [412, 900, 1301]          # arbitrary but fixed, so runs are comparable


# Deals every day of two full cycles through the game's own dealer.
DEAL_PROBE = """
  () => {
    const cycles = ROUND_PLAN.map((plan) => {
      const tiers = plan.tiers || [plan.tier];
      return tiers.reduce((a, t) => a +
        POOL.filter(d => d.type === plan.type && d.tier === t).length, 0);
    });
    const span = Math.max(...cycles) * 2 + 5;
    const days = [];
    for(let d = 0; d < span; d++) days.push(dealFor(d).map(e => e.id));
    return { cycles, days, again: dealFor(7).map(e => e.id), pool: POOL.length };
  }
"""

# Minutes from now to the browser's own midnight, computed independently of
# the page's own helper so the check is not the code under test.
CLOCK_PROBE = """
  () => {
    const d = new Date();
    const mid = new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1).getTime();
    return Math.round((mid - Date.now()) / 60000);
  }
"""
# Winds the page's clock to 25 seconds before local midnight -- far enough out
# that the page finishes loading on the old day.
NEAR_MIDNIGHT = """
  (() => {
    const RealDate = Date;
    const d = new RealDate();
    const target = new RealDate(d.getFullYear(), d.getMonth(), d.getDate() + 1)
                     .getTime() - 25000;
    const skew = target - RealDate.now();
    function FakeDate(...a){
      return a.length ? new RealDate(...a) : new RealDate(RealDate.now() + skew);
    }
    FakeDate.prototype = RealDate.prototype;
    FakeDate.now = () => RealDate.now() + skew;
    FakeDate.UTC = RealDate.UTC; FakeDate.parse = RealDate.parse;
    window.Date = FakeDate;
  })();
"""

# Builds a real collection, then measures the code against what the same
# collection would weigh if it carried records rather than ids.
BACKUP_PROBE = """
  () => {
    POOL.slice(0, 400).forEach(e => catalogue(e, true));
    checkAchievements(); saveProfile();
    const code = exportProfile();
    return { code, bytes: code.length,
             entries: Object.keys(profile.collection).length,
             ach: profile.achievements.length,
             asRecords: JSON.stringify(profile.collection).length };
  }
"""
# One entry this browser has and the code does not, then a second restore.
MERGE_PROBE = """
  (code) => {
    const mine = POOL.find(e => !profile.collection[e.id]);
    const before = Object.keys(profile.collection).length;
    catalogue(mine, true);
    const withMine = Object.keys(profile.collection).length;
    importProfile(code);
    return { before, after: Object.keys(profile.collection).length,
             mineKept: !!profile.collection[mine.id], withMine };
  }
"""

# Ranks as defined, and which distinctions carry none.
AWARD_PROBE = """
  () => {
    const ranks = {};
    const unranked = [];
    ACHIEVEMENTS.forEach(a => {
      const k = a.secret ? 'secret' : a.rank;
      if(!k) unranked.push(a.id);
      else ranks[k] = (ranks[k] || 0) + 1;
    });
    return { ranks, unranked, secrets: ACHIEVEMENTS.filter(a => a.secret).length };
  }
"""

# Where each piece of the board actually lands.
ORDER_PROBE = """
  () => {
    const at = sel => {
      const e = document.querySelector('#viewGame > ' + sel);
      const b = e.getBoundingClientRect();
      return { top: Math.round(b.top + scrollY), left: Math.round(b.left),
               w: Math.round(b.width) };
    };
    return { rounds: at('.rounds-row'), meta: at('.meta-row'),
             photo: at('.photo-box'), map: at('.map-wrap'),
             guess: at('.guess-row'), clues: at('.clues') };
  }
"""

def check(cond, label, detail=""):
    print(("  PASS " if cond else "  FAIL ") + label + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(label)


def serve(root):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw): super().__init__(*a, directory=root, **kw)
        def log_message(self, *a): pass
    httpd = socketserver.TCPServer(("127.0.0.1", 0), Quiet)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


TAP_JS = """(pt) => {
  const p = project(pt.lat, pt.lng);
  const svg = document.getElementById('mapSvg');
  const r = svg.getBoundingClientRect();
  svg.dispatchEvent(new MouseEvent('click', {
    clientX: r.left + ((p.x - mapView.x) / mapView.w) * r.width,
    clientY: r.top  + ((p.y - mapView.y) / mapView.h) * r.height,
    bubbles: true }));
}"""


def tap_guess(page, country_js):
    """Guess by pointing at the map, the way a player does."""
    pt = page.evaluate(f"() => {{ const c = {country_js}; return {{lat:c.lat, lng:c.lng}}; }}")
    page.evaluate(TAP_JS, pt)
    page.wait_for_timeout(180)
    page.click("#confirmGuess")
    page.wait_for_timeout(220)


def T_BONUS_INTRO_SHOWN(page):
    """The bonus round's terms have to be visible before a guess is spent."""
    return page.evaluate("""
      () => document.getElementById('mapReadout').textContent === t().bonusIntro
    """)


def play_day(page, base, day, width, label):
    """One full day: round 1 won, round 2 lost on purpose, round 3 solved."""
    errors, bad_requests = [], []
    page.on("pageerror", lambda e: errors.append(str(e)))
    # A missing photo is expected and handled by the placeholder; a missing
    # script or data file is not. Google Fonts is excluded because this sandbox
    # blocks it at the proxy — the page falls back to system fonts here, which
    # says nothing about a real browser.
    def interesting(url, kind):
        if "fonts.googleapis.com" in url or "fonts.gstatic.com" in url:
            return False
        return kind in ("script", "stylesheet", "document", "fetch", "xhr")
    page.on("requestfailed", lambda r: bad_requests.append(r.url)
            if interesting(r.url, r.resource_type) else None)
    page.on("response", lambda r: bad_requests.append(f"{r.status} {r.url}")
            if r.status >= 400 and interesting(r.url, r.request.resource_type) else None)

    # The day is injected before the page runs, not passed in the URL: ?day=N
    # only replays a day this browser has already finished, which is the point
    # of the change being tested.
    if day is not None:
        page.add_init_script(f"window.HERITLE_TEST_DAY = {day};")
    page.goto(base)
    page.wait_for_function("typeof POOL !== 'undefined' && POOL.length > 0", timeout=15000)
    page.evaluate("document.getElementById('fnClose').click()")   # dismiss Field Notes
    page.wait_for_timeout(200)

    if day is not None:
        check(page.evaluate("dayIndex") == day, f"{label}: ?day={day} overrides the date",
              str(page.evaluate("dayIndex")))
    else:
        check(page.evaluate("dayIndex === todayIndex && !isPractice"),
              f"{label}: no ?day means today, and it counts")
    check(page.evaluate("targets.length") == 4, f"{label}: four targets chosen")
    # Information hierarchy: the accent colour has to keep meaning one thing.
    # It marks what is live or actionable -- the current round, the guess
    # button, your pin. When a language setting and a category caption also
    # wore it, it meant nothing and the eye had nowhere to go first.
    gold_boxes = page.evaluate("""
      () => {
        const top = document.querySelector('.photo-box').getBoundingClientRect().top;
        const near = (c) => { const m = String(c).match(/\\d+/g); return m &&
          Math.abs(+m[0]-201)<12 && Math.abs(+m[1]-162)<12 && Math.abs(+m[2]-75)<12; };
        const out = [];
        for(const el of document.querySelectorAll('header *, .nav *, .rounds-row *, .meta-row *')){
          const b = el.getBoundingClientRect();
          if(!b.height || b.top >= top) continue;
          const cs = getComputedStyle(el);
          const boxed = (near(cs.borderTopColor) && cs.borderTopWidth !== '0px')
                     || near(cs.backgroundColor);
          if(boxed) out.push(el.className || el.tagName);
        }
        return out;
      }
    """)
    check(len(gold_boxes) <= 2,
          f"{label}: the accent colour stays scarce above the puzzle",
          f"{len(gold_boxes)}: {gold_boxes}")
    # The language control is a preference, not a move: it must not be one.
    check(not any('lang' in str(c) for c in gold_boxes),
          f"{label}: the language control does not wear the accent colour")
    # The mark: top-left, a real tap target, and it spins when tapped.
    mark = page.locator("#mark")
    check(mark.count() == 1, f"{label}: the mark is on the page")
    mb = mark.bounding_box()
    if mb is None:
        # Hidden because nothing was uploaded; the graceful-absence check below
        # is the one that matters.
        mb = {"width": 44, "height": 44, "x": 0, "y": 0}
    check(bool(mb) and mb["width"] >= 40 and mb["height"] >= 40,
          f"{label}: the mark is big enough to tap",
          str(mb and (round(mb["width"]), round(mb["height"]))))
    # Measured against the rendered TEXT of the wordmark, not its element box:
    # the box spans the full width of the header, so comparing boxes compares
    # two rectangles that both start at x=0 and proves nothing.
    gap = page.evaluate("""
      () => {
        const m0 = document.getElementById('mark');
        if(m0.hidden) return null;
        const wm = document.querySelector('.wordmark');
        const r = document.createRange();
        r.selectNodeContents(wm);
        const text = r.getBoundingClientRect();
        const m = document.getElementById('mark').getBoundingClientRect();
        return { markRight: m.right, textLeft: text.left, markLeft: m.left,
                 markTop: m.top };
      }
    """)
    if gap:
        check(gap["markRight"] <= gap["textLeft"] + 1,
              f"{label}: the mark sits clear to the left of the wordmark",
              f"mark ends {round(gap['markRight'])}, text starts {round(gap['textLeft'])}")
        check(gap["markLeft"] >= 0 and gap["markTop"] >= 0,
              f"{label}: and is fully on screen", str(gap))
    # The brand file is uploaded separately, so the page has to behave whether
    # it is there or not. What must never happen is a broken-image icon: the
    # button hides itself and the header falls back to the wordmark alone.
    state = page.evaluate("""
      () => { const i = document.querySelector('#mark img');
              const m = document.getElementById('mark');
              return { w: i.naturalWidth, complete: i.complete,
                       hidden: m.hidden, src: i.getAttribute('src') }; }
    """)
    check(state["src"].startswith("assets/"),
          f"{label}: the mark is loaded from assets/", state["src"])
    if state["w"] > 0:
        check(not state["hidden"], f"{label}: a mark that loads is shown")
        # One gesture, two effects: the mark spins and the menu opens. Checked
        # together because that is what a tap does -- asserting them separately
        # meant the spin check left the menu open under the next one.
        menu = page.locator("#markMenu")
        check(menu.is_hidden(), f"{label}: the menu starts closed")
        mark.click()
        page.wait_for_timeout(80)
        check(menu.is_visible(), f"{label}: tapping the mark opens the menu")
        check(page.locator("#mark").get_attribute("aria-expanded") == "true",
              f"{label}: and says so to a screen reader")
        # It drops down rather than appearing, and the page goes quiet behind it.
        anim = page.evaluate(
            "() => getComputedStyle(document.getElementById('markMenu')).animationName")
        check(anim == "menu-drop", f"{label}: the menu animates down", str(anim))
        dim = page.locator("#markDim")
        check(dim.is_visible(), f"{label}: and the page behind it is dimmed")
        mw = menu.bounding_box()["width"]
        check(mw >= 200, f"{label}: the menu is wide enough to read", str(round(mw)))
        # The little person lives in the menu now, beside Who am I. Holding him
        # winds him up; the header mark itself no longer turns.
        figure = page.locator("#markTop")
        check(figure.count() == 1, f"{label}: the little person is in the menu")
        fb = figure.bounding_box()
        page.mouse.move(fb["x"] + fb["width"] / 2, fb["y"] + fb["height"] / 2)
        page.mouse.down()
        page.wait_for_timeout(700)
        check("spinning" in (figure.get_attribute("class") or ""),
              f"{label}: holding him winds him up")
        turned = page.evaluate(
            "() => document.querySelector('#markTop img').style.transform")
        check("rotate" in (turned or ""), f"{label}: and he turns", str(turned))
        check(menu.is_visible(),
              f"{label}: spinning him does not close the menu he is in")
        page.mouse.up()
        # He coasts down under friction rather than on a timer, so the class
        # has to come off at the end or he could never go again.
        page.wait_for_timeout(4000)
        check("spinning" not in (figure.get_attribute("class") or ""),
              f"{label}: and the spin clears itself so it can go again")
        check("spinning" not in (mark.get_attribute("class") or ""),
              f"{label}: the header mark itself never spins")
    else:
        # Skipped, not returned from: a brand file that has not been uploaded
        # yet must not cost the other three hundred checks in this run.
        check(state["hidden"],
              f"{label}: a missing mark hides itself rather than showing a broken image",
              str(state))
        print(f"  ---- no mark uploaded; skipped the spin checks")

        # ---- the mark is a spinning top ----
        # A quick tap opens the menu; holding winds him up, and letting go
        # leaves him coasting to a stop wherever his momentum takes him. So a
        # long press must NOT also toggle the menu: the hand asked for a spin.
        angle_of = """() => {
          const m = getComputedStyle(document.querySelector('#mark img')).transform;
          const n = m && m.match(/matrix\\(([^)]+)\\)/);
          if(!n) return 0;
          const [a, b] = n[1].split(',').map(Number);
          return Math.atan2(b, a) * 180 / Math.PI;
        }"""
        if menu.is_visible():
            page.keyboard.press("Escape"); page.wait_for_timeout(120)
        mb2 = mark.bounding_box()
        cx, cy = mb2["x"] + mb2["width"] / 2, mb2["y"] + mb2["height"] / 2
        page.mouse.move(cx, cy)
        page.mouse.down()
        page.wait_for_timeout(900)
        spun_a = page.evaluate(angle_of)
        page.wait_for_timeout(150)
        spun_b = page.evaluate(angle_of)
        check(abs(spun_a - spun_b) > 0.5,
              f"{label}: holding the mark winds him up",
              f"{spun_a:.1f} then {spun_b:.1f}")
        page.mouse.up()
        check(menu.is_hidden(),
              f"{label}: and a long press is a spin, not a request for the menu")
        # Momentum: still turning after the finger is off.
        after_a = page.evaluate(angle_of)
        page.wait_for_timeout(200)
        after_b = page.evaluate(angle_of)
        check(abs(after_a - after_b) > 0.5,
              f"{label}: he keeps turning once released",
              f"{after_a:.1f} then {after_b:.1f}")
        # And he stops, holding whatever angle he stopped on.
        for _ in range(24):
            page.wait_for_timeout(250)
            if page.evaluate(
                "() => !document.getElementById('mark').classList.contains('spinning')"):
                break
        check(page.evaluate(
                "() => !document.getElementById('mark').classList.contains('spinning')"),
              f"{label}: and comes to rest")
        rest_a = page.evaluate(angle_of)
        page.wait_for_timeout(350)
        check(abs(page.evaluate(angle_of) - rest_a) < 0.01,
              f"{label}: resting wherever his momentum left him",
              f"{rest_a:.1f} deg")

    # The links live in that menu. The foot of the page was the wrong home for
    # them: nobody scrolls past the puzzle to find out what the game is.
    menu = page.locator("#markMenu")
    if menu.is_hidden():
        mark.click(); page.wait_for_timeout(120)
    hrefs = menu.locator("a").evaluate_all("els => els.map(e => e.href)")
    filled = page.evaluate("Object.values(LINKS).filter(Boolean).length")
    check(len(hrefs) == filled,
          f"{label}: every link with an address is shown, and only those",
          f"{len(hrefs)} shown, {filled} configured")
    check(all(h.startswith("https://") or h.startswith("mailto:") for h in hrefs),
          f"{label}: and each goes somewhere real", str(hrefs))
    # Grouped, because seven links in one run put the official registers level
    # with an Instagram handle. Every group with links in it gets its heading,
    # and a heading over nothing is worse than none.
    heads = menu.locator(".menu-head").all_inner_texts()
    groups_with_links = page.evaluate(
        "() => LINK_GROUPS.filter(g => g.keys.some(k => LINKS[k])).length")
    check(len(heads) == groups_with_links,
          f"{label}: the menu is grouped under headings", str(heads))
    check(all(h.strip() for h in heads),
          f"{label}: and every heading is written in this language", str(heads))
    # The registers come before the game's own links: they are the reason the
    # menu exists rather than an afterthought under it.
    first_group = page.evaluate("() => LINK_GROUPS[0].keys.filter(k => LINKS[k])[0]")
    check(hrefs[0] == page.evaluate("k => LINKS[k]", first_group),
          f"{label}: with somewhere to read further at the top", hrefs[0])

    # Who am I: the one item in the menu that stays inside the game.
    check(page.locator("#aboutOpen").count() == 1, f"{label}: the menu offers Who am I")
    page.locator("#aboutOpen").click(); page.wait_for_timeout(250)
    about = page.locator("#aboutBackdrop")
    check("open" in (about.get_attribute("class") or ""),
          f"{label}: which opens a panel")
    paras = page.locator("#aboutBody p").all_inner_texts()
    check(len(paras) >= 3, f"{label}: with something actually written in it",
          str(len(paras)))
    check(all(len(x) > 120 for x in paras),
          f"{label}: and none of it is a placeholder",
          str([len(x) for x in paras]))
    check(page.locator("#aboutTitle").inner_text().strip() != "",
          f"{label}: and a title")
    page.keyboard.press("Escape"); page.wait_for_timeout(200)
    check("open" not in (about.get_attribute("class") or ""),
          f"{label}: Escape closes the panel")
    # Every language has to carry the text; a missing one would silently read
    # in English, which is the failure this project keeps guarding against.
    said = {}
    for code in ("en", "fr", "es"):
        page.click(f".lang-btn[data-lang='{code}']")
        page.wait_for_timeout(120)
        if menu.is_hidden():
            mark.click(); page.wait_for_timeout(120)
        page.locator("#aboutOpen").click(); page.wait_for_timeout(180)
        said[code] = "\n".join(page.locator("#aboutBody p").all_inner_texts())
        check(len(said[code]) > 600, f"{label}: {code.upper()} Who am I is written",
              str(len(said[code])))
        page.keyboard.press("Escape"); page.wait_for_timeout(150)
    check(len({said["en"], said["fr"], said["es"]}) == 3,
          f"{label}: and each language is its own text, not a fallback")
    page.click(".lang-btn[data-lang='en']"); page.wait_for_timeout(120)
    if menu.is_hidden():
        mark.click(); page.wait_for_timeout(120)

    # It has to be dismissable, or it sits over the board.
    page.keyboard.press("Escape"); page.wait_for_timeout(120)
    check(menu.is_hidden(), f"{label}: Escape closes the menu")
    mark.click(); page.wait_for_timeout(120)
    # A real click, at a point the page itself confirms is empty. Three
    # hand-picked targets were wrong in three different ways: the photograph
    # opens the lightbox, whose overlay then swallows every later click; the
    # tagline sits underneath the open menu; and a point just right of the menu
    # landed on the nav and switched views, which broke every check after it.
    # So: ask the document what is at a candidate point, and only click where
    # nothing interactive lives.
    spot = page.evaluate("""
      () => {
        const m = document.getElementById('markMenu').getBoundingClientRect();
        const busy = 'button, a, .nav, .map-wrap, .photo-box, .modal, .lightbox,'
                   + ' input, label, .mark, .mark-menu';
        for(let y = Math.round(m.bottom) + 8; y < innerHeight - 8; y += 6){
          for(let x = 8; x < innerWidth - 8; x += 10){
            if(x > m.left - 4 && x < m.right + 4 && y > m.top - 4 && y < m.bottom + 4) continue;
            const el = document.elementFromPoint(x, y);
            if(!el || el.closest(busy)) continue;
            return { x, y, at: el.tagName.toLowerCase() + '.' + (el.className || '') };
          }
        }
        return null;
      }
    """)
    check(spot is not None, f"{label}: there is somewhere empty to tap")
    if spot:
        page.mouse.click(spot["x"], spot["y"])
        page.wait_for_timeout(150)
        check(menu.is_hidden(),
              f"{label}: and a tap anywhere else closes it", str(spot))
        check(page.locator("#markDim").is_hidden(),
              f"{label}: and the dimmer goes with it")

    # Guessing is done by pointing at the map. Every country the game will
    # accept has to be reachable that way, or it cannot be guessed at all.
    check(page.evaluate("!!LAND_SHAPES"), f"{label}: country shapes loaded")
    # Reachable means a tap can actually select it: a polygon to land in, or
    # -- for a country too small to have one, like Vatican City -- close
    # enough to its centroid for the snap to catch it.
    unreachable = page.evaluate("""
      () => COUNTRIES.filter(c => {
        if(!c.iso) return true;
        if(LAND_SHAPES[c.iso]) return false;
        // The path a real tap takes, not countryNear in isolation: the
        // polygon test runs first and can answer with the enclosing country.
        const p = project(c.lat, c.lng);
        const got = countryByIso(isoAt(p.x, p.y)) || countryNear(p.x, p.y);
        return !(got && got.id === c.id);
      }).map(c => c.names.en)
    """)
    check(not unreachable, f"{label}: every guessable country can be tapped",
          ", ".join(unreachable[:5]))
    # And no entry may be left with an answer nobody can give.
    unwinnable = page.evaluate("""
      () => { const ok = new Set(COUNTRIES.map(c => c.id));
              return POOL.filter(e => !(e.countryIds || []).some(id => ok.has(id)))
                         .map(e => e.names.en); }
    """)
    check(not unwinnable, f"{label}: no entry has an unreachable answer",
          ", ".join(unwinnable[:5]))
    # Open water is not a guess, and must not spend one.
    before = page.evaluate("state.guesses[0].length")
    page.evaluate(TAP_JS, {"lat": 0, "lng": -140})
    page.wait_for_timeout(200)
    check(page.evaluate("state.guesses[0].length") == before,
          f"{label}: tapping open water does not spend a guess")
    check(page.locator("#pendingGuess").is_hidden(),
          f"{label}: open water proposes nothing")
    # The confirm bar sits below the map; on a phone that is off-screen, so a
    # pin would appear with no visible way to commit it.
    pt = page.evaluate("() => { const c = COUNTRIES[0]; return {lat:c.lat, lng:c.lng}; }")
    page.evaluate(TAP_JS, pt)
    page.wait_for_timeout(700)
    pb, vh = page.locator("#pendingGuess").bounding_box(), page.viewport_size["height"]
    # Fully visible is the requirement. The scroll-margin cushion only applies
    # when a scroll actually happens, and once the header stopped wasting 60px
    # the bar fits without one -- the browser then leaves it where it is, a
    # couple of pixels off the bottom, which is in view and tappable.
    check(bool(pb) and pb["y"] >= 0 and pb["y"] + pb["height"] <= vh,
          f"{label}: the confirm bar is fully on screen",
          f"bottom={pb and round(pb['y'] + pb['height'])} vh={vh}")
    page.evaluate("clearPending(); renderMapForRound();")
    page.wait_for_timeout(150)
    # The detailed geometry is fetched, not inlined, so a missing or
    # canvas-mismatched file degrades silently to the coarse outline.
    check(page.evaluate("LAND_PATH !== null"), f"{label}: detailed map geometry loaded")
    # Pin radii are in world units and must counter-scale, or a guess dot
    # covers a whole country once you zoom in.
    r_world, r_zoom = page.evaluate("""
      () => {
        addPin(0, 0, 'far', false);
        const c = document.querySelector('#pinLayer circle');
        const a = parseFloat(c.getAttribute('r'));
        mapView.w = MAP_W / 8; applyView();
        const b = parseFloat(c.getAttribute('r'));
        mapView = { x:0, y:0, w:MAP_W, h:MAP_H }; applyView();
        return [a, b];
      }
    """)
    check(r_zoom < r_world / 4, f"{label}: pins scale with the map",
          f"world r={r_world} zoomed r={r_zoom}")

    # ---- every language renders ----
    # Needles from each tagline that do not appear in the other two.
    for code, needle in (("fr", "chaque jour"), ("es", "cada día"), ("en", "each day")):
        page.click(f".lang-btn[data-lang='{code}']")
        page.wait_for_timeout(120)
        check(needle in page.locator("#tagline").inner_text().lower(),
              f"{label}: {code.upper()} renders")

    # ---- a guess must report its verdict without scrolling ----
    # The verdict used to live only in the history list below the map, so on a
    # phone a guess looked like it had done nothing.
    # Played through the map rather than by calling submitGuess: the input is
    # the part most likely to break, and driving the game past it would hide
    # exactly that.
    tap_guess(page, "COUNTRIES.find(c => c.names.en !== targets[0].country.en)")
    page.wait_for_timeout(600)      # the panel is scrolled into view smoothly
    readout = page.locator("#mapReadout")
    check("last-guess" in (readout.get_attribute("class") or ""),
          f"{label}: the guess verdict is shown under the map")
    check(readout.locator(".hist-tag").count() == 3,
          f"{label}: country, continent and region are marked on it",
          str(readout.locator(".hist-tag").count()))
    rbox, vh = readout.bounding_box(), page.viewport_size["height"]
    # Wholly on screen and not flush against the bottom edge.
    check(bool(rbox) and rbox["y"] >= 0 and rbox["y"] + rbox["height"] <= vh - 8,
          f"{label}: the verdict is on screen without scrolling",
          f"bottom={rbox and round(rbox['y'] + rbox['height'])} vh={vh}")

    # ---- an element inscribed by several states accepts any of them ----
    # Marking eleven of Nowruz's twelve countries wrong would be a bug, not a
    # hard round, and the pipeline used to keep only the first of them.
    multi = page.evaluate("""
      () => {
        const e = POOL.find(d => d.countryIds && d.countryIds.length > 1);
        if(!e) return null;
        return { n: e.countryIds.length, names: e.countryNames.map(c => c.en) };
      }
    """)
    check(multi is not None, f"{label}: the pool has multinational entries")
    if multi:
        ok = page.evaluate("""
          names => {
            const e = POOL.find(d => d.countryIds && d.countryIds.length > 1);
            const saved = targets[0];
            targets[0] = e;
            const before = state.round; state.round = 0;
            const accepted = names.map(n =>
              targetCountries().some(c => c.names.en === n));
            targets[0] = saved; state.round = before;
            return accepted;
          }
        """, multi["names"])
        check(all(ok), f"{label}: every inscribing country counts as correct",
              str(list(zip(multi["names"], ok))))

    # ---- a wrong guess reveals another photograph, and you can page back ----
    # A single weak photo made a round unguessable rather than hard, so each
    # miss uncovers another. Driven through submitGuess rather than by poking
    # the state, because the view advancing is part of the behaviour.
    photo_state = page.evaluate("""
      () => {
        const tg = POOL.find(t => (t.photos || []).length > 2);
        if(!tg) return null;
        targets[state.round] = tg;
        // Staging a new target for this round means staging a live round: the
        // guess above can land on a second inscribing country and solve it,
        // and submitGuess refuses to act on a finished round.
        state.roundStatus[state.round] = null;
        photoView[state.round] = 0;
        render();
        const first = currentPhoto(tg).file;
        const unlockedBefore = unlockedCount(tg);
        // Not already guessed: a repeat is refused outright, and the first
        // non-answer country is exactly the one the verdict check above used.
        const wrong = COUNTRIES.find(c => !targetCountries().some(a => a.id === c.id)
                                       && !currentGuesses().some(g => g.id === c.id));
        submitGuess(wrong);
        const after = currentPhoto(tg).file;
        const shownIdx = photoIndexFor(tg);
        const unlockedAfter = unlockedCount(tg);
        stepPhoto(-1);
        const backIdx = photoIndexFor(tg), backOne = currentPhoto(tg).file;
        stepPhoto(1);
        const forwardAgain = currentPhoto(tg).file;
        return { first, after, backOne, forwardAgain, shownIdx, backIdx,
                 unlockedBefore, unlockedAfter,
                 credit: document.getElementById('photoCredit').textContent };
      }
    """)
    check(photo_state is not None, f"{label}: some entries carry several photos")
    if photo_state:
        check(photo_state["unlockedAfter"] == photo_state["unlockedBefore"] + 1,
              f"{label}: a guess unlocks one more photograph",
              f"{photo_state['unlockedBefore']} -> {photo_state['unlockedAfter']}")
        check(photo_state["shownIdx"] == photo_state["unlockedAfter"] - 1,
              f"{label}: the newly unlocked photograph is the one shown",
              f"index {photo_state['shownIdx']} of {photo_state['unlockedAfter']}")
        # Back one from whatever is showing -- not back to the first, since a
        # guess earlier in the round may already have unlocked others.
        check(photo_state["backIdx"] == photo_state["shownIdx"] - 1
              and photo_state["backOne"] != photo_state["after"],
              f"{label}: you can page back to an earlier photograph",
              f"index {photo_state['backIdx']} after {photo_state['shownIdx']}")
        check(photo_state["forwardAgain"] == photo_state["after"],
              f"{label}: and forward again to the newest")
        # A photographer's name or licence template often names a country.
        check(photo_state["credit"] == "",
              f"{label}: no photo credit while the round is live",
              photo_state["credit"])
    page.reload()
    page.wait_for_function("typeof POOL !== 'undefined' && POOL.length > 0", timeout=15000)
    page.evaluate("document.getElementById('fnClose')?.click()")
    page.wait_for_timeout(250)
    # The checks above spent guesses on round 1, and what a solve is worth now
    # depends on which guess it lands on -- so clear the round before playing
    # it, or "the first guess" is not the first guess.
    page.evaluate("""
      () => { state.guesses[0] = []; state.roundStatus[0] = null;
              state.roundScore[0] = 0; saveState(); render(); }
    """)
    page.wait_for_timeout(150)

    # ---- round 1: win outright ----
    page.evaluate("submitGuess(targetCountry())")
    page.wait_for_timeout(250)
    check(page.evaluate("state.roundStatus[0]") == "solved", f"{label}: round 1 won")
    check(abs(page.evaluate("state.roundScore[0]") - page.evaluate("ROUND_PLAN[0].points")) < 0.01,
          f"{label}: the country on the first guess takes full marks",
          str(page.evaluate("state.roundScore[0]")))
    page.click("#nextBtn"); page.wait_for_timeout(250)

    # ---- round 2: spend the allowance -- the best guess is what scores ----
    allowed = page.evaluate("guessesAllowed(1)")
    check(allowed == 4, f"{label}: four guesses on a heritage round", str(allowed))
    wrongs = page.evaluate("""
      () => COUNTRIES.filter(c => c.names.en !== targets[1].country.en)
                     .slice(0, 4).map(c => c.id)
    """)
    check(len(wrongs) == 4, f"{label}: four wrong countries available", str(len(wrongs)))
    for i, cid in enumerate(wrongs):
        page.evaluate("id => submitGuess(COUNTRIES.find(c => c.id === id))", cid)
        page.wait_for_timeout(60)
        if i == 0:
            # The whole point of this panel: after a wrong guess it has to be
            # impossible to think you solved it. The first player through the
            # game guessed a neighbouring country, saw two ticks and a small
            # distance, and concluded the game was broken.
            rd = page.locator("#mapReadout")
            txt = rd.inner_text()
            check("\u2717" in txt, f"{label}: a wrong guess is marked with a cross", txt)
            verdict = rd.locator(".lg-verdict").inner_text()
            check("\u2717" in verdict and len(verdict.strip()) > 3,
                  f"{label}: and says in words that the country is wrong", verdict)
            check(rd.locator(".lg-verdict.no").count() == 1
                  and rd.locator(".lg-verdict.ok").count() == 0,
                  f"{label}: the verdict is not dressed as a success")
            tags = rd.locator(".hist-tag").all_inner_texts()
            check(len(tags) == 3,
                  f"{label}: country, continent and region each get a mark", str(tags))
            check(tags[0].startswith("\u2717"),
                  f"{label}: and the country mark is the wrong one", str(tags))
            pips = rd.locator(".lg-pip")
            check(pips.count() == 4, f"{label}: one box per try", str(pips.count()))
            check(rd.locator(".lg-pip.used").count() == 1
                  and rd.locator(".lg-pip.free").count() == 3,
                  f"{label}: one box spent, three still open")
            tries = rd.locator(".lg-tries").inner_text()
            check("1" in tries and "4" in tries,
                  f"{label}: the tries are counted where the eye already is", tries)
            check("3" in tries, f"{label}: and it says how many are left", tries)
    check(page.evaluate("state.roundStatus[1]") == "failed", f"{label}: round 2 missed",
          str(page.evaluate("state.roundStatus[1]")))
    check(page.evaluate("state.guesses[1].length") == 4,
          f"{label}: the round ends after its allowance")
    # Scored on the closest guess of the round, not the last one: a player who
    # narrowed it down and then gambled the final try keeps what they found.
    expected = page.evaluate("() => ROUND_PLAN[1].points * missCredit(state.guesses[1])")
    check(abs(page.evaluate("state.roundScore[1]") - expected) < 0.01,
          f"{label}: the best guess is the one that scores",
          f"{page.evaluate('state.roundScore[1]')} vs {expected}")
    check(page.evaluate("state.roundScore[1]") < page.evaluate("ROUND_PLAN[1].points"),
          f"{label}: a missed round scores less than full marks")
    # Missing has to be worth less than the worst possible solve, or the
    # incentive to actually find it disappears.
    check(page.evaluate("state.roundScore[1]")
          < page.evaluate("ROUND_PLAN[1].points * SOLVE_CREDIT[SOLVE_CREDIT.length-1]"),
          f"{label}: and less than the latest possible solve")
    page.click("#nextBtn"); page.wait_for_timeout(250)

    # ---- round 3: a wrong guess first, then solve -- still full marks ----
    w = page.evaluate("() => COUNTRIES.find(c => c.names.en !== targets[2].country.en).id")
    page.evaluate("id => submitGuess(COUNTRIES.find(c => c.id === id))", w)
    page.wait_for_timeout(120)
    page.evaluate("submitGuess(targetCountry())")
    page.wait_for_timeout(250)
    check(page.evaluate("state.roundStatus[2]") == "solved", f"{label}: round 3 solved")
    rd = page.locator("#mapReadout")
    check(rd.locator(".lg-verdict.ok").count() == 1,
          f"{label}: a right country is marked right")
    check(rd.locator(".lg-pip.hit").count() == 1,
          f"{label}: and the box it was found on is ticked, not crossed")
    # Solving on the second guess is worth less than solving on the first, or
    # the day's score says nothing about how it went -- which is how every
    # score landed on one of eight values.
    expected = page.evaluate("() => ROUND_PLAN[2].points * SOLVE_CREDIT[1]")
    check(abs(page.evaluate("state.roundScore[2]") - expected) < 0.01,
          f"{label}: a later solve is worth less than an outright one",
          f"{page.evaluate('state.roundScore[2]')} vs {expected}")
    check(page.evaluate("state.roundScore[2]") > page.evaluate("ROUND_PLAN[2].points * 0.5"),
          f"{label}: but still most of the round")
    page.click("#nextBtn"); page.wait_for_timeout(250)

    # ---- round 4: the intangible bonus round ----
    # If the pool has no traditions in it the bonus round silently falls back
    # to a fourth site, so check the pool first -- otherwise the failure reads
    # as a game bug when it is a dataset that predates the intangible pool.
    check(page.evaluate("POOL.some(d => d.type === 'immaterial')"),
          f"{label}: the dataset carries intangible entries")
    check(page.evaluate("targets[3].type") == "immaterial",
          f"{label}: the bonus round is an intangible element",
          str(page.evaluate("targets[3].type")))
    # A tradition is far harder to place than a building, so a single guess
    # meant the round was lost by default rather than played. Three, like the
    # rest -- and the photograph ladder that comes with them.
    check(page.evaluate("guessesAllowed(3)") == 4,
          f"{label}: the bonus round allows four guesses",
          str(page.evaluate("guessesAllowed(3)")))
    check(T_BONUS_INTRO_SHOWN(page), f"{label}: the bonus round says so before the guess")
    wrongs = page.evaluate("""
      () => COUNTRIES.filter(c => !targetCountries().some(a => a.id === c.id))
                     .slice(0, 4).map(c => c.id)
    """)
    check(len(wrongs) == 4, f"{label}: four wrong countries available for the bonus")
    for i, cid in enumerate(wrongs):
        page.evaluate("id => submitGuess(COUNTRIES.find(c => c.id === id))", cid)
        page.wait_for_timeout(80)
        if i == 0:
            check(page.evaluate("state.roundStatus[3]") is None,
                  f"{label}: one wrong guess does not end the bonus round",
                  str(page.evaluate("state.roundStatus[3]")))
    check(page.evaluate("state.roundStatus[3]") == "failed", f"{label}: bonus round resolved")
    check(page.evaluate("state.guesses[3].length") == 4,
          f"{label}: the bonus round ends after its allowance",
          str(page.evaluate("state.guesses[3].length")))
    page.click("#nextBtn"); page.wait_for_timeout(400)

    # ---- final screen ----
    check(not page.locator("#finalResult").is_hidden(), f"{label}: final screen shown")
    # The badge row is emptied on this screen; an empty bordered pill used to
    # draw a small box above the summary.
    check(page.locator(".meta-row").is_hidden() or
          (page.locator(".meta-row").bounding_box() or {}).get("height", 0) == 0,
          f"{label}: no empty badge box above the summary")
    grid = page.locator("#finalResult .share-grid").inner_text()
    check("—" in grid or len(grid.strip()) > 0, f"{label}: share grid rendered", repr(grid))
    check(grid.count("\n") == 3, f"{label}: share grid has one line per round", repr(grid))
    score = page.evaluate("totalScore()")
    mx = page.evaluate("MAX_SCORE")
    check(mx == 150, f"{label}: the day is scored out of 150", str(mx))
    check(0 < score < mx, f"{label}: score reflects the missed rounds", f"{score}/{mx}")
    statuses = page.evaluate("state.roundStatus")
    check(statuses == ["solved", "failed", "solved", "failed"],
          f"{label}: 2 solved / 2 missed", str(statuses))

    check(not errors, f"{label}: no console errors", "; ".join(errors[:3]))
    check(not bad_requests, f"{label}: no broken script/data requests",
          "; ".join(bad_requests[:3]))
    return errors, bad_requests


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="test a deployed build instead of a local copy")
    ap.add_argument("--real", action="store_true",
                    help="serve the committed data/dataset.json rather than synthetic data")
    args = ap.parse_args()

    httpd = root = None
    if args.url:
        base = args.url if args.url.endswith("/") else args.url + "/"
        print(f"testing deployed build at {base}")
    else:
        root = tempfile.mkdtemp(prefix="heritle-smoke-")
        shutil.copy(os.path.join(REPO, "heritle.html"), os.path.join(root, "index.html"))
        # The page loads its mark from assets/, so the hermetic root needs them
        # -- otherwise even the fallback 404s and the check cannot tell a
        # missing file from a broken one.
        assets = os.path.join(REPO, "assets")
        if os.path.isdir(assets):
            shutil.copytree(assets, os.path.join(root, "assets"))
        if args.real:
            shutil.copytree(os.path.join(REPO, "data"), os.path.join(root, "data"))
            print("serving the committed dataset")
        else:
            subprocess.run([sys.executable, os.path.join(REPO, "tests", "make_synthetic_dataset.py"),
                            os.path.join(root, "data", "dataset.json")],
                           check=True, stdout=subprocess.DEVNULL)
            # The map geometry is real either way -- it is independent of the
            # dataset, and without it the run reports a missing-file failure
            # that says nothing about the game.
            land = os.path.join(REPO, "data", "land.json")
            if os.path.exists(land):
                shutil.copy(land, os.path.join(root, "data", "land.json"))
        httpd, port = serve(root)
        base = f"http://127.0.0.1:{port}/"

    chrome = os.environ.get("CHROME_BIN") or next(
        (p for p in glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")), None)
    launch = {"args": ["--no-sandbox"]}
    if chrome and os.path.exists(chrome):
        launch["executable_path"] = chrome

    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch)
        for label, vp, mobile in [("mobile 375", {"width": 375, "height": 812}, True),
                                  ("desktop 1280", {"width": 1280, "height": 900}, False)]:
            print(f"\n== {label} ==")
            for day in DAYS[:1] if args.url else DAYS:
                ctx = browser.new_context(viewport=vp, has_touch=mobile, is_mobile=mobile)
                page = ctx.new_page()
                play_day(page, base, day, vp["width"], f"{label} d{day}")
                ctx.close()

        # ---- the collection, passport and archive after a completed day ----
        print("\n== collection / passport / archive ==")
        ctx = browser.new_context(viewport={"width": 375, "height": 812},
                                  has_touch=True, is_mobile=True)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        play_day(page, base, None, 375, "profile")   # today: the scoring path
        page.evaluate("showView('Collection')"); page.wait_for_timeout(300)
        cards = page.locator("#viewCollection .card").count()
        check(cards >= 2, "solved entries are catalogued", str(cards))
        acc = page.locator("#viewCollection .acc").first.inner_text()
        check(acc.startswith("HTL."), "cards carry an accession number", acc)
        # A card is the only way back to something met in a round, so it has to
        # open, and open with links that go somewhere.
        page.locator("#viewCollection .card").first.click()
        page.wait_for_timeout(300)
        check("open" in (page.locator("#modalBackdrop").get_attribute("class") or ""),
              "a collection card opens its entry")
        # The photographs come first: a card is a drawer of plates, not a
        # caption. And the credits are owed in full here -- the answer is known.
        check(not page.locator("#gal").is_hidden(), "the entry opens on its photographs")
        check(bool(page.evaluate("document.getElementById('galImg').src")),
              "the gallery has a photograph in it")
        check(page.locator("#galCredit").inner_text().strip() != "",
              "the photograph is credited where nothing is left to spoil")
        links = page.locator("#modalLinks .learn-link").count()
        check(links >= 1, "the card's entry offers somewhere to learn more",
              str(links))
        hrefs = page.locator("#modalLinks .learn-link").evaluate_all(
            "els => els.map(e => e.href)")
        check(all(h.startswith("https://") for h in hrefs),
              "every link resolves to a real address", str(hrefs))
        # Rows of equal width, or they read as leftovers rather than a list.
        widths = page.locator("#modalLinks .learn-link").evaluate_all(
            "els => els.map(e => Math.round(e.getBoundingClientRect().width))")
        check(len(set(widths)) == 1, "the links line up as rows of one width",
              str(widths))
        labels = page.locator("#modalLinks .ll-text").all_inner_texts()
        check(any(l.lower().startswith("discover videos about") for l in labels),
              "the video row is named after the place", str(labels))
        check(labels[-1].lower().startswith("discover videos about"),
              "and comes last, under the reading links", str(labels))
        # One place to read about it, never two. The official listing where the
        # entry has one; the encyclopaedia only where it does not, and only for
        # a title the build checked.
        rows = page.evaluate("""
          () => {
            const pick = (test) => POOL.find(test);
            const read = (e) => {
              const div = document.createElement('div');
              div.innerHTML = learnLinks(e).join('');
              return [...div.querySelectorAll('.learn-link')].map(a => a.href);
            };
            const withSite = pick(e => e.siteId);
            const withWiki = pick(e => !e.siteId && !e.officialUrl && e.wiki);
            const withNone = pick(e => !e.siteId && !e.officialUrl && !e.wiki);
            return {
              site: withSite ? read(withSite) : null,
              wiki: withWiki ? read(withWiki) : null,
              none: withNone ? read(withNone) : null
            };
          }
        """)
        if rows["site"]:
            check(any("whc.unesco.org" in h for h in rows["site"]),
                  "an inscribed site links to its official listing", str(rows["site"]))
            check(not any("wikipedia.org" in h for h in rows["site"]),
                  "and is not also sent to the encyclopaedia", str(rows["site"]))
        check(rows["wiki"] is not None,
              "the pool has entries with no official page but a checked article")
        if rows["wiki"]:
            check(any("wikipedia.org" in h for h in rows["wiki"]),
                  "an entry with no official page falls back to the article",
                  str(rows["wiki"]))
            check(len(rows["wiki"]) == 2,
                  "which is one place to read and one to watch", str(rows["wiki"]))
        if rows["none"]:
            check(len(rows["none"]) == 1 and "youtube" in rows["none"][0],
                  "an entry with neither is left with the video search alone",
                  str(rows["none"]))
        # Favouriting from the card that is already open.
        page.locator("#modalFav").click(); page.wait_for_timeout(200)
        page.evaluate("document.getElementById('modalClose').click()")
        page.wait_for_timeout(250)
        check(page.evaluate("Object.keys(profile.favourites).length") == 1,
              "the star keeps an entry",
              str(page.evaluate("Object.keys(profile.favourites).length")))
        heads = page.locator("#viewCollection .panel-head h2").all_inner_texts()
        check(len(heads) == 2 and "Favourite" in heads[0],
              "favourites get a shelf of their own, first", str(heads))
        check(page.locator("#viewCollection .card .fav.on").count() == 1,
              "and the starred card shows as kept")
        # Paging, staged on an entry that certainly has several photographs
        # rather than on whichever one the day happened to catalogue. Last,
        # because this entry need not be in the collection -- and on one that
        # is not, the star is rightly hidden.
        page.evaluate("""
          () => { const e = POOL.find(d => (d.photos || []).length > 1);
                  if(e) openInfoModal(e, profile.collection[e.id]); }
        """)
        page.wait_for_timeout(200)
        shots = page.evaluate("galleryShots.length")
        check(shots > 1, "an entry with several photographs opens with them all",
              str(shots))
        if shots > 1:
            first = page.evaluate("document.getElementById('galImg').src")
            page.locator("#galNext").click(); page.wait_for_timeout(150)
            check(page.evaluate("document.getElementById('galImg').src") != first,
                  "the gallery pages to the next photograph")
            check(page.locator("#galDots i.on").count() == 1,
                  "exactly one dot marks where you are")
            page.locator("#galPrev").click(); page.wait_for_timeout(150)
            check(page.evaluate("document.getElementById('galImg').src") == first,
                  "and back again")
        if shots > 1:
            # A swipe, because reaching for a small arrow is not what a hand
            # expects to do with a photograph.
            at = page.evaluate("galleryAt")
            page.evaluate("""
              () => {
                const gal = document.getElementById('gal');
                const r = gal.getBoundingClientRect();
                const y = r.top + r.height / 2;
                const touch = (type, x) => gal.dispatchEvent(new TouchEvent(type, {
                  bubbles: true,
                  changedTouches: [new Touch({ identifier: 1, target: gal,
                                               clientX: x, clientY: y })]
                }));
                touch('touchstart', r.left + r.width * 0.8);
                touch('touchend',   r.left + r.width * 0.2);
              }
            """)
            page.wait_for_timeout(150)
            check(page.evaluate("galleryAt") == at + 1,
                  "swiping left moves to the next photograph",
                  str(page.evaluate("galleryAt")))
            page.evaluate("""
              () => {
                const gal = document.getElementById('gal');
                const r = gal.getBoundingClientRect();
                const y = r.top + r.height / 2;
                const touch = (type, x) => gal.dispatchEvent(new TouchEvent(type, {
                  bubbles: true,
                  changedTouches: [new Touch({ identifier: 1, target: gal,
                                               clientX: x, clientY: y })]
                }));
                touch('touchstart', r.left + r.width * 0.2);
                touch('touchend',   r.left + r.width * 0.8);
              }
            """)
            page.wait_for_timeout(150)
            check(page.evaluate("galleryAt") == at,
                  "and swiping right goes back")
            # A mostly-vertical drag is the page scrolling, not a swipe.
            page.evaluate("""
              () => {
                const gal = document.getElementById('gal');
                const r = gal.getBoundingClientRect();
                const x = r.left + r.width / 2;
                const touch = (type, y) => gal.dispatchEvent(new TouchEvent(type, {
                  bubbles: true,
                  changedTouches: [new Touch({ identifier: 1, target: gal,
                                               clientX: x, clientY: y })]
                }));
                touch('touchstart', r.top + 10);
                touch('touchend',   r.top + 120);
              }
            """)
            page.wait_for_timeout(150)
            check(page.evaluate("galleryAt") == at,
                  "a vertical drag is a scroll, not a swipe")
        check(page.locator("#modalFav").is_hidden(),
              "an entry not in the collection offers no star to keep it by")
        page.evaluate("document.getElementById('modalClose').click()")
        page.wait_for_timeout(200)

        # Starring must not open the card -- it is a button of its own.
        page.evaluate("document.getElementById('modalBackdrop').classList.remove('open')")
        page.locator("#viewCollection .card .fav").first.click()
        page.wait_for_timeout(250)
        check("open" not in (page.locator("#modalBackdrop").get_attribute("class") or ""),
              "tapping the star does not open the card")
        check(page.evaluate("Object.keys(profile.favourites).length") == 0,
              "and starring again puts it back")
        page.evaluate("showView('Passport')"); page.wait_for_timeout(300)
        check(page.locator("#viewPassport .stamp").count() >= 1, "passport shows a stamp")
        # What a player comes back to is the stamps they have, so the earned
        # ones are on the page and the rest are behind a disclosure.
        # Visible, not total: a secret nobody has earned is not listed, which
        # is the point of it being secret.
        expected_ach = page.evaluate("visibleAchievements().length")
        total_ach = page.evaluate("ACHIEVEMENTS.length")
        tiers = page.evaluate("ARCHIVIST_TIERS")
        for want in (100, 250, 500, 750, 1000):
            check(want in tiers, f"the collection ladder reaches {want}", str(tiers))
        check(tiers == sorted(tiers), "and it climbs in order", str(tiers))
        pool = page.evaluate("POOL.length")
        check(max(tiers) <= pool,
              "the top of the ladder is inside the pool, so it can be reached",
              f"top {max(tiers)} of {pool} entries")
        # A tier with no name renders as an empty stamp, in one language only,
        # which is exactly the kind of gap nobody notices until a player gets
        # there months later.
        missing = page.evaluate("""
          () => {
            const out = [];
            for(const code of ['en','fr','es']){
              for(const n of ARCHIVIST_TIERS){
                const e = UI[code].ach.coll[n];
                if(!e || !e[0] || !e[1]) out.push(code + ':' + n);
              }
            }
            return out;
          }
        """)
        check(not missing, "every tier is named in all three languages", str(missing))
        marks = page.evaluate(
            "() => ACHIEVEMENTS.filter(a => a.tier).map(a => a.mark)")
        check(all(len(m) <= 3 for m in marks),
              "and its stamp mark is short enough to read on a stamp", str(marks))
        check(expected_ach >= 20, "there are distinctions worth chasing",
              str(expected_ach))
        check(total_ach > expected_ach,
              "and at least one of them is a secret, so it is not listed",
              f"{total_ach} defined, {expected_ach} shown")
        secret = page.evaluate("""
          () => ACHIEVEMENTS.filter(a => a.secret).map(a => a.id)
        """)
        names = page.locator("#viewPassport .ach-tile span").all_inner_texts()
        check(bool(secret), "a secret distinction exists", str(secret))
        check(not any("Dizzy" in n for n in names),
              "and it is nowhere on the page until it is earned", str(names))
        # Earn it the way a player would: hold him down until he has turned a
        # hundred times without stopping. Measured at about ten and a half
        # seconds of holding, so this is slow but it is the real path.
        page.evaluate("showView('Today')"); page.wait_for_timeout(200)
        if page.locator("#markMenu").is_hidden():
            page.locator("#mark").click()
            page.wait_for_timeout(250)
        dz = page.locator("#markTop").bounding_box()
        page.mouse.move(dz["x"] + dz["width"] / 2, dz["y"] + dz["height"] / 2)
        page.mouse.down()
        got = False
        for _ in range(40):                      # up to 20s
            page.wait_for_timeout(500)
            if page.evaluate("() => !!profile.dizzy"):
                got = True
                break
        page.mouse.up()
        page.keyboard.press("Escape")       # or the dimmer eats the next click
        page.wait_for_timeout(200)
        check(got, "a hundred turns without stopping earns Dizzy")
        if got:
            check(page.locator(".award-card").count() == 1,
                  "and it says so when it happens rather than waiting to be found")
            check("Dizzy" in page.locator(".award-card").inner_text(),
                  "naming it on the card",
                  page.locator(".award-card").inner_text().replace("\n", " / "))
            check(page.evaluate("() => profile.achievements.includes('dizzy')"),
                  "and it is recorded")
            page.evaluate("showView('Passport')"); page.wait_for_timeout(300)
            shown_names = page.locator("#viewPassport .ach-tile span").all_inner_texts()
            check(any("Dizzy" in n for n in shown_names),
                  "and now it is on the page", str(shown_names[-4:]))
            # Earning one secret reveals that one and no other, so the
            # denominator moves by exactly one. It used to be compared against
            # the whole table, which was the same number only while Dizzy was
            # the only secret there was.
            expected_ach = page.evaluate("visibleAchievements().length")
            head = page.locator("#viewPassport .panel-head p").last.inner_text()
            check(str(expected_ach) in head,
                  "and the count includes it once it exists",
                  f"{head} against {expected_ach} shown")
            still_hidden = page.evaluate("""
              () => ACHIEVEMENTS.filter(a => a.secret
                      && !profile.achievements.includes(a.id)).length
            """)
            check(still_hidden >= 1 and expected_ach == total_ach - still_hidden,
                  "and the secrets nobody has found yet stay out of the count",
                  f"{expected_ach} shown, {total_ach} defined, {still_hidden} hidden")
            # Generically: whatever secrets this run happens not to have
            # earned -- playing through it in three languages earns one of
            # them by itself -- must be nowhere on the page. Naming them here
            # assumed they were unearned, which is a different claim.
            hidden_names = page.evaluate("""
              () => ACHIEVEMENTS.filter(a => a.secret
                      && !profile.achievements.includes(a.id))
                      .map(a => t().ach[a.id][0])
            """)
            on_page = page.locator("#viewPassport").inner_text()
            check(all(n not in on_page for n in hidden_names),
                  "and finding one secret does not give away the others",
                  str(hidden_names))
        # Earned enough to be worth showing, rather than whatever four entries
        # in one day happens to unlock -- otherwise "only the earned ones are
        # shown" passes against an empty list and proves nothing.
        page.evaluate("""
          () => {
            POOL.slice(0, 60).forEach(e => catalogue(e, true));
            profile.days[dayIndex] = { score: MAX_SCORE,
              statuses: ['solved','solved','solved','solved'] };
            checkAchievements();
            renderPassport();
          }
        """)
        page.wait_for_timeout(250)
        earned = page.evaluate("profile.achievements.length")
        check(earned >= 5, "a filled collection earns a spread of distinctions",
              str(earned))
        shown = page.locator("#viewPassport > .ach-grid > .ach-tile").count()
        check(shown == earned, "only the earned distinctions are on the page",
              f"{shown} shown, {earned} earned")
        head = page.locator("#viewPassport .panel-head p").last.inner_text()
        check(str(earned) in head and str(expected_ach) in head,
              "the heading counts what is earned against what exists", head)
        # An earned stamp is turned; a locked one sits straight.
        rot = page.evaluate("""
          () => {
            const e = document.querySelector('#viewPassport > .ach-grid .stamp-mark');
            const l = document.querySelector('.ach-locked .stamp-mark');
            return [getComputedStyle(e).transform, l ? getComputedStyle(l).transform : 'none'];
          }
        """)
        check(rot[0] != "none" and rot[0] != rot[1],
              "an earned stamp is struck at an angle, a locked one is not", str(rot))
        # Three to a row, and the description only when asked for.
        cols = page.evaluate("""
          () => {
            const g = document.querySelector('#viewPassport > .ach-grid');
            return getComputedStyle(g).gridTemplateColumns.split(' ').length;
          }
        """)
        check(cols == 3, "the stamps sit three to a row", str(cols))
        check(page.locator("#viewPassport .ach-detail").count() == 0,
              "no description is shown until a stamp is tapped")
        page.evaluate("() => document.querySelectorAll('.award-card')"
                      ".forEach(e => e.remove())")
        tiles = page.locator("#viewPassport > .ach-grid > .ach-tile")
        # The fourth tile: its detail has to land at the end of the second row,
        # not at the bottom of the grid, or it reads as unrelated to the tap.
        target = min(3, tiles.count() - 1)
        tiles.nth(target).click(); page.wait_for_timeout(200)
        det = page.locator("#viewPassport .ach-detail")
        check(det.count() == 1, "tapping a stamp shows its description")
        check(det.first.inner_text().strip() != "",
              "which says what it is for", det.first.inner_text())
        near = page.evaluate("""
          i => {
            const g = document.querySelector('#viewPassport > .ach-grid');
            const kids = [...g.children];
            const tile = kids.filter(k => k.matches('.ach-tile'))[i];
            const det = g.querySelector('.ach-detail');
            return det.getBoundingClientRect().top - tile.getBoundingClientRect().bottom;
          }
        """, target)
        check(0 <= near < 120,
              "and it opens just under the row that was tapped", str(near))
        tiles.nth(target).click(); page.wait_for_timeout(200)
        check(page.locator("#viewPassport .ach-detail").count() == 0,
              "tapping it again closes it")
        det = page.locator("#viewPassport .ach-locked")
        check(det.count() == 1, "the rest are behind a disclosure")
        check(not page.evaluate(
                "document.querySelector('.ach-locked').hasAttribute('open')"),
              "which starts closed")
        # Closed means out of the way, not merely unstyled.
        check(page.locator(".ach-locked .ach-tile").first.is_hidden(),
              "a locked distinction is not visible until asked for")
        page.evaluate("document.querySelector('.ach-locked summary').click()")
        page.wait_for_timeout(200)
        check(page.locator(".ach-locked .ach-tile").first.is_visible(),
              "and is there when it is")
        check(page.locator("#viewPassport .ach-tile").count() == expected_ach,
              "every distinction is accounted for, open", str(expected_ach))
        # The stamp is drawn, not set in type: a glyph in a circle sat off
        # centre at every size, which is what made it look cheap.
        box = page.locator("#viewPassport .ach-tile .stamp-mark").first.bounding_box()
        check(box and abs(box["width"] - box["height"]) < 2,
              "the stamp is round", str(box))
        centred = page.evaluate("""
          () => {
            const svg = document.querySelector('.ach-tile .stamp-mark');
            const ring = svg.querySelector('.ring.inner').getBoundingClientRect();
            const txt = svg.querySelector('.stamp-text').getBoundingClientRect();
            return [Math.abs((ring.left + ring.right) / 2 - (txt.left + txt.right) / 2),
                    Math.abs((ring.top + ring.bottom) / 2 - (txt.top + txt.bottom) / 2)];
          }
        """)
        check(max(centred) < 2.5, "and its mark sits in the middle of it",
              str(centred))
        # Names, not numbers: a ladder called Archivist I..VI is a table row.
        names = page.locator("#viewPassport .ach-tile span").all_inner_texts()
        check(not any(re.search(r"\b(I{1,3}|IV|V|VI)$", n) for n in names),
              "no distinction is named by a numeral", str(names[:8]))
        check(any("Discovering" in n or "couverte" in n or "Descubriendo" in n
                  for n in names),
              "a continent can be discovered", str(names[:8]))
        # ---- the back catalogue is not a URL any more ----
        # ?day=N used to pin any puzzle, and the archive linked to it for each
        # of the last sixty days, so the whole history could be walked by
        # counting upwards. It is honoured only for a day this browser has
        # actually finished.
        print("\n== the back catalogue ==")
        today = page.evaluate("todayIndex")
        unplayed = today - 5
        fresh = ctx.new_page()
        fresh.goto(f"{base}?day={unplayed}")
        fresh.wait_for_function("typeof POOL !== 'undefined' && POOL.length > 0", timeout=15000)
        landed = fresh.evaluate("dayIndex")
        # Read again from the page that did the landing: a run that straddles
        # local midnight has two different "today"s, and comparing across the
        # boundary fails on a game that behaved perfectly.
        today = fresh.evaluate("todayIndex")
        # A day that has happened opens again -- as practice, which is what the
        # archive links to. What must hold is not that it is shut, but that it
        # pays nothing: no score, no collection, no distinction.
        if unplayed >= 0:
            check(landed == unplayed and fresh.evaluate("isPractice"),
                  "a day nobody played opens as practice",
                  f"asked {unplayed}, landed {landed}, "
                  f"practice {fresh.evaluate('isPractice')}")
            before_practice = fresh.evaluate("""
              () => ({ entries: Object.keys(profile.collection).length,
                       ach: profile.achievements.length })
            """)
            fresh.evaluate("document.getElementById('fnClose')?.click()")
            fresh.evaluate("submitGuess(targetCountry())")
            fresh.wait_for_timeout(300)
            check(fresh.evaluate("state.roundStatus[0]") == "solved",
                  "and plays like the game it is")
            # A delta, not a zero: this browser has already played today, so
            # its collection is not empty and never will be again.
            after = fresh.evaluate("""
              () => ({ entries: Object.keys(profile.collection).length,
                       day: !!profile.days[dayIndex],
                       ach: profile.achievements.length })
            """)
            check(after["entries"] == before_practice["entries"]
                  and not after["day"]
                  and after["ach"] == before_practice["ach"],
                  "while paying nothing into the collection, the record or the "
                  "distinctions", f"{before_practice} -> {after}")
        # Tomorrow, though, is not an archive.
        ahead = ctx.new_page()
        ahead.goto(f"{base}?day={today + 3}")
        ahead.wait_for_function("typeof POOL !== 'undefined' && POOL.length > 0",
                                timeout=15000)
        check(ahead.evaluate("dayIndex") == ahead.evaluate("todayIndex"),
              "a day that has not happened yet lands on today",
              str(ahead.evaluate("dayIndex")))
        ahead.close()
        check(landed == today or unplayed >= 0,
              "asking for a day before the game existed lands on today",
              f"asked {unplayed}, got {landed}")
        # A PAST day this browser has finished is still replayable -- it spoils
        # nothing, and the archive offers it. Seeded, because the only day this
        # run has finished is today, and replaying today is not a replay: the
        # first version of this check asked for today back and then wondered why
        # it was not practice.
        # One day back, not three: the game launched on day 0, so on day 1 a
        # "three days ago" is day -2 and does not exist. Skipped entirely on
        # launch day, when there is no past day to replay at all.
        seeded = today - 1
        if seeded < 0:
            print("  ---- day 0: no past day exists yet, skipped the replay check")
        page.evaluate("""
          d => { profile.days[d] = { score: 42, at: Date.now(),
                                     statuses: ['solved','failed','solved','failed'] };
                 saveProfile(); }
        """, seeded)
        if seeded >= 0:
            again = ctx.new_page()
            again.goto(f"{base}?day={seeded}")
            again.wait_for_function("typeof POOL !== 'undefined' && POOL.length > 0", timeout=15000)
            check(again.evaluate("dayIndex") == seeded,
                  "a past day you have finished can still be replayed",
                  f"asked {seeded}, got {again.evaluate('dayIndex')}")
            check(again.evaluate("isPractice") is True,
                  "and a replay is practice, so it cannot rewrite your record")
            again.close()
        fresh.close()

        page.evaluate("showView('Archive')"); page.wait_for_timeout(300)
        # One row per day since launch, capped at the 60 the archive shows. On
        # day one that is a single row -- an archive of days nobody could have
        # played would be padding, not history.
        # Every row opens now -- today to play, any past day to practise --
        # and a day nobody finished still says so beside its link.
        links = page.locator("#viewArchive .arch-row a").count()
        rows = page.locator("#viewArchive .arch-row").count()
        check(links == rows, "every archive row offers a way in",
              f"{links} links vs {rows} rows")
        hrefs = page.locator("#viewArchive .arch-row a").evaluate_all(
            "els => els.map(e => e.getAttribute('href'))")
        past = [h for h in hrefs if h != "."]
        check(all("practice=1" in h for h in past),
              "and every past day is offered as practice, not as a scored round",
              str(past[:3]))
        played_days = page.evaluate("Object.keys(profile.days).map(Number)")
        unplayed_rows = rows - sum(1 for d in played_days
                                   if max(0, today - 60) <= d <= today)
        check(page.locator("#viewArchive .arch-locked").count() == unplayed_rows,
              "a day nobody finished still says so",
              f"{page.locator('#viewArchive .arch-locked').count()} vs {unplayed_rows}")
        hrefs = page.locator("#viewArchive .arch-row a").evaluate_all(
            "els => els.map(e => e.getAttribute('href'))")
        check(all(h == "." or h.startswith("?day=") for h in hrefs),
              "archive links are today or a replay", str(hrefs))

        expected = min(page.evaluate("todayIndex") + 1, 61)
        check(page.locator("#viewArchive .arch-row").count() == expected,
              "archive lists one row per day since launch",
              f"{page.locator('#viewArchive .arch-row').count()} vs {expected}")
        # The row for a day that was actually played. Nothing looked at this
        # before, and it had been printing "76 / undefined" ever since the
        # score line started carrying its maximum.
        played = page.locator("#viewArchive .arch-row .arch-score").first.inner_text()
        check("undefined" not in played and "NaN" not in played,
              "a played day shows a real score in the archive", played)
        check("/" in played and played.strip().split("/")[-1].strip().isdigit(),
              "the archive score carries its maximum", played)
        # colour-blind toggle
        page.evaluate("showView('Passport')"); page.wait_for_timeout(200)
        page.check("#cbToggle"); page.wait_for_timeout(200)
        check(page.evaluate("document.body.classList.contains('cb')"),
              "colour-blind marks toggle on")
        check(not errors, "no console errors across the panels", "; ".join(errors[:3]))
        ctx.close()

        # ---- how the days are dealt ----
        # The pick used to be hash(day, slot) % pool.length: sampling with
        # replacement, so the first repeat landed on day 23-30 of real play and
        # a third of the first year re-dealt something already shown. These
        # checks run through the game's own dealFor(), one whole cycle at a
        # time, which is only possible because it takes the day as an argument.
        print("\n== the deal ==")
        ctx = browser.new_context(viewport={"width": 375, "height": 812})
        page = ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(base)
        page.wait_for_function("typeof POOL !== 'undefined' && POOL.length > 0",
                               timeout=20000)
        deal = page.evaluate(DEAL_PROBE)
        cycles, days = deal["cycles"], deal["days"]
        check(deal["again"] == days[7],
              "the same day deals the same four entries every time",
              f"{deal['again']} vs {days[7]}")
        check(all(len(set(d)) == len(d) for d in days),
              "no day ever deals the same entry twice")
        # The property that matters: within one pass through a round's pool
        # every entry appears exactly once. That is what "no repeats" means
        # here -- not a long gap, but a permutation.
        for slot, n in enumerate(cycles):
            seq = [d[slot] for d in days[:n]]
            check(len(set(seq)) == n,
                  f"round {slot + 1} deals its whole pool without repeating",
                  f"{len(set(seq))} distinct in a {n}-day cycle")
            nxt = [d[slot] for d in days[n:n * 2]]
            check(len(set(nxt)) == n and set(nxt) == set(seq),
                  f"round {slot + 1} starts the pool again on the next pass",
                  f"{len(set(nxt))} distinct")
            check(nxt[:min(20, n)] != seq[:min(20, n)],
                  f"round {slot + 1} deals the second pass in a different order")
        # Every entry the dataset carries has to get a day, or the pool is
        # decoration. The bonus round was drawn from tier 1 alone, which left
        # 356 of 653 living traditions -- the least famous, the most fragile --
        # unreachable for ever.
        span = max(cycles)
        seen = {x for d in days[:span] for x in d}
        check(len(seen) >= deal["pool"] - 1,
              "every entry in the pool is dealt within one full cycle",
              f"{len(seen)} of {deal['pool']} entries in {span} days")
        check(not errs, "and dealing throws nothing", "; ".join(errs[:2]))
        ctx.close()

        # ---- the clock ----
        # The countdown ran to the next UTC midnight while the puzzle turns
        # over at the player's own, so it was wrong for almost everyone: in
        # Paris it hit zero at 02:00 and then showed nothing for 22 hours.
        print("\n== the clock ==")
        for tz, city in (("Europe/Paris", "Paris"), ("America/New_York", "New York"),
                         ("Australia/Sydney", "Sydney")):
            ctx = browser.new_context(viewport={"width": 375, "height": 812},
                                      timezone_id=tz)
            pg = ctx.new_page()
            pg.goto(base)
            pg.wait_for_function("typeof POOL !== 'undefined' && POOL.length > 0",
                                 timeout=20000)
            pg.wait_for_timeout(250)
            shown = pg.locator("#countdown").inner_text()
            left = pg.evaluate(CLOCK_PROBE)
            check(bool(shown.strip()), f"{city}: the countdown says something", shown)
            hh, mm = (shown.split()[-1].split(":") + ["0", "0"])[:2]
            claimed = int(hh) * 60 + int(mm)
            check(abs(claimed - left) <= 2,
                  f"{city}: and counts to that city's midnight, not UTC's",
                  f"shows {claimed} min, {left} min to local midnight")
            ctx.close()

        # A tab left open across midnight kept serving yesterday's puzzle to a
        # board that looked current. The clock is moved to just before local
        # midnight and the page left to cross it.
        ctx = browser.new_context(viewport={"width": 375, "height": 812},
                                  timezone_id="Europe/Paris")
        pg = ctx.new_page()
        pg.add_init_script(NEAR_MIDNIGHT)
        pg.goto(base)
        pg.wait_for_function("typeof POOL !== 'undefined' && POOL.length > 0",
                             timeout=20000)
        before = pg.locator("#countdown").inner_text()
        check(":" in before, "a tab open near midnight is still counting down", before)
        pg.wait_for_timeout(27000)
        check(pg.locator("#newDayBtn").count() == 1,
              "and when the day turns it offers the new one rather than going blank",
              pg.locator("#countdown").inner_text())
        # It must not reload under a player who may be mid-round: the offer is
        # a button, and the old board is still there until it is taken.
        check(pg.evaluate("typeof targets !== 'undefined' && targets.length > 0"),
              "without pulling the board out from under them")
        ctx.close()

        # ---- a day, once dealt, stays dealt ----
        # The deal is a function of the dataset, and the dataset moves: tiers
        # are rank tertiles of sitelink counts and the deal walks a permutation
        # of each pool, so regenerating it re-deals days that were already
        # played. A puzzle could change under a player mid-round, and every
        # past day replayed as something that never happened.
        print("\n== a day stays dealt ==")
        ctx = browser.new_context(viewport={"width": 375, "height": 812})
        page = ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(base)
        page.wait_for_function("typeof POOL !== 'undefined' && POOL.length > 0",
                               timeout=20000)
        page.wait_for_timeout(200)
        first = page.evaluate("targets.map(e => e.id)")
        check(page.evaluate("(state.ids || []).length") == len(first),
              "the day's four entries are written into its save", str(first))
        # Now do to the pool exactly what regenerating the dataset does: change
        # what is in it, and re-deal.
        moved = page.evaluate("""
          () => {
            const before = targets.map(e => e.id);
            // What regenerating the dataset actually does: new entries, and
            // sitelink counts that move entries between fame tiers.
            POOL.forEach((e, i) => { e.tier = (i % 3) + 1; });
            computeTargets();
            const retiered = targets.map(e => e.id);

            // And the harder case: an entry leaves the pool altogether,
            // because the map cannot answer its country any more.
            const lost = before[1];
            POOL = POOL.filter(e => e.id !== lost);
            computeTargets();
            const afterLoss = targets.map(e => e.id);

            // What the day would have been dealt without any of this.
            const ids = state.ids; state.ids = null;
            const rec = profile.days[dayIndex]; profile.days[dayIndex] = null;
            const redealt = dealFor(dayIndex).map(e => e.id);
            state.ids = ids; profile.days[dayIndex] = rec;
            return { before, retiered, afterLoss, redealt, lost };
          }
        """)
        check(moved["retiered"] == moved["before"],
              "re-tiering the whole pool does not change a day already dealt",
              f"{moved['before']} -> {moved['retiered']}")
        check(moved["redealt"] != moved["before"],
              "and that shift really would have re-dealt it otherwise",
              str(moved["redealt"]))
        survivors = [i for i in range(4) if i != 1]
        check(all(moved["afterLoss"][i] == moved["before"][i] for i in survivors),
              "an entry leaving the pool costs only its own round",
              f"{moved['before']} -> {moved['afterLoss']}")
        check(moved["afterLoss"][1] != moved["lost"]
              and len(set(moved["afterLoss"])) == 4,
              "and that round is refilled with something else",
              str(moved["afterLoss"]))
        check(not errs, "and nothing throws while it happens", "; ".join(errs[:2]))
        ctx.close()

        # The daily save is per-day and can be cleared; the passport record is
        # what a replay months later has to lean on.
        ctx = browser.new_context(viewport={"width": 375, "height": 812},
                                  has_touch=True, is_mobile=True)
        page = ctx.new_page()
        play_day(page, base, None, 375, "freeze")
        played = page.evaluate("profile.days[dayIndex].ids")
        check(isinstance(played, list) and len(played) == 4,
              "a finished day records what was played in the passport", str(played))
        check(played == page.evaluate("targets.map(e => e.id)"),
              "and it is what was actually on the board")
        rebuilt = page.evaluate("""
          () => {
            state.ids = null;              // as if the daily save had expired
            computeTargets();
            return targets.map(e => e.id);
          }
        """)
        check(rebuilt == played,
              "so the day can be rebuilt from the passport alone", str(rebuilt))
        ctx.close()

        # ---- a collection that can leave this browser ----
        # It lives in one browser and nowhere else: clear the site data, change
        # phone, or leave it a fortnight on Safari, whose eviction does not care
        # how long the collection took, and a year of play is gone.
        print("\n== backup ==")
        ctx = browser.new_context(viewport={"width": 375, "height": 812},
                                  has_touch=True, is_mobile=True)
        page = ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        play_day(page, base, None, 375, "backup")
        made = page.evaluate(BACKUP_PROBE)
        check(made["bytes"] > 0, "a collection produces a code", f"{made['bytes']} chars")
        # Ids, not records: the dataset already holds the names, countries and
        # photographs, and a 600 KB code is not something anyone pastes.
        check(made["bytes"] < made["asRecords"] / 4,
              "and the code is small enough to send to yourself",
              f"{made['bytes']} chars vs {made['asRecords']} as records")
        page.evaluate("showView('Passport')")
        page.wait_for_timeout(300)
        check(page.locator("#backupCode").count() == 1,
              "the passport offers the code")
        check(len(page.input_value("#backupCode")) == made["bytes"],
              "with the code in it, ready to copy")
        # The hard part is the other end: a browser that has never seen any of
        # this.
        ctx2 = browser.new_context(viewport={"width": 375, "height": 812})
        fresh = ctx2.new_page()
        fresh.on("pageerror", lambda e: errs.append(str(e)))
        fresh.goto(base)
        fresh.wait_for_function("typeof POOL !== 'undefined' && POOL.length > 0",
                                timeout=20000)
        check(fresh.evaluate("Object.keys(profile.collection).length") == 0,
              "a fresh browser starts with nothing")
        out = fresh.evaluate("code => importProfile(code)", made["code"])
        check(bool(out) and out["entries"] == made["entries"],
              "and a pasted code brings the whole collection back",
              f"{out} against {made['entries']} entries")
        check(fresh.evaluate("profile.achievements.length") == made["ach"],
              "with the distinctions re-earned from it, not taken on trust",
              f"{fresh.evaluate('profile.achievements.length')} vs {made['ach']}")
        fresh.reload()
        fresh.wait_for_function("typeof POOL !== 'undefined' && POOL.length > 0",
                                timeout=20000)
        check(fresh.evaluate("Object.keys(profile.collection).length") == made["entries"],
              "and it is still there after a reload")
        # Merging, not replacing: a code from an old phone must never delete a
        # week of play on the new one.
        kept = fresh.evaluate(MERGE_PROBE, made["code"])
        check(kept["after"] == kept["before"] + 1,
              "restoring again keeps what this browser already had",
              f"{kept['before']} -> {kept['after']}")
        check(fresh.evaluate("importProfile('not a code')") is None,
              "a code that is not a code is refused")
        check(fresh.evaluate("importProfile('')") is None, "and so is an empty one")
        check(not errs, "and none of it throws", "; ".join(errs[:2]))
        ctx2.close()
        ctx.close()

        # ---- rank, date, and the secrets ----
        print("\n== distinctions ==")
        ctx = browser.new_context(viewport={"width": 375, "height": 812},
                                  has_touch=True, is_mobile=True)
        page = ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        play_day(page, base, None, 375, "awards")
        spread = page.evaluate(AWARD_PROBE)
        check(spread["unranked"] == [],
              "every distinction has a rank or is a secret", str(spread["unranked"]))
        check(spread["secrets"] >= 3,
              "there are several secrets, not one", str(spread["secrets"]))
        check(spread["ranks"]["prestige"] >= 3 and spread["ranks"]["common"] >= 3,
              "and the ranks are actually used", str(spread["ranks"]))
        page.evaluate("showView('Passport')")
        page.wait_for_timeout(350)
        tiles = page.locator("#viewPassport > .ach-grid > .ach-tile")
        earned = page.evaluate("profile.achievements.length")
        check(tiles.count() == earned, "the earned stamps are on the page",
              f"{tiles.count()} of {earned}")
        # A passport is a record of where you have been and when.
        dated = page.locator("#viewPassport > .ach-grid .ach-when").count()
        check(dated == earned, "each carries the date it was earned",
              f"{dated} of {earned}")
        order = page.evaluate("""
          () => [...document.querySelectorAll('#viewPassport > .ach-grid > .ach-tile')]
                  .map(t => profile.achievementsAt[t.dataset.ach] || 0)
        """)
        check(order == sorted(order, reverse=True),
              "newest first, so the passport reads chronologically", str(order[:4]))
        classes = page.evaluate("""
          () => [...document.querySelectorAll('#viewPassport > .ach-grid > .ach-tile')]
                  .map(t => (t.className.match(/r-\\w+/) || ['?'])[0])
        """)
        check(all(c != "?" for c in classes),
              "and every stamp is drawn in its rank", str(set(classes)))
        check(page.locator("#viewPassport .ach-tile.r-secret").count() >= 1,
              "a secret earned is drawn as a secret")
        tiles.first.click()
        page.wait_for_timeout(250)
        detail = page.locator("#viewPassport .ach-detail").inner_text()
        check(any(w in detail.upper() for w in ("SECRET", "PRESTIGE", "RARE", "COMMON",
                                                "SECRÈTE", "COURANTE", "COMÚN", "RARA")),
              "and says its rank when tapped", detail.replace("\n", " | "))
        check(not errs, "and none of it throws", "; ".join(errs[:2]))
        ctx.close()

        # ---- the archive shows what a day was ----
        # Closing the back catalogue took the replay away, which was right, and
        # also took away any way of finding out what a missed day even was.
        print("\n== the archive ==")
        ctx = browser.new_context(viewport={"width": 375, "height": 812},
                                  has_touch=True, is_mobile=True)
        page = ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(base)
        page.wait_for_function("typeof POOL !== 'undefined' && POOL.length > 0",
                               timeout=20000)
        page.evaluate("document.getElementById('fnClose')?.click()")
        page.evaluate("showView('Archive')")
        page.wait_for_timeout(350)
        peeks = page.locator("#viewArchive [data-arch-day]")
        if page.evaluate("todayIndex") > 0:
            check(peeks.count() >= 1, "a past day can be looked up",
                  str(peeks.count()))
            before = page.evaluate("Object.keys(profile.collection).length")
            peeks.first.click()
            page.wait_for_timeout(400)
            names = page.locator("#viewArchive .arch-entry-text b").all_inner_texts()
            check(len(names) == 4, "and shows all four entries of that day", str(names))
            check(all(n.strip() for n in names), "each one named", str(names))
            check(page.locator("#viewArchive .arch-note").count() == 1,
                  "with it said plainly that looking is not collecting")
            # The whole point of the compromise.
            check(page.evaluate("Object.keys(profile.collection).length") == before,
                  "and nothing is catalogued by looking",
                  f"{before} -> {page.evaluate('Object.keys(profile.collection).length')}")
            page.locator("#viewArchive .arch-entry").first.click()
            page.wait_for_timeout(300)
            check("open" in (page.locator("#modalBackdrop").get_attribute("class") or ""),
                  "an entry from the archive opens")
            check(page.evaluate("Object.keys(profile.collection).length") == before,
                  "and opening it does not catalogue it either")
            check(page.evaluate("profile.achievements.length") == 0,
                  "nor does it earn anything",
                  str(page.evaluate("profile.achievements")))
        else:
            print("  ---- launch day: no past day to look up yet")
        check(page.evaluate(
                "() => !document.querySelector(`[data-arch-day='${todayIndex}']`)"),
              "today is never revealed in the archive")
        check(not errs, "and the archive throws nothing", "; ".join(errs[:2]))
        ctx.close()

        # ---- the pages at the foot ----
        # A site that asks nothing of anyone still has to say so somewhere, in
        # every language it speaks.
        print("\n== terms, privacy, questions ==")
        ctx = browser.new_context(viewport={"width": 375, "height": 812})
        page = ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(base)
        page.wait_for_function("typeof POOL !== 'undefined' && POOL.length > 0",
                               timeout=20000)
        page.evaluate("document.getElementById('fnClose')?.click()")
        page.wait_for_timeout(250)
        foot = page.locator("#siteFoot")
        check(foot.count() == 1, "the page has a foot")
        # On every view, not only Today: inside the game view it showed on one
        # of the four, and on a wide screen it was auto-placed into the board's
        # own grid, in a column beside the guess counter.
        for view in ("Game", "Collection", "Passport", "Archive"):
            page.evaluate("v => showView(v)", view)
            page.wait_for_timeout(200)
            box = page.evaluate("""
              () => {
                const f = document.getElementById('siteFoot').getBoundingClientRect();
                const p = document.querySelector('.page').getBoundingClientRect();
                return { h: f.height, w: Math.round(f.width), page: Math.round(p.width) };
              }
            """)
            check(box["h"] > 0 and abs(box["w"] - box["page"]) < 2,
                  f"and it is at the foot of {view}, the width of the page",
                  f"{box['w']} of {box['page']}")
        page.evaluate("showView('Game')")
        page.wait_for_timeout(200)
        check(page.locator("#siteFoot [data-doc]").count() == 3,
              "with the three documents on it",
              str(page.locator("#siteFoot [data-doc]").all_inner_texts()))
        check(page.locator('#siteFoot a[href^="mailto:"]').count() == 1,
              "and somewhere to write to")
        # The credit line is not decoration: the photographs are other
        # people's work under their own licences.
        credit = foot.inner_text()
        for owed in ("Wikidata", "Commons", "Natural Earth"):
            check(owed in credit, f"the foot credits {owed}", credit[:90])
        seen = {}
        for code in ("en", "fr", "es"):
            page.evaluate("c => { lang = c; render(); }", code)
            page.wait_for_timeout(200)
            for doc in ("faq", "privacy", "terms"):
                page.locator(f"#siteFoot [data-doc={doc}]").click()
                page.wait_for_timeout(180)
                title = page.locator("#aboutTitle").inner_text().strip()
                text = page.locator("#aboutBody").inner_text().strip()
                heads = page.locator("#aboutBody .doc-head").count()
                check(bool(title) and heads >= 5 and len(text) > 600,
                      f"{code} {doc}: written, not stubbed",
                      f"{heads} sections, {len(text)} chars")
                seen[(code, doc)] = text
                page.keyboard.press("Escape")
                page.wait_for_timeout(120)
        # Each language its own text, not the English one showing through.
        for doc in ("faq", "privacy", "terms"):
            check(len({seen[(c, doc)] for c in ("en", "fr", "es")}) == 3,
                  f"{doc} is written three times over, not once and reused")
        # The claims in there have to be true of this build, or the privacy
        # page is a lie: no analytics, no cookies, no third party but the ones
        # it names.
        hosts = page.evaluate("""
          () => [...new Set(performance.getEntriesByType('resource')
                   .map(r => new URL(r.name).host))].sort()
        """)
        outside = [h for h in hosts if "127.0.0.1" not in h and "localhost" not in h]
        check(all(("wikimedia" in h or "wikipedia" in h or "gstatic" in h
                   or "googleapis" in h) for h in outside),
              "the page contacts nobody the privacy page does not name", str(outside))
        check(page.evaluate("document.cookie") == "",
              "and sets no cookies", page.evaluate("document.cookie"))
        check(not errs, "and none of the documents throw", "; ".join(errs[:2]))
        ctx.close()

        # ---- the board is in the order it is read ----
        # Naming grid rows for the photograph and the map while leaving the
        # pips and the score badges to auto-placement put them *after* the
        # board on a wide screen -- below the fold, on the live site, for four
        # days. Auto-placement fills the first free row, and rows 1 and 2 were
        # spoken for.
        print("\n== reading order ==")
        for width, wide in ((390, False), (1280, True)):
            ctx = browser.new_context(viewport={"width": width, "height": 900})
            page = ctx.new_page()
            page.goto(base)
            page.wait_for_function("typeof POOL !== 'undefined' && POOL.length > 0",
                                   timeout=20000)
            page.evaluate("document.getElementById('fnClose')?.click()")
            page.wait_for_timeout(300)
            box = page.evaluate(ORDER_PROBE)
            tag = f"{width}px"
            check(box["rounds"]["top"] < box["photo"]["top"],
                  f"{tag}: the round pips are above the board",
                  f"{box['rounds']['top']} vs {box['photo']['top']}")
            check(box["meta"]["top"] < box["photo"]["top"],
                  f"{tag}: and so is the score",
                  f"{box['meta']['top']} vs {box['photo']['top']}")
            check(box["clues"]["top"] >= box["photo"]["top"],
                  f"{tag}: the clues come after it")
            if wide:
                check(box["map"]["left"] > box["photo"]["left"] + box["photo"]["w"] - 5,
                      f"{tag}: photograph and map sit side by side",
                      f"photo ends {box['photo']['left'] + box['photo']['w']}, "
                      f"map starts {box['map']['left']}")
                check(box["guess"]["left"] >= box["map"]["left"] - 5,
                      f"{tag}: and the prompt to tap is under the map")
            else:
                check(box["map"]["top"] > box["photo"]["top"],
                      f"{tag}: photograph above map, in one column")
            check(page.evaluate("document.documentElement.scrollWidth")
                  <= width + 1, f"{tag}: nothing pushes the page sideways")
            ctx.close()

        # ---- winning something is an event ----
        print("\n== announcements ==")
        ctx = browser.new_context(viewport={"width": 375, "height": 812})
        page = ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(base)
        page.wait_for_function("typeof POOL !== 'undefined' && POOL.length > 0",
                               timeout=20000)
        page.evaluate("document.getElementById('fnClose')?.click()")
        page.wait_for_timeout(200)
        page.evaluate("() => { POOL.slice(0, 12).forEach(e => catalogue(e, true)); "
                      "checkAchievements(); }")
        page.wait_for_timeout(500)
        card = page.locator(".award-card")
        check(card.count() == 1, "winning a distinction says so on the spot",
              str(card.count()))
        said = card.first.inner_text()
        # Named through achText: the collection ladder and the continents are
        # named by tier, not by id, so reading T.ach[id] skipped most of them
        # and announced nothing at all.
        check(len(said.strip()) > 20 and "undefined" not in said,
              "and names what was won", said.replace("\n", " / "))
        check(card.first.locator(".stamp-mark").count() == 1,
              "with the stamp on it")
        check(bool(page.evaluate(
                "() => (document.querySelector('.award-card').className.match(/r-\\w+/)||[])[0]")),
              "drawn in the rank that was won")
        # Several can land together; they queue rather than stack up the screen.
        page.evaluate("() => { POOL.slice(0, 120).forEach(e => catalogue(e, true)); "
                      "checkAchievements(); }")
        page.wait_for_timeout(300)
        check(page.locator(".award-card").count() == 1,
              "and several at once arrive one at a time",
              str(page.locator(".award-card").count()))
        # Restoring a backup re-earns in bulk: twenty announcements would be a
        # punishment for restoring.
        quiet = page.evaluate("""
          () => {
            document.querySelectorAll('.award-card').forEach(e => e.remove());
            const code = exportProfile();
            profile.achievements = []; profile.achievementsAt = {};
            importProfile(code);
            return document.querySelectorAll('.award-card').length;
          }
        """)
        check(quiet == 0, "restoring a backup does not parade them", str(quiet))
        # ---- the stamp row stays a row ----
        page.evaluate("""
          () => {
            for(let i = 0; i < 9; i++)
              profile.days[dayIndex - i] = { score: 100, ids: [],
                statuses: ['solved','solved','solved','failed'], at: Date.now() };
            saveProfile(); showView('Passport'); renderPassport();
          }
        """)
        page.wait_for_timeout(300)
        shown = page.locator("#viewPassport .stamps .stamp").count()
        check(shown == 5, "the passport shows five days of stamps, not every day",
              str(shown))
        check(page.locator(".stamps-more").count() == 1,
              "and says how many more there are",
              page.locator(".stamps-more").inner_text()
              if page.locator(".stamps-more").count() else "-")
        check(not errs, "and none of it throws", "; ".join(errs[:2]))
        ctx.close()

        # ---- a missed day can be practised ----
        # Closing the back catalogue stopped anyone farming a collection out of
        # it. Practice gives the puzzle back without giving the credit.
        print("\n== practising the archive ==")
        ctx = browser.new_context(viewport={"width": 375, "height": 812})
        page = ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(base)
        page.wait_for_function("typeof POOL !== 'undefined' && POOL.length > 0",
                               timeout=20000)
        today = page.evaluate("todayIndex")
        if today >= 1:
            page.goto(f"{base}?day={today - 1}&practice=1")
            page.wait_for_function("typeof POOL !== 'undefined' && POOL.length > 0",
                                   timeout=20000)
            page.wait_for_timeout(300)
            check(page.evaluate("dayIndex") == today - 1,
                  "a day nobody played can still be opened",
                  str(page.evaluate("dayIndex")))
            check(page.evaluate("isPractice"), "and it is practice")
            page.evaluate("document.getElementById('fnClose')?.click()")
            page.evaluate("submitGuess(targetCountry())")
            page.wait_for_timeout(400)
            check(page.evaluate("state.roundStatus[0]") == "solved",
                  "it plays like the game it is")
            check(page.evaluate("Object.keys(profile.collection).length") == 0,
                  "but nothing it shows is catalogued",
                  str(page.evaluate("Object.keys(profile.collection).length")))
            check(not page.evaluate("!!profile.days[dayIndex]"),
                  "and no score is recorded for it")
            check(page.evaluate("profile.achievements.length") == 0,
                  "so it cannot be farmed for distinctions")
            # Tomorrow is not an archive.
            page.goto(f"{base}?day={today + 3}")
            page.wait_for_function("typeof POOL !== 'undefined' && POOL.length > 0",
                                   timeout=20000)
            check(page.evaluate("dayIndex") == page.evaluate("todayIndex"),
                  "a day that has not happened yet lands on today",
                  str(page.evaluate("dayIndex")))
        else:
            print("  ---- launch day: no past day to practise yet")
        check(not errs, "and practising throws nothing", "; ".join(errs[:2]))
        ctx.close()

        # ---- storage that fights back ----
        # Three ways the game meets a browser it cannot save to, all of which
        # used to be fatal: the state read and write had no guard at all, and
        # they run at the top level and from inside submitGuess.
        print("\n== hostile storage ==")

        def storage_case(name, init_script, expect_remembers):
            ctx = browser.new_context(viewport={"width": 375, "height": 812},
                                      has_touch=True, is_mobile=True)
            pg = ctx.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.add_init_script(init_script)
            pg.goto(base)
            try:
                pg.wait_for_function(
                    "typeof POOL !== 'undefined' && POOL.length > 0", timeout=20000)
                loaded = True
            except Exception:
                loaded = False
            check(loaded, f"{name}: the game still loads")
            if loaded:
                pg.evaluate("document.getElementById('fnClose')?.click()")
                pg.wait_for_timeout(200)
                # The board has to be playable, not merely present: a throw
                # inside submitGuess left the guess unrendered and the game
                # looked like it had stopped responding.
                tap_guess(pg, "COUNTRIES.find(c => c.names.en !== targets[0].country.en)")
                pg.wait_for_timeout(400)
                check(pg.evaluate("state.guesses[0].length") == 1,
                      f"{name}: a guess is accepted",
                      str(pg.evaluate("state.guesses[0].length")))
                check(pg.locator(".hist-row").count() == 1,
                      f"{name}: and the board redraws around it")
                check(pg.locator("#mapReadout .lg-verdict").count() == 1,
                      f"{name}: and the verdict is shown")
                if expect_remembers is None:
                    # The planted generation is a literal, so a bump to
                    # STORAGE_GEN would disarm these cases in silence: the
                    # page's own first-load sweep would delete the blob before
                    # the read under test.
                    check(pg.evaluate("STORAGE_GEN") == "4",
                          f"{name}: the planted generation still matches the game's",
                          str(pg.evaluate("STORAGE_GEN")))
                if expect_remembers is False:
                    # Nothing is written, which is the honest outcome; what
                    # matters is that the game does not pretend otherwise by
                    # falling over.
                    pg.reload()
                    pg.wait_for_function(
                        "typeof POOL !== 'undefined' && POOL.length > 0", timeout=20000)
                    check(pg.evaluate("state.guesses[0].length") == 0,
                          f"{name}: it simply does not remember, and says nothing")
            check(not errs, f"{name}: and nothing throws", "; ".join(errs[:2]))
            ctx.close()

        # 1. A blob that will not parse -- a tab killed mid-write, or a player
        #    who edited it. JSON.parse threw at the top level: blank page, and
        #    unrecoverable without devtools.
        storage_case("corrupt save", """
          (() => {
            const day = Math.floor((Date.UTC(new Date().getFullYear(),
                                             new Date().getMonth(),
                                             new Date().getDate())
                                    - Date.UTC(2026, 8, 11)) / 86400000);
            // A returning player, or the sweep clears the blob before the
            // read that is under test ever happens.
            localStorage.setItem('heritle-gen', '4');
            localStorage.setItem('heritle-' + day, '{"round":0,"guesses":[[');
            localStorage.setItem('heritle-profile', 'not json at all');
          })();
        """, None)

        # 2. A blob that parses but is the wrong shape. Every render walks
        #    these arrays.
        storage_case("nonsense save", """
          (() => {
            const day = Math.floor((Date.UTC(new Date().getFullYear(),
                                             new Date().getMonth(),
                                             new Date().getDate())
                                    - Date.UTC(2026, 8, 11)) / 86400000);
            localStorage.setItem('heritle-gen', '4');
            localStorage.setItem('heritle-' + day,
              JSON.stringify({ round: 'x', guesses: 7, roundStatus: null,
                               roundScore: ['a'] }));
          })();
        """, None)

        # 3. Storage that throws on every call, which is private browsing with
        #    a zero quota, a full quota, and some extensions.
        storage_case("storage throws", """
          (() => {
            const boom = () => { throw new DOMException('QuotaExceededError'); };
            Object.defineProperty(window, 'localStorage', {
              configurable: true,
              get: () => ({ getItem: boom, setItem: boom, removeItem: boom,
                            key: boom, clear: boom, length: 0 })
            });
          })();
        """, False)

        browser.close()

    if httpd:
        httpd.shutdown()
    if root:
        shutil.rmtree(root, ignore_errors=True)

    print("\n" + ("SMOKE PASSED" if not FAILS else f"{len(FAILS)} FAILED: {FAILS[:6]}"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
