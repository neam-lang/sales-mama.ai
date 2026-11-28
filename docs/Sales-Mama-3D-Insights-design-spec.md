# Sales Mama 3D Insights: Design Spec and Implementation Plan v1

> **Status:** proposed (2026-11-28). Spec only; nothing is built yet. Owner: manager.
> **Feature:** a panoramic 3D map of the Singapore market. Reps and the manager can orbit it, fly through it and question it by voice. Every answer becomes a 3D graph on the map, plus an insight card that explains it.
> **Applies to:**
> - `console/`: a new Insights route, the 3D scene, voice commands and a new A2UI component
> - `scripts/`: a new `market_map.py` and geo data in `knowledge/geo/`
> - `AGENTS.md` and a new `mama-market` skill (Phase 3D-3 needs plan mode)
> - a new ADR-0012
> **Builds on:**
> - `docs/Frontend_Design_Spec.md` v2 (shell, canvas, visual system, motion)
> - `docs/Sales-Mama-Voice-design-spec.md` (live voice, navigation grammar, spoken answers)
> - `scripts/company_analytics.py` (segment statistics on the registry index)
> - ADR-0003 (deterministic math), ADR-0005 (data residency), ADR-0006 (the console renders only), ADR-0008 (local registry index), ADR-0009 (scripts emit data, views are A2UI)

---

## 0. Why this spec

Today Sales Mama can already say *"Singapore has 9,618 live clinic companies, with a median age of 8.4 years and 92.7% filing on time."* That fact arrives as a flat card with a bar chart of "postal sector 52, 46, 31…". That works for a single number, but it cannot answer the questions a manager asks when planning territories and targets:

| Question people ask | What they get today | What is missing |
|---|---|---|
| "Where is the clinic market in Singapore?" | Top 10 postal sectors as bars | The **geography**: which towns, how clustered, east versus west |
| "How big is the market for IT Care?" | Nothing; the model must not invent it | A **sizing** computed from the registry and product values (TAM, SAM, SOM) |
| "Where are we strong, where are we absent?" | The rep book as a list | **Penetration** by area: our accounts against the addressable base |
| "Which areas are growing?" | One incorporations-by-year chart for the whole segment | **Momentum by area**, compared side by side |
| "Is Tampines really better than Jurong, or is it noise?" | No statistics | Proper **tests and intervals**, said plainly |

**Goal:** an *insight space*. This is one panoramic 3D Singapore where:
- **height is size** (how many companies)
- **colour is a second measure** (growth, penetration or health)
- **floating 3D graphs** answer each question where it applies on the map
- **Sales Mama's voice** flies the camera and narrates the insight in one short sentence

It should be the most memorable screen in Sales Mama, and also the most honest one.

---

## 1. Principles

The UI principles (UI.md §1, Frontend spec §1) and the voice principles stay. There are six new ones:

1. **The map is a view, never a brain.** Every number on the map is computed by `scripts/market_map.py` from the local registry index and bound by key. The model chooses *which* question to run, then explains the result. It never types a number, a coordinate or a height (ADR-0003, ADR-0009).
2. **Height means one thing.** In any scene, extrusion height encodes exactly one measure, named in the legend: for example *"Height: live clinic companies"*. Colour encodes at most one more, in stepped classes. There are no unlabelled 3D bars.
3. **Every bar has a number.** 3D distorts perception: far bars look short. So the selected and the top five areas always carry a value label, and every scene has a **table view** one key away (`Tab`).
4. **Say what the data is.** ACRA records the **registered address**, not where a company operates, and it has no headcount. The map says this in its footer and in the "How this was computed" disclosure. Our share is called **penetration** (our accounts ÷ addressable base), never "market share", because we have no competitor data.
5. **Voice is the remote control.** A camera command ("fly to Jurong", "rotate", "top view") runs locally in under 300 ms with a spoken confirmation. A question goes to Sales Mama and returns as a scene. Both work with the mouse and keyboard too.
6. **Calm motion, no motion sickness.** Camera flights last 1.2–2.0 s on an ease-in-out curve, with at most one flight at a time. The slow panorama orbit runs only when the user starts it. `prefers-reduced-motion` turns flights into cross-fades.

**Non-negotiables** (unchanged ADRs):
- **Console:** the console only renders. Questions become prompts, and the scripts compute (ADR-0006).
- **Data residency:** all data stays local (ADR-0005). The registry index is a rebuildable cache of public data (ADR-0008). Map geometry is public open data, bundled locally.
- **Scoping (rule 16):** company-level pins are shown only for the viewer's own accounts (the manager sees the team). Market layers show **aggregates only**, at least 5 companies per cell. There are no director or person names anywhere on the map.
- **No gradient washes and no emoji (UI.md §4).** Colour ramps are stepped solid classes, and the ground is a solid tint.

---

## 2. References: what we take, what we leave

| Product | Take | Leave |
|---|---|---|
| **Apple Maps Flyover / Google Earth** | Smooth pitched orbit; "fly to" with an arc that eases out; a tour of stops | Photoreal textures (heavy, licensed, distracting) |
| **kepler.gl / deck.gl examples** | Extruded choropleths, hexagon bins, column layers, arcs; GPU picking; tooltips | Configuration panels full of sliders |
| **Bloomberg / Financial Times data graphics** | One headline number per view, the source line, an honest legend | Dense multi-panel layouts |
| **Mapbox storytelling templates** | Camera "chapters" synced to narration | Scroll-jacking |
| **Perplexity answer anatomy (already in chat v2)** | Answer first, then sources, then detail, then follow-ups | — |
| **Siri / Sales Mama Voice** | Tap once, talk, hear a short reply while the screen changes | A separate AI brain |

