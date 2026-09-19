#!/usr/bin/env python3
"""How many heritage sites have a 360 panorama on Mapillary?

Commons holds heritage photographs, not heritage 360s: a survey of fourteen
famous sites found one unambiguous equirectangular panorama, and several near
misses that were only wide or cropped photographs landing near 2:1 by accident.
Mapillary is street-level imagery built for this, and it answers a much better
question.

**Relevance here is geometric, not textual.** Every survey before this one
searched by name and then tried to judge whether a result was really about the
place -- which went wrong three times, most memorably when every site in a
twenty-site run returned the same 1.3 GB picture of the Milky Way. Mapillary is
queried by bounding box, and the dataset already carries coordinates for all
1,872 entries, so "is this image of Petra" becomes "is this image within 150
metres of Petra". That is a fact about the image, not a guess about a search
engine.

Before any filtering, --schema prints what a response actually contains. That
habit is the direct result of writing three filters against fields that were
not there.

    python tools/survey_mapillary.py --schema
    python tools/survey_mapillary.py --sample 45

Needs MAPILLARY_TOKEN in the environment: Mapillary's *access token*, the one
beginning MLY|. Not the client secret, which is for signing users in, and not
the authorisation URL.

Licence caution, to settle before anything ships: Mapillary imagery is
CC-BY-SA, but Mapillary's own API terms place conditions on bulk download and
redistribution that a CC licence alone does not answer. Read them before the
first image is cached, not after.
"""
import argparse
import json
import math
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

GRAPH = "https://graph.mapillary.com/images"
RADIUS_M = 150          # a box this big around a site is still that site
# Lean on purpose. The coverage survey asked for geometry, compass_angle and
# creator as well, and Speyer Cathedral reported one panorama; asking for
# id,is_pano alone at the same radius and limit found twenty. Mapillary meters
# the *amount of data* in a response, so a fat field set quietly returns fewer
# rows -- which made the coverage figure a lower bound rather than a count.
# Nothing here needs more than whether each image is a sphere.
FIELDS = "id,is_pano"
PER_SITE = 50


def bbox(lat, lng, metres=RADIUS_M):
    """A box of about this many metres around a point.

    A degree of latitude is ~111 km everywhere; a degree of longitude shrinks
    with the cosine of the latitude, which matters for a site in Svalbard and
    not at all for one in Kenya. Cheap to do properly, so do it properly.
    """
    dlat = metres / 111_000.0
    dlng = metres / (111_000.0 * max(0.05, math.cos(math.radians(lat))))
    return f"{lng - dlng},{lat - dlat},{lng + dlng},{lat + dlat}"


class ApiError(Exception):
    """Carries what the server said, not just the status line.

    A bare "HTTP Error 500" is the least useful thing a client can report: the
    body normally names the offending parameter. Throwing it away turns a
    two-minute fix into guesswork.
    """


def fetch(token, lat, lng, limit=PER_SITE, fields=FIELDS, metres=RADIUS_M):
    params = {"access_token": token, "fields": fields,
              "bbox": bbox(lat, lng, metres), "limit": str(limit)}
    url = GRAPH + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "heritle-survey"})
    try:
        with urllib.request.urlopen(req, timeout=60) as fh:
            return json.load(fh)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", "replace")[:400]
        except Exception:                           # noqa: BLE001
            body = "(no body)"
        # The token is in the query string, so the URL never gets printed.
        raise ApiError(f"HTTP {exc.code}: {body}") from None


TOO_MUCH = "reduce the amount of data"


