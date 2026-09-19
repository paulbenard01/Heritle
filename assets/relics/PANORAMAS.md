# 360 panoramas: what the sources actually hold

Measured 19 September 2026, against the real dataset, by
`tools/survey_mapillary.py` and `tools/survey_panoramas.py`.

## Mapillary — 45 sites, spread across fame tiers

| | |
|---|---|
| At least one 360 within 150 m | **5 of 45 (11%)** |
| Any street-level imagery at all | 22 of 45 (49%) |
| Panoramas found in total | 34 |
| Extrapolated to the whole pool | ~208 of 1,872 entries |

## The finding that matters: coverage is street-shaped

The five hits were not scattered. They were **Rjukan–Notodden (12 panoramas),
Grand-Bassam (13), Røros (5), Pienza (3), Speyer Cathedral (1)** — and four of
the five are inhabited historic *towns*, not single monuments.

That is what street-level imagery is. Someone drives or walks a route with a
360 rig, so a historic town centre gets dozens and a temple on a hill gets
none. The zeroes are the tell: Konark Sun Temple, Tsodilo, Mount Kumgang,
Jiuzhaigou Valley, the Rice Terraces of the Philippine Cordilleras, Lake
Turkana, Djenné, the Sacred Mijikenda Kaya Forests — nothing at all.

So 200 places is reachable in principle, but the 200 you would reach are
biased towards **European historic town centres**. Four of the five hits here
were European. A game built on this pool would ask the player to place a
cobbled street in Norway rather more often than it asked about Angkor.

Only 11% have a 360 while 49% have *some* imagery, which says most Mapillary
contributions are flat phone and dashcam frames rather than spherical rigs.

## Wikimedia Commons — thin, and easy to overcount

A 2:1 aspect ratio is how an equirectangular panorama is recognised, and it is
**necessary but not sufficient**: plenty of wide or cropped photographs land
near 2:1 by accident. Of six apparent hits across fourteen famous sites, only
the Colosseum's was unambiguously a 360 — a CC0 HDRI by Greg Zaal and Rico
Cilliers via Poly Haven. One was a church in **Cusco**, not Barcelona.

The definitive test is the GPano XMP tag (`ProjectionType=equirectangular`),
not the shape. That has not been implemented yet.

## Not usable

**Google Street View** — the terms forbid downloading and self-hosting. Worth
recording so nobody spends a week discovering it.

## Open questions before committing to this

1. **Resolution.** Nothing here measured how large the Mapillary panoramas are.
   A dashcam sphere from 2014 is not worth looking at.
2. **Mapillary's API terms.** The imagery is CC-BY-SA, but Mapillary's own
   terms place conditions on bulk download and redistribution that a Creative
   Commons licence does not settle. To be read before the first image is
   cached.
3. **Whether a street-biased pool is the game you want.** This is the real
   question, and it is not a technical one.