**What makes Sales Mama 3D Insights unique.** There are five signature elements:

1. **The Island.** An abstract, solid-tint Singapore made of 55 planning areas, floating on a quiet ground with a thin coastline. It has no street clutter and needs no licensed basemap. It is recognisable at a glance, and it works offline.
2. **Insight Towers.** Planning areas rise as extruded prisms. The selected tower glows with a lime rim (the Sales Mama "now" colour) and carries a floating **graph card** above it: a small 3D bar or sparkline with the number.
3. **Mama Beam.** While Sales Mama speaks about an area, a thin violet beam drops from the caption bar to that area. You always know what the voice refers to.
4. **Whitespace Halos.** Large addressable bases where we have no accounts are ringed with a slowly pulsing lime halo. Where to go next is visible in one second.
5. **Market Tour.** "Mama, give me the market tour" starts a guided panorama of five stops: the whole island, the biggest region, the fastest-growing area, the biggest whitespace, and the recommendation. Each stop has one spoken sentence and one card.

---

## 3. Information architecture

A new route joins the nav rail between Book and Reports:

| Route | URL | Purpose | Context panel |
|---|---|---|---|
| **Insights** | `/insights?seg=clinics&m=base&c=growth&area=tampines&view=3d` | The 3D market space | Insight stack: headline metrics, area card, answer cards, "How computed" |

Every view state lives in the URL, so a scene can be bookmarked and refreshed:
- segment
- height measure
- colour measure
- selected area
- camera preset
- view (`3d | top | table`)

A chat answer that produces a map scene opens it **in the canvas** (Frontend spec §5), using the same component as the route. "Open in Insights" moves the scene to the full route.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ SM Sales Mama  [⌘K]   SG 10:42 ● open        ◉ Mama is listening…              [Kestrel 14:00] │
├────┬───────────────────────────────────────────────────────────────────┬─────────────────────┤
│ ⌂  │ Clinics ▾   Height: Live companies ▾   Colour: Growth 12m ▾   3D|Top|Table │ INSIGHT STACK    │
│ 💬 │                                                                   │ ┌─────────────────┐ │
│ 📅 │                   ┌───┐  ← graph card "Tampines 412 · +9%"        │ │ 9,618 live      │ │
│ ◎  │          ▂▃▅      │▇▅▃│                                           │ │ clinic companies│ │
│ ▤  │      ▃▅▇█▇▅▃▂   ║ └───┘                                           │ │ SAM S$31.2M/yr  │ │
│ ◈  │   ▂▅██████▇▅▃▂  ║  ← Mama Beam                                    │ │ Penetration 0.4%│ │
│ ⚙  │  ▁▃▅▇█████▇▆▅▃▂▁  ◯ whitespace halo                               │ └─────────────────┘ │
│    │     ▁▂▃▄▅▄▃▂▁                                                     │ Tampines  ▸ card    │
│    │  N ⊕   Legend: height = live companies · colour 5 classes growth  │ Answer: "East has…" │
│    │ "East has the most clinics: 2,310, growing 9% a year."  (captions)│ How computed ▸      │
│    │ [◉ orb]  Ask about the market…                         [⌘↵]       │ Follow-ups ▸ ▸ ▸    │
└────┴───────────────────────────────────────────────────────────────────┴─────────────────────┘
  nav rail gets ◈ Insights · stage fluid (WebGL) · context panel 360px, resizable 300–640
```

- **Mobile (under 900 px):** the stage is full width. The insight stack becomes the bottom sheet. Two-finger rotate and pinch zoom.
- **Phase 3D-2 includes Top and Table views.** Top is a flat 2D choropleth from straight above. Table is a sortable data table. Both are always available: they are the accessibility and printing paths, and the fallback when WebGL2 is missing.

---

## 4. Data and geography

### 4.1 Geography hierarchy

| Level | Count | Source | Used for |
|---|---|---|---|
| Singapore | 1 | — | The headline |
| Region | 5 (Central, East, North, North-East, West) | URA Master Plan 2019 (each planning area carries its region) | Region tours, region comparison |
| **Planning area** | 55 | **URA Master Plan 2019 Planning Area Boundary (No Sea)**, GeoJSON, data.gov.sg, Singapore Open Data Licence | **The main towers** (polygons) |
| Postal district / sector | 28 / ~80 | Public URA district-to-sector table; the 2-digit sector is already used by `company_analytics.py` | Phase 1 join key (sector → planning area) |
| Building (postal code) | thousands per segment | OneMap Search API (postal → lat/lon), opt-in, cached | Phase 3D-6 hexbins and own-account pins |

**The join problem, stated honestly.** The registry gives a 6-digit postal code. A postal **sector** (2 digits) does not map exactly onto a planning area: about a fifth of sectors straddle two or more. So there are two methods:

- **Phase 1 (no geocoding).** `knowledge/geo/sg_sectors.yaml` maps each sector to **weights over planning areas**. The weights are built once, offline, by geocoding one sample of postal codes per sector and counting point-in-polygon hits; the build script is checked in. Area counts from this method are **estimates**. They are labelled `≈`, and the totals always add up to the segment total exactly (largest-remainder rounding).
- **Phase 3D-6 (geocoded).** Each distinct postal code in a segment is geocoded once via OneMap and cached in `company-check/data/geo.sqlite`, which is git-ignored. Each code is then placed in an area by point-in-polygon. Counts become exact, and the `≈` disappears.

### 4.2 Files

```
knowledge/geo/
  sg_planning_areas.geojson      55 polygons, simplified to ~250 KB (Douglas-Peucker, 15 m), id/name/region
  sg_sectors.yaml                sector -> district, region, {planning_area: weight}
  sg_geo.meta.yaml               dataset ids, versions, licence lines, build date
