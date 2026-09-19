#!/usr/bin/env python3
"""Take a downloaded 3D model and make it small enough to ship, then say by how
much.

Heritle 3D serves its models from a static site with no backend, so the budget
is not GitHub's 100 MB ceiling: it is what a phone will download before the
player gives up, and what the repository can carry without its history doubling
every time a model is re-exported. The target is 1-3 MB.

This is a wrapper around gltf-transform, which does the actual work. It exists
so the chain is written down, identical for every model, and reported rather
than assumed -- the point is to know what each step bought.

Runs on a GitHub runner (see .github/workflows/process-models.yml); the
development sandbox can reach neither npm nor any model host.

    python tools/process_model.py raw/sphinx.glb assets/relics/relic-014.glb

Steps, in order:
  1. prune + dedup     drop unused nodes, materials, meshes; merge duplicates
  2. resize textures   2048 px is past what a 375 px board can show
  3. webp textures     usually the single biggest win on a photogrammetry scan
  4. simplify          decimate to a triangle budget, error-bounded
  5. draco             compress what geometry is left
  6. rename            generic mesh/node/material names, so the file names
                       nothing -- the anonymisation rule, enforced not trusted
"""
import argparse
import json
import os
import shutil
import struct
import subprocess
import sys

GLTF_TRANSFORM = "gltf-transform"
MAX_TEXTURE = 2048
TARGET_RATIO = 0.35          # keep ~35% of triangles; raise if it looks bad
SIMPLIFY_ERROR = 0.001       # gltf-transform's error bound, in scene units
BUDGET_MB = 3.0


def run(args, **kw):
    print("    $ " + " ".join(args))
    return subprocess.run(args, check=True, **kw)


def size_mb(path):
    return os.path.getsize(path) / 1_000_000


def inspect(path):
    """Triangle count and texture bytes, read out of the file itself."""
    try:
        out = subprocess.run([GLTF_TRANSFORM, "inspect", path],
                             capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}
    tris = None
    for line in out.splitlines():
        if "triangles" in line.lower():
            digits = "".join(c for c in line if c.isdigit())
            if digits:
                tris = int(digits)
                break
    return {"triangles": tris}


def anonymise(path):
    """Strip every name out of the glTF JSON chunk.

    A model re-exported from Sketchfab carries the uploader's mesh names, and
    those are very often the monument. The filename being relic-014.glb counts
    for nothing if the answer is sitting in the JSON a curious player can read
    straight out of the network tab.
    """
    with open(path, "rb") as fh:
        data = fh.read()
    magic, _version, _total = struct.unpack("<4sII", data[:12])
    if magic != b"glTF":
        print("    ! not a .glb, skipping the rename step")
        return 0
    jlen, jtype = struct.unpack("<II", data[12:20])
    if jtype != 0x4E4F534A:
        print("    ! first chunk is not JSON, skipping the rename step")
        return 0
    doc = json.loads(data[20:20 + jlen].decode("utf-8").rstrip())

    renamed = 0
    for key, stem in (("meshes", "mesh"), ("nodes", "node"),
                      ("materials", "mat"), ("images", "img"),
                      ("scenes", "scene"), ("animations", "anim")):
        for i, item in enumerate(doc.get(key, [])):
            if item.get("name") not in (None, f"{stem}{i}"):
                renamed += 1
            item["name"] = f"{stem}{i}"
    # The generator string names the exporter and sometimes the project.
    doc.setdefault("asset", {})["generator"] = "heritle"
    for extra in ("extras", "copyright"):
        doc.get("asset", {}).pop(extra, None)

    js = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)
    rest = data[20 + jlen:]
    out = struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + len(rest))
    out += struct.pack("<II", len(js), 0x4E4F534A) + js + rest
    with open(path, "wb") as fh:
        fh.write(out)
    return renamed


def leaks(path, words):
    """Does the finished file contain any of these words anywhere?"""
    with open(path, "rb") as fh:
        blob = fh.read().lower()
    return [w for w in words if w and len(w) > 3 and w.lower().encode() in blob]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dest")
    ap.add_argument("--ratio", type=float, default=TARGET_RATIO)
    ap.add_argument("--texture", type=int, default=MAX_TEXTURE)
    ap.add_argument("--forbid", default="",
                    help="comma-separated words that must not survive "
                         "(the monument's name and its aliases)")
    args = ap.parse_args()

    before = size_mb(args.src)
    before_tris = inspect(args.src).get("triangles")
    print(f"  in:  {args.src}  {before:.2f} MB"
          + (f", {before_tris:,} triangles" if before_tris else ""))

    os.makedirs(os.path.dirname(args.dest) or ".", exist_ok=True)
    work = args.dest + ".work.glb"
    shutil.copy(args.src, work)

    steps = [
        (["prune", work, work], "prune"),
        (["dedup", work, work], "dedup"),
        (["resize", work, work, "--width", str(args.texture),
          "--height", str(args.texture)], "resize textures"),
        (["webp", work, work, "--quality", "82"], "webp textures"),
        (["simplify", work, work, "--ratio", str(args.ratio),
          "--error", str(SIMPLIFY_ERROR)], "simplify"),
        (["draco", work, work], "draco"),
    ]
    for argv, label in steps:
        mb = size_mb(work)
        try:
            run([GLTF_TRANSFORM] + argv, stdout=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            # A scan with no textures has nothing to resize; that is not a
            # failure, and stopping here would lose the steps that did work.
            print(f"    - {label}: skipped (step reported an error)")
            continue
        print(f"    - {label}: {mb:.2f} -> {size_mb(work):.2f} MB")

    renamed = anonymise(work)
    print(f"    - rename: {renamed} names replaced")

    shutil.move(work, args.dest)
    after = size_mb(args.dest)
    after_tris = inspect(args.dest).get("triangles")

    print(f"  out: {args.dest}  {after:.2f} MB"
          + (f", {after_tris:,} triangles" if after_tris else ""))
    if before:
        print(f"  ratio: {after / before * 100:.1f}% of the original")

    bad = leaks(args.dest, [w.strip() for w in args.forbid.split(",")])
    if bad:
        print(f"  FAIL the finished file still contains: {', '.join(bad)}")
        return 1
    if args.forbid:
        print("  ok: the answer appears nowhere in the finished file")
    if after > BUDGET_MB:
        print(f"  FAIL {after:.2f} MB is over the {BUDGET_MB} MB budget."
              f" Lower --ratio or --texture and run it again.")
        return 1
    print(f"  ok: within the {BUDGET_MB} MB budget")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
