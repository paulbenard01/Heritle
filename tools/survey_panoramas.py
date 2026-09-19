#!/usr/bin/env python3
"""How many heritage sites actually have a usable 360 panorama on Commons?

The question that decides whether Heritle 3D becomes Heritle 360, and whether
it can reach two hundred places rather than twenty. Answered by asking, not by
recollection.

The trick that makes this measurable: an equirectangular panorama -- the format
every 360 viewer reads -- is always **exactly twice as wide as it is tall**.
That is a property of the projection, not a convention someone might have
skipped, so it identifies panoramas far more reliably than Commons' category
tree, where a 360 of Petra might sit under any of a dozen parent categories or
none. Width and height come back from the same imageinfo call the dataset
pipeline already makes.

    python tools/survey_panoramas.py --sample 60
    python tools/survey_panoramas.py --names "Petra,Taj Mahal"

Reports, per site: whether a panorama exists, its size, its resolution and its
licence. Then the totals that matter -- hit rate, licence split, and what two
hundred of them would weigh.
"""
import argparse
import json
import os
import random
import sys
import time
import urllib.parse
import urllib.request

API = "https://commons.wikimedia.org/w/api.php"

# 2:1, with a little slack for a stitcher that rounded a pixel.
RATIO_LO, RATIO_HI = 1.97, 2.03
MIN_WIDTH = 3000            # below this a 360 is too soft to look at
UA = "heritle-panorama-survey (https://heritle.org)"

REFUSE = ("noncommercial", "nonderiv", "noderiv")


def api(params):
    params = dict(params, format="json", formatversion="2")
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as fh:
        return json.load(fh)


def panoramas_for(name, limit=40):
    """Every 2:1 image Commons offers for this name, largest first."""
    try:
        data = api({
            "action": "query",
            "generator": "search",
            "gsrsearch": f'{name} filetype:bitmap',
            "gsrnamespace": "6",          # File:
            "gsrlimit": str(limit),
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
        })
    except Exception as exc:                        # noqa: BLE001
        print(f"    ! search failed: {exc}", file=sys.stderr)
        return []

    out = []
    for page in (data.get("query", {}) or {}).get("pages", []) or []:
        info = (page.get("imageinfo") or [None])[0]
        if not info:
            continue
        w, h = info.get("width") or 0, info.get("height") or 0
        if not h or w < MIN_WIDTH:
            continue
        if not (RATIO_LO <= w / h <= RATIO_HI):
            continue
        meta = info.get("extmetadata") or {}
        lic = (meta.get("LicenseShortName") or {}).get("value", "?")
        author = (meta.get("Artist") or {}).get("value", "")
        # Commons puts HTML in Artist; the tags are noise in a report.
        for tag in ("<", ">"):
            if tag in author:
                author = " ".join(author.split("<")[0].split())
        out.append({
            "title": page.get("title", ""),
            "w": w, "h": h,
            "bytes": info.get("size") or 0,
            "licence": lic,
            "author": author[:38],
            "url": info.get("descriptionurl") or info.get("url"),
        })
    out.sort(key=lambda p: -p["w"])
    return out


def usable(p):
    low = (p["licence"] or "").lower()
    return not any(w in low for w in REFUSE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="data/dataset.json")
    ap.add_argument("--sample", type=int, default=40)
    ap.add_argument("--names", default="", help="comma-separated, instead of a sample")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    if args.names:
        names = [n.strip() for n in args.names.split(",") if n.strip()]
    else:
        if not os.path.exists(args.dataset):
            print(f"no {args.dataset}", file=sys.stderr)
            return 1
        with open(args.dataset, encoding="utf-8") as fh:
            entries = json.load(fh)["entries"]
        # Sites only, and spread across fame tiers: a survey of famous places
        # alone would flatter the answer, and the pool is mostly not famous.
        sites = [e for e in entries if e.get("type") == "material"]
        random.Random(args.seed).shuffle(sites)
        by_tier = {1: [], 2: [], 3: []}
        for e in sites:
            t = e.get("tier")
            if t in by_tier and len(by_tier[t]) < args.sample // 3 + 1:
                by_tier[t].append(e)
        names = [e["names"]["en"] for t in (1, 2, 3) for e in by_tier[t]][:args.sample]
        tiers = {e["names"]["en"]: e["tier"] for t in (1, 2, 3) for e in by_tier[t]}

    hits, total_bytes, licences = 0, 0, {}
    print(f"surveying {len(names)} sites\n")
    for name in names:
        pans = panoramas_for(name)
        ok = [p for p in pans if usable(p)]
        tier = f"t{tiers[name]}" if not args.names else "  "
        if ok:
            hits += 1
            best = ok[0]
            total_bytes += best["bytes"]
            licences[best["licence"]] = licences.get(best["licence"], 0) + 1
            print(f"  {tier} {name[:44]:<44} {len(ok):>2} pano  "
                  f"{best['w']}x{best['h']}  {best['bytes']/1_000_000:>5.1f} MB  "
                  f"{best['licence'][:18]}")
        else:
            print(f"  {tier} {name[:44]:<44}  — none"
                  + (f" ({len(pans)} found, all unusable)" if pans else ""))
        time.sleep(0.3)

    print(f"\n=== {hits} of {len(names)} sites have a usable 360 panorama "
          f"({hits * 100 // max(1, len(names))}%) ===")
    if hits:
        avg = total_bytes / hits / 1_000_000
        print(f"  average original: {avg:.1f} MB")
        print(f"  200 sites at that rate: {avg * 200:.0f} MB raw, "
              f"roughly {avg * 200 * 0.08:.0f} MB once resized to 4096x2048 WebP")
        print("  licences:")
        for lic, n in sorted(licences.items(), key=lambda kv: -kv[1]):
            print(f"    {n:>3}  {lic}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
