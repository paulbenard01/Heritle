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

# Words that carry no identifying weight, so a title matching only these is not
# a match at all.
STOP = {"the", "of", "and", "national", "park", "historic", "centre", "center",
        "city", "town", "old", "site", "sites", "cathedral", "church", "castle",
        "palace", "temple", "monastery", "area", "region", "valley", "island",
        "islands", "great", "new", "saint", "st", "de", "la", "le", "du", "des"}


def keywords(name):
    """The distinctive words in a site's name."""
    cleaned = "".join(c if c.isalnum() or c.isspace() else " " for c in name.lower())
    return [w for w in cleaned.split() if len(w) > 3 and w not in STOP]


def about(title, name):
    """Is this file actually about this site?

    Search relevance cannot be trusted for this. Adding an OR clause for
    panorama words made every site in a twenty-site survey return the same
    1.3 GB image, because the clause let the site's name stop constraining the
    query -- the survey was measuring the largest panoramas on Commons rather
    than the ones belonging to each place. So relevance is verified here rather
    than assumed: a distinctive word of the name has to appear in the file's
    own title.
    """
    keys = keywords(name)
    if not keys:
        return True                     # nothing distinctive to test against
    low = title.lower()
    return any(k in low for k in keys)


def api(params):
    params = dict(params, format="json", formatversion="2")
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as fh:
        return json.load(fh)


def _search(query, limit):
    return api({
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": "6",          # File:
        "gsrlimit": str(limit),
        "prop": "imageinfo",
        "iiprop": "url|size|extmetadata",
    })


def panoramas_for(name, limit=50):
    """Every 2:1 image Commons offers for this name, largest first.

    Two queries, unioned. Commons sorts by relevance, so for a cathedral with
    three thousand photographs a panorama may simply not appear in the first
    fifty results of a plain name search -- which would make a survey of the
    plain query measure Commons' ranking rather than its holdings. The second
    query asks for panoramas by name.
    """
    pages, seen = [], set()
    for query in (f'{name} (360 OR panorama OR equirectangular OR spherical)',
                  f'{name} filetype:bitmap'):
        try:
            data = _search(query, limit)
        except Exception as exc:                    # noqa: BLE001
            print(f"    ! search failed: {exc}", file=sys.stderr)
            continue
        for page in (data.get("query", {}) or {}).get("pages", []) or []:
            if page.get("title") in seen:
                continue
            seen.add(page.get("title"))
            page["_for"] = name
            pages.append(page)
        time.sleep(0.2)
    data = {"query": {"pages": pages}}

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
        if not about(page.get("title", ""), page.get("_for", "")):
            continue
        out.append({
            "title": page.get("title", ""),
            "w": w, "h": h,
            "bytes": info.get("size") or 0,
            "licence": lic,
            "author": author[:38],
            "url": info.get("descriptionurl") or info.get("url"),
            "file": info.get("url") or "",
        })
    out.sort(key=lambda p: -p["w"])
    return out


def usable(p):
    low = (p["licence"] or "").lower()
    return not any(w in low for w in REFUSE)


# --- the projection test, finally implemented ------------------------------
#
# A 2:1 aspect ratio is necessary and nowhere near sufficient. It matched a
# church in Cusco for "Sagrada Familia" and a cropped wide photograph for
# "Angkor Wat", and a survey built on it counts panoramas that are not
# panoramas. The real test is the GPano XMP tag the stitcher writes into the
# file, so this reads the file.
#
# Only the head of it. XMP lives in an APP1 segment near the start of a JPEG,
# so 128 KB of an 80 MB image answers the question -- which is what makes
# checking every candidate affordable rather than a download of the whole of
# Commons.

XMP_HEAD = 131_072
PANO_MARKS = (b"GPano:ProjectionType", b"equirectangular",
              b"UsePanoramaViewer", b"FullPanoWidthPixels")


