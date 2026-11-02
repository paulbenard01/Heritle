"""Build data/extras.json: what the game says about an entry beyond its name.

For every entry in data/dataset.json, two things from Wikidata:

  c  the World Heritage criteria it was inscribed under (P2614), as roman
     numerals -- ["i", "iv"]. Sites only; traditions are not inscribed under
     criteria.
  w  the title of its Wikipedia article in English, French and Spanish, read
     off the item's sitelinks. The game fetches the article's opening
     paragraph live, in the player's language, so only the title ships.

A separate file rather than new fields in dataset.json on purpose: the daily
deal is a function of dataset.json, and regenerating it reshuffles days that
have already been played. This can be rebuilt as often as Wikidata improves
without touching a single puzzle.

    python3 tools/build_extras.py
"""
import json
import os
import re
import sys
import time

import requests

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET = os.path.join(HERE, "data", "dataset.json")
OUT = os.path.join(HERE, "data", "extras.json")

ENDPOINT = "https://query.wikidata.org/sparql"
HEADERS = {
    "User-Agent": "Heritle/1.0 (https://heritle.org; paulbenard01@gmail.com)",
    "Accept": "application/sparql-results+json",
}
BATCH = 150
ROMAN = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"}

QUERY = """
SELECT ?item ?crit ?en ?fr ?es WHERE {
  VALUES ?item { %s }
  OPTIONAL { ?item wdt:P2614 ?c . ?c rdfs:label ?crit . FILTER(LANG(?crit) = "en") }
  OPTIONAL { ?a schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> ; schema:name ?en }
  OPTIONAL { ?b schema:about ?item ; schema:isPartOf <https://fr.wikipedia.org/> ; schema:name ?fr }
  OPTIONAL { ?d schema:about ?item ; schema:isPartOf <https://es.wikipedia.org/> ; schema:name ?es }
}
"""


def run(query):
    for attempt in range(6):
        r = requests.get(ENDPOINT, params={"query": query}, headers=HEADERS, timeout=120)
        if r.status_code == 200:
            return r.json()["results"]["bindings"]
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 ** attempt * 3)
            continue
        r.raise_for_status()
    raise RuntimeError("Wikidata kept refusing; try again later")


def main():
    entries = json.load(open(DATASET, encoding="utf-8"))["entries"]
    by_qid = {}
    for e in entries:
        if e.get("qid"):
            by_qid.setdefault(e["qid"], []).append(e)
    qids = sorted(by_qid)
    found = {}
    for i in range(0, len(qids), BATCH):
        chunk = qids[i:i + BATCH]
        rows = run(QUERY % " ".join("wd:" + q for q in chunk))
        for row in rows:
            q = row["item"]["value"].rsplit("/", 1)[1]
            rec = found.setdefault(q, {"c": set(), "w": {}})
            crit = row.get("crit", {}).get("value", "")
            m = re.fullmatch(r"\(?([ivx]+)\)?", crit.strip().lower())
            if m and m.group(1) in ROMAN:
                rec["c"].add(m.group(1))
            for lang in ("en", "fr", "es"):
                if lang in row:
                    rec["w"][lang] = row[lang]["value"]
        print(f"  {min(i + BATCH, len(qids))}/{len(qids)}", file=sys.stderr)
        time.sleep(1)

    order = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"]
    out = {}
    for e in entries:
        rec = found.get(e.get("qid"))
        if not rec:
            continue
        item = {}
        # Criteria are a property of inscribed sites; a tradition carrying one
        # would be a Wikidata error, not something to show.
        if e["type"] == "material" and rec["c"]:
            item["c"] = sorted(rec["c"], key=order.index)
        if rec["w"]:
            item["w"] = rec["w"]
        if item:
            out[e["id"]] = item

    sites = sum(1 for e in entries if e["type"] == "material")
    with_c = sum(1 for v in out.values() if "c" in v)
    with_w = {l: sum(1 for v in out.values() if l in v.get("w", {})) for l in ("en", "fr", "es")}
    meta = {"source": "Wikidata (CC0): P2614 and Wikipedia sitelinks",
            "built": time.strftime("%Y-%m-%d"),
            "criteria": f"{with_c} of {sites} sites",
            "articles": {l: f"{n} of {len(entries)}" for l, n in with_w.items()}}
    json.dump({"meta": meta, "entries": out}, open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
