#!/usr/bin/env python3
"""Search Sketchfab for usable scans of a monument and print a shortlist.

Searching a famous monument returns a great deal of low-poly fan art, voxel
builds and game props alongside the genuine photogrammetry, and trawling that
for two dozen monuments is a long evening. This does the filtering a machine
can do and leaves the judgement it cannot: whether the thing actually looks
like the monument.

Written against the fields the API really returns, printed by --schema, after a
first version filtered on `license.slug` and `textureCount` -- neither of which
exists -- and rejected every candidate for all twenty-five monuments. A filter
that cannot pass is the same mistake as a test that cannot fail.

What is actually there:
    license          {"uid": ..., "label": "CC Attribution"}   <- label, not slug
    archives.glb     {"size": ..., "textureCount": ..., "textureMaxResolution": ...}
    staffpickedAt    Sketchfab's own curation, when present
    faceCount, vertexCount, likeCount, viewCount, user, viewerUrl

Search needs no credentials. Downloading does, so this prints links to open.

    python tools/shortlist_models.py "Petra Al-Khazneh"
    python tools/shortlist_models.py "Stonehenge" --schema
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request

API = "https://api.sketchfab.com/v3/search"

# Only these two can ship. Share-alike would bind the game; non-commercial and
# no-derivatives both forbid exactly what the pipeline does to the file. The
# API gives a human label rather than a slug, so the test is on the words --
# and note that "CC Attribution-ShareAlike" contains "CC Attribution", which is
# why the refusals are checked first.
REFUSE = ("noncommercial", "noderiv", "sharealike")
ACCEPT = ("cc0", "public domain", "cc attribution")

MIN_FACES = 40_000          # below this it is decoration, not a scan
MIN_TEXTURE = 1024          # an untextured or low-textured scan reads as clay


def search(query, limit=24):
    params = {
        "type": "models",
        "q": query,
        "downloadable": "true",
        "count": str(limit),
        "sort_by": "-likeCount",
    }
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "heritle-shortlist"})
    with urllib.request.urlopen(req, timeout=60) as fh:
        return json.load(fh).get("results", [])


def glb(model):
    return ((model.get("archives") or {}).get("glb") or {})


def licence(model):
    return ((model.get("license") or {}).get("label") or "").strip()


def licence_ok(model):
    low = licence(model).lower()
    if not low:
        return False
    if any(word in low for word in REFUSE):
        return False
    return any(word in low for word in ACCEPT)


def assess(model, min_faces):
    """Why this one is, or is not, worth opening."""
    notes = []
    if not licence_ok(model):
        notes.append(licence(model) or "no licence given")
    if (model.get("faceCount") or 0) < min_faces:
        notes.append(f"{model.get('faceCount') or 0:,} faces")
    if not model.get("isDownloadable"):
        notes.append("not downloadable")
    a = glb(model)
    if not a:
        notes.append("no glb")
    else:
        if not (a.get("textureCount") or 0):
            notes.append("untextured")
        elif (a.get("textureMaxResolution") or 0) < MIN_TEXTURE:
            notes.append(f"{a.get('textureMaxResolution')}px textures")
    return notes


def quality(model):
    """Rank what survives. Staff picks first -- Sketchfab curates those, and it
    is the only external judgement of quality available without looking."""
    return (1 if model.get("staffpickedAt") else 0,
            model.get("likeCount") or 0,
            model.get("faceCount") or 0)


def dump_schema(query):
    results = search(query, 3)
    if not results:
        print("  no results to inspect")
        return
    print(f"--- fields on a search result, {query!r} ---")
    for k in sorted(results[0].keys()):
        v = results[0][k]
        flat = (repr(v)[:88] if isinstance(v, (str, int, float, bool, type(None)))
                else json.dumps(v)[:88])
        print(f"  {k:22} {flat}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="+")
    ap.add_argument("--schema", action="store_true",
                    help="print the fields the API returns, and stop")
    ap.add_argument("--min-faces", type=int, default=MIN_FACES)
    ap.add_argument("--limit", type=int, default=24)
    args = ap.parse_args()

    query = " ".join(args.query)
    if args.schema:
        dump_schema(query)
        return 0
    try:
        results = search(query, args.limit)
    except Exception as exc:                       # noqa: BLE001
        print(f"search failed for {query!r}: {exc}", file=sys.stderr)
        return 1

    keep, reject = [], []
    for m in results:
        (reject if assess(m, args.min_faces) else keep).append(m)
    keep.sort(key=quality, reverse=True)

    print(f"\n=== {query} — {len(results)} results, {len(keep)} worth opening ===")
    if not keep:
        print("  nothing passes. Try another phrasing, or fall back to")
        print("  Smithsonian Open Access 3D / Europeana 3D / Commons.")
    for m in keep:
        a = glb(m)
        mb = (a.get("size") or 0) / 1_000_000
        user = (m.get("user") or {}).get("displayName") or "?"
        # The evidence for the pick, printed next to it, because "this one is
        # good" is not a reason anyone can check.
        print(f"  {'STAFF PICK  ' if m.get('staffpickedAt') else '            '}"
              f"{m.get('faceCount') or 0:>9,} faces  "
              f"{a.get('textureMaxResolution') or 0:>5}px x{a.get('textureCount') or 0}  "
              f"{mb:>6.1f} MB raw  {m.get('likeCount') or 0:>5} likes")
        print(f"    {licence(m)}  by {user}")
        print(f"    {m.get('viewerUrl') or m.get('uri')}")
    if reject:
        print(f"  --- {len(reject)} set aside ---")
        for m in reject[:10]:
            print(f"    {(m.get('name') or '')[:40]:<40} "
                  f"{'; '.join(assess(m, args.min_faces))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
