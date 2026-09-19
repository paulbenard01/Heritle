# Heritle 3D — candidate models, and why each was picked

**Nobody has looked at these yet, including me.** Every pick below rests on
measurable signals only — licence, triangle count, texture resolution and
count, download weight, Sketchfab's own staff-pick curation, and the author's
provenance where it is recognisable. Not one of them has been opened in a
viewer. A model can pass every check here and still be a crude approximation of
the monument, and that is the one thing no filter catches.

So this is a shortlist, not a decision. The next step is a person opening the
links and looking.

Produced by `tools/shortlist_models.py` via the `Shortlist 3D models` workflow,
19 September 2026. Sketchfab search only; Smithsonian Open Access 3D, Europeana
3D and Wikimedia Commons have not been searched yet and are the fallback for
the gaps at the bottom.

## What was filtered out, and why

Licence first: **CC0 and CC-BY only**. Share-alike would bind the game;
non-commercial and no-derivatives both forbid exactly what the pipeline does to
the file. That alone removed most of the heritage scans on Sketchfab — a great
many are NonCommercial-ShareAlike.

Then: at least 40,000 triangles (below that it is decoration, not a scan),
textured, textures at 1024 px or better, and downloadable.

Ranked by staff-pick first, then likes, then triangle count.

## The picks

Links are `https://sketchfab.com/3d-models/none-<uid>`.

| Monument | Author | Faces | Textures | Raw | Why this one |
|---|---|---|---|---|---|
| Stonehenge | megalitharchive | 989,302 | 8192px ×1 | 80.6 MB | A specialist megalith archive — the best provenance in the set |
| Colosseum | local.yany | 1,022,400 | 4096px ×29 | 58.4 MB | 29 separate textures: a real multi-texture scan, not one baked atlas |
| Leaning Tower of Pisa | Brian Trepanier | 1,413,726 | 8192px ×1 | 217.2 MB | Highest detail available; the laser-scan alternative is NC-SA |
| Sagrada Família | Giravolt | 184,032 | 8192px ×3 | 40.0 MB | Barcelona heritage-scanning studio, working on its own doorstep |
| Eiffel Tower | Ro_mulus | 48,684 | 4096px ×3 | 51.6 MB | **Staff pick**, 346 likes — the strongest external endorsement here |
| Mont-Saint-Michel | Giorgio Scioldo | 5,749,999 | 8192px ×6 | 345.4 MB | By far the densest model found anywhere in the list |
| Notre-Dame de Paris | jjull | 256,963 | 2048px ×12 | 46.0 MB | 12 textures, 142 likes |
| Hagia Sophia | ilhanseyfeddin | 491,662 | 2048px ×1 | 19.0 MB | Weakest field of the 25 — one texture, 8 likes |
| Neuschwanstein | Brian Trepanier | 1,501,423 | 8192px ×1 | 233.2 MB | Detail; a 41k-face alternative has more likes but far less substance |
| Statue of Liberty | Maurice Svay | 699,072 | 4096px ×1 | 31.0 MB | **Staff pick**, and light for its detail |
| Christ the Redeemer | Brian Trepanier | 1,499,207 | 8192px ×1 | 229.1 MB | Best of a thin field |
| Machu Picchu | CMPLab | 723,342 | 4096px ×1 | 51.2 MB | Laboratory provenance |
| Mesa Verde | John Toeppen | 2,000,000 | 8192px ×1 | 113.1 MB | The only candidate that passed at all |
| Tikal | Brian Trepanier | 1,104,397 | 2048px ×1 | 38.4 MB | One of only two that passed |
| Great Sphinx of Giza | The Watt Institution | 1,487,624 | 8192px ×3 | 95.0 MB | A museum, scanning to museum standards |
| Petra (Al-Khazneh) | ThomasNicodeme Studio | 200,932 | 8192px ×1 | 25.6 MB | The only candidate that passed |
| Taj Mahal | THE CUBE GUY | 315,896 | 2048px ×55 | 40.1 MB | 55 textures — the most thoroughly textured model in the list |
| Angkor Wat | 333DDD | 379,354 | 8192px ×1 | 36.5 MB | See the note below: the CC0 alternatives are museum objects, not the temple |
| Borobudur | Arnadi Murtiyoso | 200,000 | 4096px ×1 | 13.3 MB | A published photogrammetry researcher; light for its detail |
| Forbidden City | Artec 3D | 677,402 | 4096px ×1 | 26.1 MB | A professional scanner manufacturer's own capture |
| Bagan | CyArk | 1,500,000 | 8192px ×1 | 88.7 MB | **CyArk** — the heritage-scanning non-profit. The strongest provenance of all 25 |
| Sydney Opera House | Nick Reinhardt | 62,424 | 2048px ×23 | 27.4 MB | 23 textures, 133 likes; the 1M-face alternative is 187 MB |

## Three that need more work

**Chichen Itza** — nothing passed, from three results. Worth retrying as
"Kukulkan", "El Castillo Yucatan", or falling back to Smithsonian/Europeana.

**Great Wall of China** — nothing passed. Everything returned is under 40,000
faces; most are game props and one is a LEGO set. A named section
("Mutianyu", "Jinshanling", "Simatai") may do better than the whole wall,
which is not a single scannable object.

**Parthenon / Acropolis** — the search ran but its output fell outside the log
I could retrieve. Re-run it.

## One trap worth recording

Searching "Angkor Wat" returns several **CC0 models from the Cleveland Museum
of Art** with excellent numbers — 150,000 faces at 8192px, 182 likes. They are
museum objects *from* Angkor (Naga finials, a Naga-enthroned Buddha), not the
temple. They would sail through every automated check and be completely wrong
for a game that asks where a building is. The same pattern shows up under
"Borobudur" (ship reliefs) and "Forbidden City" (a lion censer).

This is exactly the judgement the filter cannot make, and the reason this file
says shortlist rather than selection.

## Weight

The raw downloads above total roughly **1.9 GB**. Every one goes through
`tools/process_model.py` before it goes anywhere near a repository: prune,
dedup, textures to 2048 px and WebP, decimate, Draco. The budget is 1–3 MB per
model, and the pipeline refuses anything over 3 MB or anything still carrying
the monument's name in its mesh names.

## Acknowledgement

Every model that ships is CC-BY or CC0, and CC-BY makes attribution a
condition, not a courtesy. The reveal screen already carries the author, the
licence and a link to the source for each monument, and the per-file log in
`README.md` in this directory records the same alongside the download date.