scripts/
  market_map.py                  questions -> scene data (JSON); stdlib only
  build_geo.py                   one-off: simplify GeoJSON, build sector weights (offline, from cached geocodes)
company-check/data/geo.sqlite    (Phase 3D-6, git-ignored) postal -> lat, lon, planning_area, geocoded_at
company-check/reports/map-*.json saved scenes, bound by the console (same as insights-*.json)
```

### 4.3 Measures

Every measure is computed in `market_map.py` from `registry.sqlite`, the rep books (`wiki/books/*.json`) and `knowledge/`. Each measure is defined once, in one table that the "How computed" disclosure prints verbatim.

| Key | Label | Definition | Notes |
|---|---|---|---|
| `base` | Live companies | Live entities whose primary SSIC matches the segment (`knowledge/icp.md` `ssic_prefixes`) | The **market base** |
| `addressable` | Addressable | `base` minus home-based (HDB residential), shells (SSIC 70) and entities under 1 year old; filing on time | The serviceable base. ICP's 10–200 employees cannot be checked: ACRA has no headcount |
| `density` | Per km² | `base` ÷ land area of the planning area | Stops large areas looking big just because they are large |
| `growth` | Growth 12 months | New registrations in the last 12 months ÷ registrations in the 12 months before, minus 1 | Hidden when fewer than 20 companies in the prior period |
| `age` | Median age | Median years since registration | |
| `ontime` | Filing on time | % with annual returns on time (as in `company_analytics.files_on_time`) | A health proxy |
| `accounts` | Our accounts | Accounts in the books at stage ≥ contacted, in this segment and area | Scoped: a rep sees their own, the manager sees the team |
| `customers` | Customers | Accounts at stage `won`/`customer` | |
| `penetration` | Penetration | `customers ÷ addressable` | **Not market share** |
| `coverage` | Coverage | `accounts ÷ addressable` | How much of the base we have touched |
| `whitespace` | Whitespace | `addressable − accounts` | Halos are drawn on the top 5 areas by whitespace × fit |
| `tam`, `sam`, `som` | Market size, S$ per year | See §4.4 | Per product, or the bundle |

### 4.4 Sizing the market (TAM, SAM, SOM)

The model never sizes a market in its head. `market_map.py size` does it, with every input shown:

```
TAM  = base          × typical_value[product][SG]        e.g. IT Care: 9,618 × S$5,000 = S$48.1M a year
SAM  = addressable   × typical_value × fit_rate          fit_rate = products/<p>.yaml fits (industry); 1.0 if all
SOM  = SAM × win_rate (range)                             win_rate from our own log: customers ÷ proposals,
                                                          last 12 months, with a Wilson 80% interval;
                                                          "not enough history" if fewer than 30 proposals
```

- The value per product comes from `knowledge/products/*.yaml` `typical_value`: IT Care S$5,000, Cloud Phone S$6,000 and Managed WiFi S$4,000 in SG. A "bundle" size uses the sum, not a guess at attach rates.
- The SOM is shown as a **range** (low–mid–high). Voice says it as *"about two to three million dollars a year"*, never as a false-precision figure.
- If a product's `fits.industries` excludes the segment, the size is **zero**, with the reason shown.

### 4.5 Statistics (deterministic, stdlib only)

All statistics are Python `statistics` and `math`, as `company_analytics.py` uses. There is no numpy, and the results are reproducible and unit-tested.

| Question shape | Method | How it is spoken |
|---|---|---|
| "Is A bigger than B?" (shares) | Two-proportion z-test, plus a Wilson 95% interval for each | "Yes. Tampines has a clearly higher share of new clinics: 9% against 4%." / "No real difference: within noise." |
| "Which areas stand out?" | Robust z-score on density (median and MAD), \|z\| > 2.5 | "Two areas stand out: Novena and Bukit Merah." |
| "Is the market concentrated?" | Top-5 area share plus a Herfindahl index over areas | "Fairly spread: the top five areas hold 31%." |
| "Where are the hot spots?" | Getis-Ord Gi* on planning-area neighbours (queen contiguity, precomputed) | Hot and cold areas tinted, "Hot spot in the East around Tampines and Bedok." |
| "Does growth follow density?" | Spearman rank correlation with n, and a permutation p-value (1,000 shuffles, fixed seed) | "Weak link: rho 0.21, could be chance." |
| "What's the trend?" | Yearly registrations, Theil–Sen slope | "Rising by about 40 a year since 2018." |
| "How is it distributed?" | Percentiles (p10/p50/p90) across areas | Spoken only as the median and the range |

**Guards.**
- A result is never called "significant" with n under 30 or with cells under 5. It is called "too few to tell".
- Correlation is never phrased as cause.
- Each statistic carries `n`, its method and its interval in the JSON. The card shows them under "How computed".

---

## 5. Question → scene pipeline

```
 voice / composer ──► /mama (Claude Code, mama-market skill) ──► scripts/market_map.py <question>
                                                                     │  JSON: data + scene
 console canvas / Insights ◄── A2UI Map3D bound to map-<slug>.json ◄─┘
     │  camera flies, towers morph, cards appear            ▲
     └── voice: lead sentence (≤ 20 words) + Mama Beam ─────┘
```

### 5.1 `market_map.py` commands

```
python3 scripts/market_map.py overview  --segment clinics                       # island, regions, headline metrics
python3 scripts/market_map.py area      --segment clinics --area tampines       # one area: profile, trend, peers
python3 scripts/market_map.py compare   --segment clinics --areas tampines,jurong-east
python3 scripts/market_map.py rank      --segment clinics --by density|growth|whitespace|penetration --top 10
python3 scripts/market_map.py size      --segment clinics --product it-care|cloud-phone|managed-wifi|bundle [--region east]
python3 scripts/market_map.py stats     --segment clinics --test outliers|hotspots|concentration|trend|correlate --x density --y growth
python3 scripts/market_map.py tour      --segment clinics                       # five-stop guided tour
  every command: --owner me|team (scope for our accounts), --out company-check/reports/map-<slug>.json
```

All of them use the same output shape as `company_analytics.py`: `{title, summary[], as_of, licence, order[], sections{}}`. Two new section kinds are added:

```jsonc
"map3d": {
  "kind": "map3d",
  "segment": "clinics",
  "height": {"key": "base", "label": "Live clinic companies", "unit": "companies"},
  "colour": {"key": "growth", "label": "Growth, 12 months", "classes": [-0.05, 0, 0.05, 0.10], "scheme": "mama-seq"},
  "areas":  [{"id": "tampines", "name": "Tampines", "region": "east", "values": {"base": 412, "growth": 0.09, "accounts": 3}, "approx": true}],
  "focus":  ["tampines"],                     // what the camera frames
  "camera": "frame-focus",                    // preset name, never raw coordinates from the model
  "cards":  [{"area": "tampines", "kind": "bar|spark|donut|stat", "series": "trend_tampines"}],
  "halos":  ["pasir-ris", "punggol"],
  "pins":   "own-accounts",                   // or "none"; scope enforced in the script
  "story":  [{"focus": ["east"], "say_ref": "summary.0"}]   // tour stops; text comes from summary[]
},
"stat": {"kind": "stat", "method": "two-proportion z", "n": [412, 288], "value": 0.05, "ci": [0.02, 0.08], "verdict": "higher|lower|no-difference|too-few"}
```

Camera framing is computed in the browser from the area polygons and the `focus` list, so the model has no coordinates to get wrong.

### 5.2 The `mama-market` skill (Phase 3D-3, plan mode)

- It triggers on market questions: market size, where, share, penetration, growth, compare, territory, whitespace, "on the map".
- It maps the question to **one** `market_map.py` command, runs it with `--out`, and answers in the chat v2 anatomy: a lead sentence, then the bound surface, then the "How computed" disclosure, then 3 follow-ups.
- **Words it must use:** "penetration", not "market share"; "≈" for sector estimates; "registered address" when the place matters.
- **Refusals:** competitor share, revenue of named companies, anything about people. Each refusal comes with a one-line alternative that it can answer.
- **Voice mode** (`voice: true`): the lead is under 20 words and contains one number and one place.
- **Updates:** AGENTS.md gets a short "Market questions" rule, plus eval cases (§11).

---

## 6. The 3D scene

### 6.1 Technology

| Option | Verdict |
|---|---|
| **deck.gl** (MIT) with `MapView` and no basemap: `PolygonLayer` (extruded), `ColumnLayer`, `HexagonLayer`, `ArcLayer`, `ScatterplotLayer`, `TextLayer`, `PathLayer` | **Recommended.** GPU picking and transitions built in. About 55 polygons plus up to 20k points is trivial at 60 fps |
| deck.gl with MapLibre GL (BSD) and an OpenStreetMap basemap (self-hosted PMTiles extract of Singapore) | **Optional later layer** ("Streets"). It is heavier (~25 MB of tiles) and needs an ODbL attribution line |
| three.js with custom extrusion | Rejected: more code for picking, labels and transitions |
| Google 3D Tiles / Cesium | Rejected: cloud keys, licensing, data leaves the laptop |

- **Code splitting:** the scene is a **lazy chunk** (`import('./insights/Stage')`), loaded only on `/insights` or when a map3d surface first opens. **Budget:** at most 450 KB gzipped for the chunk; the main bundle is unchanged.
- **The dependency question:** this is the first new runtime dependency since the Frontend spec's "no new dependencies" rule. Manager decision D1 (§12).
- **Fallback:** without WebGL2, or on a GPU error, it falls back to the **Top** view, drawn as SVG from the same GeoJSON with the same data, so the feature never fails blank.

### 6.2 Layers

| Layer | deck.gl | Encodes | Default |
|---|---|---|---|
| Ground and coastline | `PolygonLayer` (flat), `PathLayer` | — | Always |
| **Insight Towers** | `PolygonLayer` extruded, height = `sqrt`-scaled measure, max 3,000 m | height measure (+ colour measure) | On |
| Region plinths | Flat polygons with a 2 px outline, region tint at 18% | Region | On when zoomed out |
| Graph cards | HTML overlays positioned with `project()`, max 5 | Small charts per area | Selected + focus |
| Labels | `TextLayer` with collision filter | Area name + value | Top 5 + selected |
| Whitespace Halos | `ScatterplotLayer` rings, animated radius | Top 5 whitespace × fit | On in penetration views |
| Our accounts | `ScatterplotLayer` violet dots (Phase 3D-6: real positions; earlier: area centroids with a count badge) | Own book only | Toggle `A` |
| Hexbins | `HexagonLayer`, 300 m cells, min 5 per cell | Density at building level | Phase 3D-6, toggle `H` |
| Compare arcs | `ArcLayer` between two areas, label at apex | Difference and its verdict | compare |
| Hot spots | Tower tint override: hot = Writer orange, cold = Scout blue | Gi* result | stats hotspots |
| Mama Beam | `LineLayer` from screen top to the area centroid, violet, 2 px, fades 400 ms | What the voice is talking about | While speaking |

### 6.3 Visual system (Sales Mama tokens)

- **Ground:** in light mode, the stage background is `--ground`; the island is `--surface`; the coastline is `--line-2`. Dark mode uses the same tokens. No sky gradients, no fog washes.
- **Sequential colour classes ("mama-seq"):** five stepped solid classes of the Mama violet, from tint `#EFE8FF` to solid `#6D28D9` (dark mode: `#2A2142` → `#A78BFA`). They are validated with the dataviz contrast script.
- **Diverging classes ("mama-div"):** for growth and hot spots: Scout blue ← neutral → Writer orange, in five classes. Neutral is `--line`.
- **Selection:** lime `#C8F031` rim (a 3 px outline on the tower's top face) plus a lift of 8% in height, over 200 ms.
- **Graph cards:** 20 px radius, level-1 elevation, Bricolage 28 for the number, 13 caption, tabular numbers. They hold at most one chart.
- **Lighting:** one directional light from the north-west, plus ambient. Tower sides are 12% darker than the tops, so heights read without shadows.
- **Typography on the map:** 13/15 Inter labels with a 2 px halo of `--ground`; never rotated, always facing the camera.
- **Glyphs:** shape is always shown with colour (UI.md: never colour alone): halo = ring, account = dot, hot = ▲, cold = ▼ on the label.

### 6.4 Camera presets and motion

| Preset | Pitch / bearing / zoom | Use |
|---|---|---|
| `island` | 50° / −15° / whole island | Home, overview |
| `top` | 0° / 0° | Top view, printing |
| `region:<id>` | 55° / region-specific | Region stops |
| `frame-focus` | 58° / bearing that faces the tallest focus tower | Answers |
| `panorama` | 60°, bearing +6°/s, stops on any input | "Panorama" / `P` |
| `tour` | Sequence of the above, 1.6 s flights, 6–8 s dwell | Market Tour |

Motion tokens reuse the Frontend spec §7.3:

| What moves | How |
|---|---|
| Fly-to | `FlyToInterpolator`, 1.2–2.0 s, eased with `--ease-out` |
| Tower morph between measures | Height and colour transitions over 600 ms |
| Cards | Enter over 200 ms; KPI count-up once, 600 ms |
| Reduced motion | Cuts with a 120 ms fade, no orbit, no halo pulse |

### 6.5 Controls

| Input | Action |
|---|---|
| Drag / two-finger drag | Pan |
| Right-drag, ⌥-drag / two-finger rotate | Orbit (bearing, pitch) |
| Wheel / pinch | Zoom |
| Click a tower | Select; the card opens in the insight stack |
| Double-click | Fly to it |
| `←↑→↓` | Pan |
| `Q` / `E` | Rotate |
| `W` / `S` | Tilt |
| `+` / `−` | Zoom |
| `1`–`5` | Regions |
| `0` | Island |
| `T` | Top view |
| `Tab` | Table |
| `P` | Panorama |
| `G` | Tour |
| `A` | Accounts |
| `H` | Hexbins |
| `Esc` | Deselect |
| ⌘K | "Insights: …" commands: every segment, measure and area |

---

## 7. Voice: navigate and ask in the 3D space

This builds on the live mode from the Voice spec §16: tap the orb once and talk.

### 7.1 Local commands (no model, under 300 ms, spoken confirmation)

Added to `parseCommand` in `console/shared/voice.ts` as an `insights` grammar that is active on the Insights route and on map surfaces in the canvas. The grammar matches the whole utterance, as today, so anything else is a question.

| Say | Does | Mama says (`NAV_PHRASES`) |
|---|---|---|
| "Show me Singapore", "the whole island", "zoom out" | `island` preset | "Here is Singapore." |
| "Fly to Tampines", "go to Jurong East", "show the East" | Fly to the area or region (fuzzy match against the 55 names, using `mentions.ts` strict matching) | "Here is Tampines: 412 clinics." *(the number comes from the bound scene, not from the model)* |
| "Zoom in", "closer", "zoom out" | Zoom ±1 | "Closer." |
| "Rotate left/right", "turn around" | Bearing ±45° / 180° | "Turning." |
| "Tilt up", "tilt down", "top view", "3D view" | Pitch / `top` / back to 3D | "Top view." |
| "Panorama", "fly around", "stop" | Start or stop the orbit | "Flying around." |
| "Height by growth", "colour by penetration" | Swap measures (morph) | "Height now shows growth." |
| "Show clinics", "switch to retail" | Segment (runs `overview` through the brain only on the first load; cached after) | "Here are retail companies." |
| "Show our accounts", "show hot spots", "hide halos" | Layer toggles | "Your accounts are in violet." |
| "Show the table", "back to the map" | Table / 3D | "Here is the table." |
| "Start the tour", "next stop", "previous stop", "end tour" | Market Tour control | Stop narration |
| "What can I say here?" | Speaks four examples, opens the shortcut sheet | — |

### 7.2 Questions (through Sales Mama)

Examples of questions that route to `mama-market`, with the expected scene:

| Spoken question | Command | Scene | Spoken lead (example shape) |
|---|---|---|---|
| "How big is the clinic market?" | `overview` | Island, height = base | "Singapore has 9,618 live clinic companies; the Central region holds the most." |
| "Size the market for IT Care in clinics." | `size --product it-care` | Island with region cards; S$ on plinths | "About 48 million dollars a year in total; roughly 31 million is serviceable." |
| "Where are we absent?" | `rank --by whitespace` | Halos on the top 5 | "Biggest whitespace is Woodlands: about 260 addressable clinics, none contacted." |
| "Compare Tampines and Jurong East." | `compare` | Two towers, arc with verdict | "Tampines is bigger and growing faster: 9% against 4%; the difference is real." |
| "Which areas are growing fastest?" | `rank --by growth` | Diverging colours, top 3 labelled | "Punggol grows fastest, 14% a year, but from a small base." |
| "Is the market concentrated?" | `stats --test concentration` | Top 5 towers lit, others dimmed | "Fairly spread: the top five areas hold about a third." |
| "Any hot spots?" | `stats --test hotspots` | Hot and cold tints | "One hot spot in the East around Bedok and Tampines." |
| "Does growth follow density?" | `stats --test correlate --x density --y growth` | Towers plus a floating scatter card | "Only a weak link, and it could be chance." |
| "What's our penetration in the West?" | `area --area west` | Region framed, accounts on | "Under one percent: 4 customers out of about 900 addressable." |
| "Give me the market tour." | `tour` | Five-stop tour | One sentence per stop |
| "Where should Mike focus next quarter?" (manager) | `rank --by whitespace --owner team` | Halos plus team accounts | "Woodlands and Yishun: large bases, nobody assigned." *(no assignment happens; allocation stays a skill with approval)* |

### 7.3 Speech and camera choreography

1. **Ack, immediately:** "Let me look at the market." (from the voice spec `ACKS`). A shimmer runs along the island's coastline, the "thinking" pattern.
2. **Scene arrives:** the camera starts its flight **at the same moment** the TTS starts the lead sentence. The flight time is chosen so the camera settles on the word that names the place (Inworld word timestamps are already wired for captions).
3. **Mama Beam** on the area while its name is spoken; the graph card enters as the number is spoken.
4. **Quiet after the lead.** The rest stays on screen. "Tell me more" reads the second summary line.
5. **Barge-in** ("stop", or speaking) halts the camera at its current position and stops speech, as in voice today.

---

## 8. Insight stack (context panel)

From top to bottom, all of them existing A2UI components bound to the scene file:
1. **Headline metrics** (`metrics` section): base, addressable, SAM, penetration, each with a status colour.
2. **Area card** for the selected area:
   - name, region and `≈` badge
   - the five measures
   - a 10-year registration sparkline
   - its rank among the 55
   - "Ask about Tampines" chips
3. **Answer card:** the latest question's lead, plus a stat badge (`higher · 95% CI 2–8 pts`).
4. **How computed** (disclosure):
   - measure definitions
   - formulas with inputs
   - method, `n`, interval
   - data date
   - licence line
   - the `≈` explanation
5. **Follow-ups:** 3 chips from the script's `next[]`.
6. **Save / Share:**
   - **Save** writes the scene to Reports (`map-*.json`, as reports work today).
   - **Share** exports a page with a PNG snapshot of the 3D view, the Top SVG and the table. It stays offline-clean, because the exported page needs no WebGL.

---

## 9. Architecture

```
console/src/
  insights/   InsightsView.tsx (route) · Stage.tsx (lazy; deck.gl) · layers.ts · camera.ts (presets, framing from polygons)
              TopView.tsx (SVG fallback) · TableView.tsx · GraphCard.tsx · InsightStack.tsx · tour.ts · geo.ts (load + index GeoJSON)
  a2ui/       + Map3D component (catalog entry; binds a map3d section; renders Stage in canvas)
  voice/      navigate.ts + insights actions · useVoiceController: beam + flight sync on word timings
  styles/     insights.css
console/shared/
  voice.ts    + INSIGHT_COMMANDS grammar, NAV_PHRASES for insights, area-name vocabulary for STT prompts
  geo.ts      pure: area name matching, polygon centroid/bbox, class breaks, largest-remainder rounding (tested)
console/server/
  index.ts    + GET /api/geo (serves knowledge/geo/*.geojson, cached, read-only)
scripts/      market_map.py · build_geo.py
knowledge/geo/  sg_planning_areas.geojson · sg_sectors.yaml · sg_geo.meta.yaml
```

- **State:** the scene file is the truth. `useInsights` holds only view state (camera, selection, toggles) and mirrors it to the URL.
- **STT vocabulary:** the 55 planning-area names (Ang Mo Kio, Bukit Timah, Choa Chu Kang, Pasir Ris…) are added to the Inworld STT `prompts` vocabulary while on Insights. Local names are the main transcription risk.
- **Writes:** the browser writes nothing. Saving a scene is a prompt, as in Reports today.

---

## 10. Performance, accessibility, privacy

| Area | Budget / rule |
|---|---|
| First 3D frame | Under 1.2 s after the route opens (lazy chunk plus a ~250 KB GeoJSON, cached) |
| Frame rate | 60 fps orbit on an M1 laptop at 1440×900. Degrade gracefully: hexbins off when FPS is under 40 for 2 s |
| Voice command → camera starts | Under 300 ms |
| Question → scene | Brain time, as chat today. The ack lands in under 400 ms |
| Accessibility | Table view for every scene. Every tower is reachable by keyboard (`[` `]` cycles areas by rank) and announced via `aria-live` ("Tampines, 412 clinics, rank 3 of 55"). Contrast ≥ 4.5:1 on labels. Captions for all speech |
| Privacy | Aggregates only for market layers (cells under 5 merged or hidden). Company pins only for the viewer's book. No person names. Geocoding (Phase 3D-6) sends **postal codes only** to OneMap, is opt-in, is cached, and has a manager switch |
| Licences | Footer line from `sg_geo.meta.yaml`: URA Master Plan 2019 and ACRA via data.gov.sg (Singapore Open Data Licence v1.0); OneMap attribution when geocodes are used; OSM/ODbL only if the Streets layer is enabled |

---

## 11. Implementation plan

Each phase ships alone, ends with green tests and leaves the console usable. The phases follow the house pattern: a failing test first, then the feature. Phase prompts are at the end of this section.

### Status (2026-11-28)

| Phase | Status |
|---|---|
| 3D-0 to 3D-7 | Not started: spec only |

### Phases

| Phase | Scope | Key files | Done when | Size |
|---|---|---|---|---|
| **3D-0 · Geo data spike** | Fetch and simplify the URA planning-area GeoJSON. Build `sg_sectors.yaml` (sector → area weights) from one cached sample per sector. Write `sg_geo.meta.yaml` with licence lines. Decide D2 (geocoding) | `scripts/build_geo.py`, `knowledge/geo/*` | 55 areas, each with a region. All ~80 sectors have weights summing to 1. Rendered to an SVG check image. Selftest: GeoJSON valid, ids unique | S |
| **3D-1 · Market data engine** | `market_map.py overview / area / rank` with all §4.3 measures. Largest-remainder allocation. Scope by owner. `map3d` section kind. Tests | `scripts/market_map.py`, `scripts/selftest.py`, `console/shared/a2ui.ts` (section schema) | **Invariant:** areas sum exactly to the `company_analytics.py segment` total. Measures match hand-computed fixtures. A rep sees only their own accounts | M |
| **3D-2 · Insights route, static 3D** | Route and nav item, lazy `Stage` with Island + Towers + labels, legend, Top SVG and Table views, insight stack, URL state, WebGL fallback | `console/src/insights/*`, `Nav.tsx`, `router.ts`, `insights.css`, `/api/geo` | Clinics overview renders in 3D, Top and Table with identical numbers. Chunk ≤ 450 KB gz. Works with WebGL off (SVG). Light and dark | L |
| **3D-3 · Questions → scenes** (plan mode) | `compare`, `size`, `stats` commands. The `mama-market` skill. AGENTS.md rule. `Map3D` A2UI component in chat and the canvas. Compare arcs, halos, graph cards. "How computed" | `scripts/market_map.py`, `.agents/skills/mama-market/*`, `AGENTS.md`, `a2ui/catalog.ts`, `insights/GraphCard.tsx` | The 11 questions in §7.2 each produce the right command and scene. Evals pass (§12): no invented numbers, "penetration" wording, refusals | L |
| **3D-4 · Camera, motion, tour** | Presets, fly-to, tower morphs, panorama orbit, keyboard map, Market Tour (`tour` command + `tour.ts`), reduced motion | `insights/camera.ts`, `tour.ts`, `useHotkeys` | 60 fps orbit. Every control in §6.5 works by keyboard. The tour runs 5 stops in 45 ± 10 s. Reduced motion: no orbit | M |
| **3D-5 · Voice in the 3D space** | `INSIGHT_COMMANDS` grammar, NAV phrases bound to scene numbers, area vocabulary for STT, Mama Beam, flight timed to word timestamps, barge-in stops the camera | `shared/voice.ts`, `voice/navigate.ts`, `useVoiceController.tsx` | Grammar tests for every §7.1 phrase plus near-misses that must stay questions. Live test: "fly to Choa Chu Kang" transcribed and flown in under 300 ms after the end of the turn. GPT live gets the same commands via `voice_command` | M |
| **3D-6 · Building-level precision** (optional, D2) | Opt-in OneMap geocoding of segment postal codes into `geo.sqlite`, exact area counts (drop `≈`), hexbins, own-account pins at real positions | `scripts/market_map.py geocode`, `company-check/data/geo.sqlite` | Rate-limited (under 200/min), resumable, cached. Hexbin cells under 5 hidden. Exact counts still sum to the segment total | M |
| **3D-7 · Hardening and demo** | Playwright e2e (route, fallback, keyboard, voice commands with a fake mic), visual snapshots of 4 scenes, perf budget in CI, share export (PNG + SVG + table), docs (UI.md, README), a demo film chapter | `console/e2e/*`, `docs/*`, `exportPage.ts` | CI green. Exported page offline-clean. Docs and screenshots updated | M |

**Suggested order:** 3D-0 → 3D-1 → 3D-2, then a review with screenshots, then 3D-3 → 3D-4 → 3D-5. 3D-6 when D2 is decided. 3D-7 last. Phases 3D-2 and 3D-1 can overlap once the `map3d` JSON shape (§5.1) is frozen.

### Phase prompts (paste into Claude Code, one per phase)

- **3D-0:** "Read `Sales-Mama-3D-Insights-design-spec.md` §4. Write `scripts/build_geo.py` and build `knowledge/geo/` from the URA Master Plan 2019 planning-area dataset on data.gov.sg. Verify the dataset id first. Add selftest checks. Show me an SVG of the 55 areas."
- **3D-1:** "Implement `scripts/market_map.py` overview/area/rank per §4.3 and §5.1. Write failing tests first, including the sum invariant against `company_analytics.py segment --industry clinics`."
- **3D-2:** "Build the Insights route per §3, §6 and §9 with deck.gl as a lazy chunk. Include the Top SVG and Table views and the WebGL fallback. Screenshot light and dark."
- **3D-3 (plan mode):** "Add compare/size/stats to `market_map.py`, then the `mama-market` skill, the AGENTS.md rule, the `Map3D` A2UI component and the eval cases in §12."
- **3D-4:** "Camera presets, flights, tour and keyboard per §6.4–6.5."
- **3D-5:** "Insights voice grammar and choreography per §7, with tests for every phrase."
- **3D-6:** "Opt-in OneMap geocoding per §4.1, only after the manager approves D2."
- **3D-7:** "E2E, snapshots, perf budget and share export per §10–11."

---

## 12. Testing and evals

| Layer | Tests |
|---|---|
| `market_map.py` (selftest + pytest-style cases in `selftest.py`) | The sum invariant. Largest-remainder rounding. Each measure against a 40-company fixture. TAM/SAM/SOM arithmetic. Wilson interval, z-test, Spearman, Theil–Sen and Gi* against known values. "Too few to tell" thresholds. Scope (rep vs manager). Cells under 5 merged |
| `shared/geo.ts` (Vitest) | Area-name matching (Bukit Panjang vs Bukit Batok, "AMK", "Toa Payoh" STT variants), class breaks, centroid and bbox |
| `shared/voice.ts` (Vitest) | Every §7.1 phrase → its command. Near-misses stay questions ("fly to Tampines tomorrow for a meeting" is a question) |
| Browser (Playwright) | Route loads, the 3D/Top/Table numbers are identical, keyboard map, WebGL-off fallback, reduced motion, 390 px |
| **Evals** (`evals/`, run by `scripts/eval.py`) | 1) Every number in a market answer appears in the saved scene file (the existing grounding guard, `ungroundedNumbers`). 2) The answer never says "market share" about our accounts. 3) It refuses "what is Competitor X's share" with an alternative. 4) "Is A bigger than B" with n under 30 returns "too few to tell". 5) Voice leads are 20 words or fewer with one number and one place. 6) It never names a person on the map |

---

## 13. Decisions for the manager

| # | Decision | Recommendation |
|---|---|---|
| D1 | Allow deck.gl (MIT, ~400 KB gz, lazy) as the first new runtime dependency since Frontend spec v2 | **Yes.** It is lazy, so the main bundle is unchanged. The alternative is weeks of custom WebGL |
| D2 | Geocode postal codes via OneMap (postal codes only, opt-in, cached) for exact counts and hexbins | **Yes, as Phase 3D-6.** Until then, show sector estimates marked `≈` |
| D3 | Basemap: abstract Island only, or add the OSM Streets layer | **Island only** for v1. It is distinctive, offline and licence-simple |
| D4 | Who sees team accounts on the map | The manager only. Reps see their own pins, plus market aggregates (rule 16) |
| D5 | Wording for our share | "Penetration" and "coverage". Never "market share" |
| D6 | Malaysia and India | Later. Geometry and measures are per market (`knowledge/geo/<market>/`). Ship SG first (`markets.yaml live: [SG]`) |

---

## 14. Risks

| Risk | Mitigation |
|---|---|
| **Registered address ≠ operating location** (many firms register at a corporate secretary's address in the CBD, inflating Downtown Core) | A "registered address" note in the footer. Phase 3D-1 flags postal codes with more than 50 registrations as "registration hubs", with a toggle to exclude them; the excluded count is shown |
| Sector → area estimates mislead | `≈` on every estimated value, the method explained in "How computed", exact counts in 3D-6 |
| 3D perception bias (far towers look short, occlusion) | Value labels on the top 5 and the selection, the Table view one key away, sqrt height scale stated in the legend, the Top view |
| The model invents sizes or statistics by voice | Scripts compute everything. The grounding guard checks spoken numbers against the scene file (as voice does today). Evals |
| No headcount in ACRA (the ICP is 10–200 employees) | "Addressable" is defined by proxies and labelled as such. Never claim the employee filter |
| Motion sickness and distraction | Short flights, orbit only on request, reduced-motion path, a flight stops on any input |
| Old laptops / no WebGL2 | The SVG Top view fallback, auto-degrade of layers, the perf budget in CI |
| STT mishears local names (Choa Chu Kang, Bukit Merah) | Area names in the STT prompt vocabulary, fuzzy strict matching, and "Did you mean Bukit Batok or Bukit Panjang?" when two are close |
| Dataset ids and licences change | `sg_geo.meta.yaml` records ids and versions. `build_geo.py` verifies before each rebuild. Appendix A is checked at each phase |

---

## Appendix A: Facts to verify before each phase

- **URA planning areas.** The URA Master Plan 2019 Planning Area Boundary (No Sea) is published on data.gov.sg as GeoJSON with 55 planning areas and region names, under the Singapore Open Data Licence v1.0. **Verify the current dataset id** with `fetch_dataset.py`.
- **Postal sectors.** These are the first two digits of the postal code, grouped into 28 postal districts (URA public list). `company_analytics.py` already uses 2-digit sectors.
- **OneMap.** The OneMap Search API (`/api/common/elastic/search`, `returnGeom=Y`) returns latitude and longitude for a postal code. **Verify** the current rate limits, any token requirement and the terms of use before Phase 3D-6.
- **Licences.** deck.gl is MIT. MapLibre GL JS is BSD-3 (only if D3 changes). OSM data is ODbL.
- **Product values.** IT Care S$5,000, Cloud Phone S$6,000 and Managed WiFi S$4,000 (SG), from `knowledge/products/*.yaml` `typical_value`, as of 2026-11-28. Sizing reads them live, so a change in the YAML changes the size.
- **Example figures.** Numbers in §3 and §7.2 other than the 9,618 clinics headline (measured from the sample registry, 2026-11-28) are illustrative shapes, not measurements.
