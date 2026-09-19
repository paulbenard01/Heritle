#!/usr/bin/env python3
"""Search Sketchfab for usable scans of a monument and print a shortlist.

Searching a famous monument on Sketchfab returns a great deal of low-poly fan
art, voxel builds and game props alongside the genuine photogrammetry, and
trawling that by hand for two dozen monuments is a long evening. This does the
filtering that a machine can do -- licence, downloadable, face count, textures,
provenance -- and leaves the judgement that it cannot: whether the thing
actually looks like the monument.

Search needs no credentials. Downloading does, so the shortlist gives you links
to open rather than files; see .github/workflows/process-models.yml for what to
do with one once you have picked it.

    python tools/shortlist_models.py "Petra Al-Khazneh" --min-faces 50000

Licences: CC0 and CC-BY only. Anything else cannot ship, however good it looks.
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request

API = "https://api.sketchfab.com/v3/search"
# Sketchfab's licence slugs. by = CC-BY, cc0 = public domain. The -sa, -nc and
# -nd variants are deliberately absent: share-alike would bind the game, and
# non-commercial and no-derivatives both forbid what this does to the file.
OK_LICENCES = {"cc0", "by"}
MIN_FACES = 40_000          # below this it is decoration, not a scan


def search(query, limit=24):
    params = {
        "type": "models",
        "q": query,
        "downloadable": "true",
        "archives_flavours": "false",
        "count": str(limit),
        "sort_by": "-likeCount",
    }
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "heritle-shortlist"})
    with urllib.request.urlopen(req, timeout=60) as fh:
        return json.load(fh).get("results", [])


def licence_slug(model):
    lic = model.get("license") or {}
    return (lic.get("slug") or "").lower()


def faces(model):
    return model.get("faceCount") or 0


def assess(model, min_faces):
    """Why this one is or is not worth opening."""
    notes = []
    slug = licence_slug(model)
    if slug not in OK_LICENCES:
        notes.append(f"licence {slug or '?'}")
    n = faces(model)
    if n < min_faces:
        notes.append(f"{n:,} faces")
    if not model.get("isDownloadable"):
        notes.append("not downloadable")
    # A scan carries textures; an untextured mesh of a monument is a model of
    # its shape only, which is a much weaker photograph to look at.
    if not (model.get("textureCount") or 0):
        notes.append("no textures")
    return notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="+")
    ap.add_argument("--min-faces", type=int, default=MIN_FACES)
    ap.add_argument("--limit", type=int, default=24)
    args = ap.parse_args()

    query = " ".join(args.query)
    try:
        results = search(query, args.limit)
    except Exception as exc:                       # noqa: BLE001
        print(f"search failed for {query!r}: {exc}", file=sys.stderr)
        return 1

    keep, reject = [], []
    for m in results:
        (reject if assess(m, args.min_faces) else keep).append(m)

    print(f"\n=== {query} — {len(results)} results, {len(keep)} worth opening ===")
    if not keep:
        print("  nothing passes. Try another phrasing, or fall back to")
        print("  Smithsonian Open Access 3D / Europeana 3D / Commons.")
    for m in keep:
        user = (m.get("user") or {}).get("displayName", "?")
        print(f"  {faces(m):>9,} faces  {licence_slug(m):<4}  {user[:22]:<22} "
              f"{(m.get('name') or '')[:40]}")
        print(f"             {m.get('viewerUrl') or m.get('uri')}")
    if reject:
        print(f"  --- {len(reject)} set aside ---")
        for m in reject[:8]:
            print(f"    {(m.get('name') or '')[:38]:<38} {'; '.join(assess(m, args.min_faces))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