def fetch_adaptive(token, lat, lng, limit=PER_SITE, fields=FIELDS,
                   metres=RADIUS_M):
    """Fetch, shrinking the box when Mapillary says the ask is too big.

    A 150 m box over Trafalgar Square is refused outright -- "please reduce the
    amount of data you're asking for" -- even for a single id, because the
    square is one of the most photographed places on earth. Heritage sites in
    dense cities (Notre-Dame, the Colosseum) will hit the same wall, so the
    right response is to narrow the box rather than to give up on the site.

    Returns the data and the radius that actually worked, because a hit found
    at 25 m is a different claim from one found at 150 m.
    """
    tried = []
    for m in (metres, metres // 2, metres // 4, 25):
        m = max(15, int(m))
        if m in tried:
            continue
        tried.append(m)
        try:
            return fetch(token, lat, lng, limit, fields, m), m
        except ApiError as exc:
            if TOO_MUCH not in str(exc):
                raise
    raise ApiError(f"too dense even at {tried[-1]} m")


def dump_schema(token):
    """What a response really looks like, before anything is filtered on it.

    Fields are added one at a time. Mapillary answers an unknown or
    wrongly-shaped field with a 500 rather than a 400, so the only way to find
    which one it dislikes is to walk up from a request that certainly works.
    """
    # Two hardcoded probe locations have now broken a run: Trafalgar Square
    # was too dense to answer at all, and the Eiffel Tower returned nothing
    # within 150 m. So no single guess -- walk a list until one answers, and
    # start with places this survey has already seen imagery at.
    spots = [("Røros", 62.5747, 11.3842), ("Grand-Bassam", 5.1961, -3.7381),
             ("Pienza", 43.0786, 11.6792), ("Speyer", 49.3174, 8.4421),
             ("central Paris", 48.8566, 2.3522), ("Eiffel Tower", 48.8584, 2.2945)]
    lat, lng = spots[0][1], spots[0][2]
    probes = ["id", "id,is_pano", "id,is_pano,geometry",
              "id,is_pano,geometry,captured_at",
              "id,is_pano,geometry,captured_at,compass_angle",
              "id,is_pano,geometry,captured_at,compass_angle,thumb_2048_url",
              FIELDS]
    good = None
    print("--- which fields the API accepts ---")
    for fields in probes:
        try:
            _, used = fetch_adaptive(token, lat, lng, limit=1, fields=fields)
            good = fields
            print(f"  ok    {fields}   (at {used} m)")
        except ApiError as exc:
            print(f"  FAILS {fields}")
            print(f"        {exc}")
            break
        except Exception as exc:                    # noqa: BLE001
            print(f"  FAILS {fields}  ({exc})")
            break
        time.sleep(0.3)
    if not good:
        print("\n  even the id-only request failed. That is the token or the"
              " bbox, not a field.", file=sys.stderr)
        return 1
    print(f"\n  widest working field set: {good}\n")

    items, where, used = [], None, 0
    for label, la, ln in spots:
        try:
            data, used = fetch_adaptive(token, la, ln, limit=3, fields=good)
        except Exception as exc:                    # noqa: BLE001
            print(f"  {label}: {str(exc)[:60]}")
            continue
        items = data.get("data") or []
        if items:
            where = label
            break
        print(f"  {label}: no images within {used} m")
        time.sleep(0.3)
    if not items:
        # Diagnostic, not a gate. Saying so and carrying on beats blocking the
        # measurement this run exists to make.
        print("  no probe location returned images; carrying on anyway")
        return 0
    print(f"--- {len(items)} images within {used} m of {where} ---")
    for k, v in sorted(items[0].items()):
        flat = (repr(v)[:90] if isinstance(v, (str, int, float, bool, type(None)))
                else json.dumps(v)[:90])
        print(f"  {k:18} {flat}")
    print(f"\n  is_pano across the {len(items)}: "
          f"{[i.get('is_pano') for i in items]}")
    return 0


# Sites the 45-site survey found panoramas at. Measuring resolution anywhere
# else would mean measuring nothing.
KNOWN_HITS = ["Rjukan", "Grand-Bassam", "Røros", "Pienza", "Speyer"]

# Candidates for "how big is it". Probed rather than assumed, and then checked
# against the real file anyway.
SIZE_FIELDS = ["width", "height", "thumb_original_url", "thumb_2048_url",
               "thumb_1024_url"]


def measure(url, timeout=90):
    """Download and measure. The only answer that cannot be wrong.

    Every field in this survey so far has been either absent, differently
    named or differently shaped from what was assumed, so the resolution
    question gets settled by opening the image rather than by reading a
    number beside it.
    """
    from PIL import Image
    import io as _io
    req = urllib.request.Request(url, headers={"User-Agent": "heritle-survey"})
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        blob = fh.read()
    im = Image.open(_io.BytesIO(blob))
    return im.width, im.height, len(blob)


def resolutions(token, dataset):
    """What the panoramas at the known hits are actually worth looking at."""
    with open(dataset, encoding="utf-8") as fh:
        entries = json.load(fh)["entries"]

    # Which size fields the API will give us, established the same careful way.
    base = "id,is_pano"
    good = base
    for extra in SIZE_FIELDS:
        trial = good + "," + extra
        try:
            fetch_adaptive(token, 48.8584, 2.2945, limit=1, fields=trial)
            good = trial
            print(f"  field ok      {extra}")
        except Exception:                           # noqa: BLE001
            print(f"  field refused {extra}")
        time.sleep(0.3)
    print(f"\n  using: {good}\n")

    shown = 0
    for needle in KNOWN_HITS:
        site = next((e for e in entries
                     if needle.lower() in e["names"]["en"].lower()), None)
        if not site:
            print(f"  {needle}: not in the dataset")
            continue
        try:
            data, used = fetch_adaptive(token, site["lat"], site["lng"],
                                        limit=50, fields=good)
        except Exception as exc:                    # noqa: BLE001
            print(f"  {needle}: {str(exc)[:60]}")
            continue
        panos = [i for i in (data.get("data") or []) if i.get("is_pano")]
        print(f"  {site['names']['en'][:40]:<40} {len(panos)} panoramas "
              f"within {used} m")
        if panos and not shown:
            print(f"    every field on one of them:")
            for k, v in sorted(panos[0].items()):
                flat = (repr(v)[:70] if isinstance(v, (str, int, float, bool, type(None)))
                        else json.dumps(v)[:70])
                print(f"      {k:20} {flat}")
            shown = 1
        for pano in panos[:2]:
            url = (pano.get("thumb_original_url") or pano.get("thumb_2048_url")
                   or pano.get("thumb_1024_url"))
            if not url:
                print("      (no thumbnail url returned)")
                continue
            try:
                w, h, n = measure(url)
            except Exception as exc:                # noqa: BLE001
                print(f"      measure failed: {str(exc)[:50]}")
                continue
            ratio = w / h if h else 0
            verdict = ("equirectangular" if 1.97 <= ratio <= 2.03
                       else f"ratio {ratio:.2f}, not 2:1")
            print(f"      measured {w}x{h}  {n/1_000_000:.1f} MB  {verdict}")
        time.sleep(0.4)
    return 0


CONTINENTS = {"EU": "Europe", "AS": "Asia", "AF": "Africa",
              "NA": "North America", "SA": "South America", "OC": "Oceania"}


def by_continent(token, dataset, per, radius, seed):
    """Hit rate per continent, which is the question spread actually asks.

    The fame-tier survey said 11% overall, but an overall rate hides whether
    that 11% is evenly spread or is Europe carrying the whole number. Two
    hundred places chosen by what happens to have coverage is a different game
    from two hundred chosen to look like the world, and the difference is
    measurable rather than arguable.
    """
    with open(dataset, encoding="utf-8") as fh:
        entries = json.load(fh)["entries"]
    sites = [e for e in entries
             if e.get("type") == "material" and e.get("lat") is not None]
    random.Random(seed).shuffle(sites)

    buckets = {c: [] for c in CONTINENTS}
    for e in sites:
        c = e.get("continent")
        if c in buckets and len(buckets[c]) < per:
            buckets[c].append(e)

    print(f"{per} sites per continent, {radius} m around each\n")
    totals = {}
    for code, label in CONTINENTS.items():
        group = buckets[code]
        if not group:
            print(f"  {label:<15} no sites in the pool")
            continue
        hits, panos = 0, 0
        for e in group:
            try:
                data, _ = fetch_adaptive(token, e["lat"], e["lng"],
                                         limit=PER_SITE, metres=radius)
            except Exception:                       # noqa: BLE001
                time.sleep(0.3)
                continue
            found = [i for i in (data.get("data") or []) if i.get("is_pano")]
            if found:
                hits += 1
                panos += len(found)
                print(f"    {label[:2]}  {e['names']['en'][:46]:<46} "
                      f"{len(found):>3} 360s")
            time.sleep(0.35)
        totals[label] = (hits, len(group), panos)
        print(f"  {label:<15} {hits:>2} of {len(group):<3} "
              f"({hits * 100 // max(1, len(group)):>3}%)  {panos} panoramas\n")

    print("=== spread ===")
    for label, (hits, n, panos) in sorted(totals.items(),
                                          key=lambda kv: -kv[1][0] / max(1, kv[1][1])):
        bar = "#" * (hits * 20 // max(1, n))
        print(f"  {label:<15} {hits:>2}/{n:<3} {bar}")
    got = sum(h for h, _, _ in totals.values())
    tot = sum(n for _, n, _ in totals.values())
    print(f"\n  overall {got} of {tot} ({got * 100 // max(1, tot)}%)")
    print("\n  A pool chosen for spread needs the low rows to carry their share.")
    print("  Where a row is thin, Commons and Poly Haven have to fill it.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="data/dataset.json")
    ap.add_argument("--sample", type=int, default=45)
    ap.add_argument("--radius", type=int, default=RADIUS_M)
    ap.add_argument("--schema", action="store_true")
    ap.add_argument("--by-continent", action="store_true",
                    help="hit rate per continent rather than per fame tier")
    ap.add_argument("--per", type=int, default=14,
                    help="sites per continent for --by-continent")
    ap.add_argument("--resolution", action="store_true",
                    help="measure the real pixel size of panoramas at the "
                         "sites the survey found them")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    token = os.environ.get("MAPILLARY_TOKEN", "").strip()
    if not token:
        print("MAPILLARY_TOKEN is not set. It is the access token beginning "
              "MLY|, not the client secret.", file=sys.stderr)
        return 2
    if not token.startswith("MLY"):
        print("warning: a Mapillary access token normally begins 'MLY|'. "
              "If this is the client secret, the survey will return nothing.",
              file=sys.stderr)

    if args.schema:
        return dump_schema(token)
    if args.resolution:
        return resolutions(token, args.dataset)
    if args.by_continent:
        return by_continent(token, args.dataset, args.per, args.radius, args.seed)

    with open(args.dataset, encoding="utf-8") as fh:
        entries = json.load(fh)["entries"]
    sites = [e for e in entries
             if e.get("type") == "material" and e.get("lat") is not None]
    random.Random(args.seed).shuffle(sites)
    # Across fame tiers: a survey of famous places alone flatters the answer,
    # and the pool is mostly not famous.
    by_tier = {1: [], 2: [], 3: []}
    for e in sites:
        t = e.get("tier")
        if t in by_tier and len(by_tier[t]) < args.sample // 3 + 1:
            by_tier[t].append(e)
    chosen = [e for t in (1, 2, 3) for e in by_tier[t]][:args.sample]

    with_any, with_pano, panos_total, approx = 0, 0, 0, 0
    print(f"surveying {len(chosen)} sites, {args.radius} m around each\n")
    for e in chosen:
        name = e["names"]["en"]
        try:
            data, used = fetch_adaptive(token, e["lat"], e["lng"],
                                        limit=PER_SITE, metres=args.radius)
        except Exception as exc:                    # noqa: BLE001
            print(f"  t{e['tier']} {name[:42]:<42}  ! {str(exc)[:46]}")
            time.sleep(0.4)
            continue
        items = data.get("data") or []
        panos = [i for i in items if i.get("is_pano")]
        if items:
            with_any += 1
        if panos:
            with_pano += 1
            panos_total += len(panos)
        # An approximate coordinate means the box may not be over the site at
        # all, so those results prove less. The dataset flags them.
        if e.get("approx"):
            approx += 1
        flag = " ~" if e.get("approx") else "  "
        narrowed = f"  ({used} m)" if used != args.radius else ""
        print(f"  t{e['tier']}{flag}{name[:42]:<42} "
              f"{len(items):>3} images  {len(panos):>3} are 360{narrowed}")
        time.sleep(0.4)

    n = len(chosen)
    print(f"\n=== {with_pano} of {n} sites have at least one 360 "
          f"({with_pano * 100 // max(1, n)}%) ===")
    print(f"  any street-level imagery at all: {with_any} of {n}")
    print(f"  360s found in total: {panos_total}")
    print(f"  sites whose coordinate is approximate: {approx}"
          " (their boxes may not sit over the site)")
    if with_pano:
        print(f"  extrapolated: {with_pano * 1872 // max(1, n)} of the 1,872 "
              "entries might have one")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