def projection_ok(url, timeout=45):
    """Does the file itself say it is a sphere?

    Returns True, False, or None when the question could not be put -- which
    is a third answer, not a no. Counting an unreachable file as "not a
    panorama" would quietly turn a network problem into a finding.
    """
    if not url:
        return None
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Range": f"bytes=0-{XMP_HEAD - 1}",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            head = fh.read(XMP_HEAD)
    except Exception:                                   # noqa: BLE001
        return None
    low = head.lower()
    return any(m.lower() in low for m in PANO_MARKS)


CONTINENTS = {"EU": "Europe", "AS": "Asia", "AF": "Africa",
              "NA": "North America", "SA": "South America", "OC": "Oceania"}

POLY_HAVEN = "https://api.polyhaven.com/assets?t=hdris"


class Catalogue(dict):
    """A name index that also knows how common each word in it is."""

    freq = {}

    def count_tokens(self):
        self.freq = {}
        for label in self:
            for tok in set(label.replace("_", " ").replace("-", " ").split()):
                self.freq[tok] = self.freq.get(tok, 0) + 1
        return self.freq


def poly_haven_index():
    """Poly Haven's whole HDRI catalogue, as {lowercased name: slug}.

    CC0, no key, and small enough to hold in memory. Worth asking because its
    HDRIs are genuine equirectangular spheres with no licence conditions at
    all -- but it is a library for lighting 3D renders, not a heritage
    archive, so the expectation is a handful of hits at most.
    """
    req = urllib.request.Request(POLY_HAVEN, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as fh:
            data = json.load(fh)
    except Exception as exc:                            # noqa: BLE001
        print(f"  ! Poly Haven unreachable: {exc}", file=sys.stderr)
        return {}
    out = Catalogue()
    for slug, asset in data.items():
        name = (asset.get("name") or slug).lower()
        out[name] = slug
        for tag in asset.get("tags") or []:
            out.setdefault(str(tag).lower(), slug)
    out.count_tokens()
    return out


def poly_haven_hit(name, index):
    """Does Poly Haven hold a sphere of *this place*?

    The first version of this matched on a substring of a single distinctive
    word and reported three hits, all of them false: "Museum Island" matched
    an air museum playground, "National History Park" matched a museum of
    history, and "K'gari" matched viale_giuseppe_GARIbaldi. Each one had been
    reduced to a single generic key first, because the stop list eats "island"
    and "national park".

    So: whole tokens, never substrings; every distinctive word must appear,
    not the first two; and a single short word is not enough on its own. The
    same mistake as the Sketchfab licence filter, and it deserves the same
    answer -- a filter that matches one generic word is not a filter.
    """
    keys = keywords(name)
    if not keys:
        return None
    for label, slug in index.items():
        tokens = set(label.replace("_", " ").replace("-", " ").split())
        if not all(k in tokens for k in keys):
            continue
        # A single word carries the whole match, so it has to be a word that
        # could only mean this place. Length does not say that -- "museum" and
        # "history" are both long and both generic. Rarity in the catalogue
        # does, and it is measured rather than guessed: a lone word has to be
        # unique in the catalogue. "stonehenge" appears once; "museum" and
        # "history" do not. Names like "National History Park" have no
        # distinctive word left after the stop list at all, and refusing them
        # is the right answer rather than a missed one.
        #
        # Still a heuristic. Poly Haven hits are few enough to eyeball, and
        # they should be.
        if len(keys) == 1 and index.freq.get(keys[0], 0) > 1:
            continue
        return slug
    return None


def by_continent(dataset, per, seed, verify):
    """Per-continent coverage, which is the only question left that matters.

    Mapillary is out: its terms require the Mapillary logo on any page that
    serves its images from its own servers, and that was refused. So these two
    sources are not filling gaps in a pool any more -- they are the pool, and
    this number is the pool's size.
    """
    with open(dataset, encoding="utf-8") as fh:
        entries = json.load(fh)["entries"]
    sites = [e for e in entries if e.get("type") == "material"]
    random.Random(seed).shuffle(sites)

    buckets = {c: [] for c in CONTINENTS}
    for e in sites:
        c = e.get("continent")
        if c in buckets and len(buckets[c]) < per:
            buckets[c].append(e)

    index = poly_haven_index()
    print(f"Poly Haven: {len(index)} catalogue keys\n")
    print(f"{per} sites per continent"
          + (", projection verified by reading each file" if verify else "")
          + "\n")

    totals, unverifiable = {}, 0
    for code, label in CONTINENTS.items():
        group = buckets[code]
        if not group:
            print(f"  {label:<15} no sites in the pool")
            continue
        hits = 0
        for e in group:
            name = e["names"]["en"]
            pans = [p for p in panoramas_for(name) if usable(p)]
            kept, unsure = [], 0
            for p in pans[:4]:
                if not verify:
                    kept.append(p)
                    continue
                ok = projection_ok(p["file"])
                if ok:
                    kept.append(p)
                elif ok is None:
                    unsure += 1
            unverifiable += unsure
            slug = poly_haven_hit(name, index)
            if kept or slug:
                hits += 1
                if kept:
                    best = kept[0]
                    print(f"    {code}  {name[:42]:<42} {best['w']}x{best['h']}"
                          f"  {best['bytes'] / 1_000_000:>5.1f} MB  "
                          f"{best['licence'][:16]}")
                if slug:
                    print(f"    {code}  {name[:42]:<42} Poly Haven CC0: {slug}")
            elif pans and not kept:
                # Worth printing: these are the ones 2:1 alone would have
                # counted, and the reason this survey reads the files.
                print(f"    {code}  {name[:42]:<42} "
                      f"{len(pans)} looked 2:1, none were spheres")
            time.sleep(0.25)
        totals[label] = (hits, len(group))
        print(f"  {label:<15} {hits:>2} of {len(group):<3} "
              f"({hits * 100 // max(1, len(group)):>3}%)\n")

    print("=== spread ===")
    reachable = 0
    pool = {"EU": 515, "AS": 332, "AF": 151, "NA": 112, "SA": 79, "OC": 28}
    for code, label in CONTINENTS.items():
        if label not in totals:
            continue
        hits, n = totals[label]
        rate = hits / max(1, n)
        est = int(rate * pool.get(code, 0))
        reachable += est
        print(f"  {label:<15} {hits:>2}/{n:<3} {'#' * (hits * 20 // max(1, n)):<20}"
              f" ~{est} of {pool.get(code, 0)} reachable")
    got = sum(h for h, _ in totals.values())
    tot = sum(n for _, n in totals.values())
    print(f"\n  overall {got} of {tot} ({got * 100 // max(1, tot)}%)"
          f"  ->  about {reachable} places in the whole pool")
    if unverifiable:
        print(f"  {unverifiable} candidates could not be read, so are counted "
              f"as neither yes nor no")
    thin = min((h / max(1, n) for h, n in totals.values()), default=0)
    print(f"\n  A pool balanced across continents is capped by the thinnest "
          f"row, at {thin * 100:.0f}%.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="data/dataset.json")
    ap.add_argument("--sample", type=int, default=40)
    ap.add_argument("--names", default="", help="comma-separated, instead of a sample")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--by-continent", action="store_true",
                    help="coverage per continent rather than per fame tier")
    ap.add_argument("--per", type=int, default=25,
                    help="sites per continent for --by-continent")
    ap.add_argument("--no-verify", action="store_true",
                    help="trust the 2:1 ratio instead of reading the files")
    ap.add_argument("--titles", action="store_true",
                    help="print every panorama found, not just the best")
    args = ap.parse_args()

    if args.by_continent:
        return by_continent(args.dataset, args.per, args.seed,
                            not args.no_verify)

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
            if args.titles:
                for p in ok[:4]:
                    print(f"        {p['title'][5:60]:<56} {p['w']}x{p['h']}"
                          f"  {p['bytes']/1_000_000:.1f} MB  {p['licence'][:16]}")
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
