# Map modes: virtual vs. real

GAWorld's city map supports two interchangeable modes. Both build the **same**
`city_map` structure, so routing, distance, transport, spatial queries, agent
location inference, and the visualizer all work identically — the only
difference is where the geography comes from.

| | `virtual` (default) | `real` |
|---|---|---|
| Source | Procedural spec `data/citymap.md` | Real Hangzhou OSM bundle `data/hangzhou_real.geojson` |
| Coordinates | Synthetic grid → projected to fake lat/lng around Hangzhou | True WGS-84 lat/lng from OpenStreetMap |
| Nodes | Hand-authored hubs + generated blocks | Real districts (街道), metro stations, hospitals, universities, malls, parks, government |
| Roads | Generated MST + loops | Hierarchical network synthesized over real node positions |
| Metro / river | Sample lines + Qiantang stub | Real Hangzhou metro lines + real Qiantang river polyline |
| Offline / reproducible | Yes | Yes (bundle is committed) |

## Switching modes

Set `map_mode` in your config (defaults live in
[`gaworld/settings/runtime.py`](../gaworld/settings/runtime.py)):

```jsonc
{
  "map_mode": "real",                          // "virtual" | "real"
  "real_map_path": "data/hangzhou_real.geojson"
}
```

Every map load in the simulation routes through `load_city_map` /
`load_city_map_text` in `generative_city_sim.py`, which dispatch on `map_mode`,
so switching is config-only — no code changes.

## Regenerating the real bundle

The bundle is derived from OpenStreetMap via the Overpass API and committed for
offline runs. To refresh it (requires network):

```bash
python3 scripts/dev/fetch_hangzhou_osm.py            # → data/hangzhou_real.geojson
# custom area: --bbox south,west,north,east
python3 scripts/dev/fetch_hangzhou_osm.py --bbox 30.14,119.98,30.40,120.35
```

The fetcher is deliberately **coarse** (a few hundred landmark nodes, not every
building) to match the simulation's abstraction level. It rotates across public
Overpass mirrors and backs off on rate limits; metro reconstruction is
best-effort and non-fatal.

## Bundle format

A GeoJSON `FeatureCollection` (same schema as `city_map.export_geojson`, plus a
few properties). `load_real_city_map` parses:

- **Point** features → nodes. `properties`: `name`, `category`, `kind`
  (`hub`/`place`), optional `district`.
- **LineString** `properties.kind="metro"` → a metro line: `line`, `color`,
  ordered `stops` (names matching Point nodes).
- **LineString** `properties.kind="river"` → the river: `name`, `width_km`.
- **LineString** `properties.kind="road"` → an explicit road edge
  (`source`/`target` node names). Omitted edges are auto-generated.

Any bundle in this format works, so the real-map mode is not Hangzhou-specific —
point the fetcher (or a hand-authored GeoJSON) at another city and it loads the
same way.

## Rendering in the viewer

The Phaser viewer at [`site/citymap/`](../site/citymap) renders whichever map
you feed it. Regenerate its data from the real map:

```bash
python3 scripts/dev/real_citymap_viz.py    # → data/citymap_real_visualization.json (+ .geojson)
```

Then load `data/citymap_real_visualization.json` in `site/citymap/viewer.html`
(载入地图 JSON). The virtual map's committed exports are left untouched.
