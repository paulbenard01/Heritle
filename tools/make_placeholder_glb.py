#!/usr/bin/env python3
"""Write a tiny glTF 2.0 binary: one untextured box.

The Heritle 3D board needs a model to stand in for the real scans while the
guess -> reveal flow is being built, and downloading one would mean a licence to
track for an asset nobody is meant to keep. This one is generated, so it is our
own work, CC0, and about 800 bytes.

It is deliberately not a monument. A placeholder that looked like a building
would be mistaken for a real asset in a screenshot.

    python tools/make_placeholder_glb.py assets/relics/placeholder.glb
"""
import json
import os
import struct
import sys

# A unit box centred on the origin, sitting on y=0 so <model-viewer> frames it
# the way it frames a scanned monument.
POSITIONS = [
    (-0.5, 0.0, -0.5), (0.5, 0.0, -0.5), (0.5, 1.0, -0.5), (-0.5, 1.0, -0.5),
    (-0.5, 0.0,  0.5), (0.5, 0.0,  0.5), (0.5, 1.0,  0.5), (-0.5, 1.0,  0.5),
]
FACES = [
    (0, 1, 2), (0, 2, 3),      # back
    (4, 6, 5), (4, 7, 6),      # front
    (0, 4, 5), (0, 5, 1),      # bottom
    (3, 2, 6), (3, 6, 7),      # top
    (0, 3, 7), (0, 7, 4),      # left
    (1, 5, 6), (1, 6, 2),      # right
]


def pad(buf: bytes, fill: bytes) -> bytes:
    """glTF chunks are 4-byte aligned; JSON pads with spaces, BIN with zeros."""
    over = len(buf) % 4
    return buf if not over else buf + fill * (4 - over)


def build() -> bytes:
    idx = b"".join(struct.pack("<H", i) for f in FACES for i in f)
    idx = pad(idx, b"\x00")                      # keep POSITION 4-byte aligned
    pos = b"".join(struct.pack("<fff", *v) for v in POSITIONS)
    bin_chunk = idx + pos

    gltf = {
        "asset": {"version": "2.0", "generator": "heritle make_placeholder_glb"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        # A generic node name: nothing in the file may hint at what it stands
        # for, the same rule the real models are re-exported under.
        "nodes": [{"mesh": 0, "name": "node"}],
        "meshes": [{"name": "mesh", "primitives": [{"attributes": {"POSITION": 1},
                                                    "indices": 0, "material": 0}]}],
        "materials": [{"name": "mat", "pbrMetallicRoughness": {
            "baseColorFactor": [0.79, 0.64, 0.29, 1.0],
            "metallicFactor": 0.1, "roughnessFactor": 0.8}}],
        "accessors": [
            {"bufferView": 0, "componentType": 5123, "count": len(FACES) * 3,
             "type": "SCALAR"},
            {"bufferView": 1, "componentType": 5126, "count": len(POSITIONS),
             "type": "VEC3",
             "min": [min(v[i] for v in POSITIONS) for i in range(3)],
             "max": [max(v[i] for v in POSITIONS) for i in range(3)]},
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(idx), "target": 34963},
            {"buffer": 0, "byteOffset": len(idx), "byteLength": len(pos), "target": 34962},
        ],
        "buffers": [{"byteLength": len(bin_chunk)}],
    }

    js = pad(json.dumps(gltf, separators=(",", ":")).encode("utf-8"), b" ")
    total = 12 + 8 + len(js) + 8 + len(bin_chunk)
    out = struct.pack("<4sII", b"glTF", 2, total)
    out += struct.pack("<II", len(js), 0x4E4F534A) + js
    out += struct.pack("<II", len(bin_chunk), 0x004E4942) + bin_chunk
    return out


def main() -> int:
    dest = sys.argv[1] if len(sys.argv) > 1 else "assets/relics/placeholder.glb"
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    data = build()
    with open(dest, "wb") as fh:
        fh.write(data)
    print(f"{dest}: {len(data)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
