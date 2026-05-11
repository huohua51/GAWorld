import heapq
import math
import os
import re
from collections import defaultdict
from pathlib import Path

BASE_LAT = 30.2741
BASE_LNG = 120.1551
KM_PER_GRID_X = 0.85
KM_PER_GRID_Y = 0.72
LAT_PER_KM = 1.0 / 111.0
LNG_PER_KM = 1.0 / 96.0

TRANSPORT_MODES = {
    "walk":  {"speed_kmh": 4.8,  "fixed_min": 0},
    "bike":  {"speed_kmh": 13.0, "fixed_min": 1},
    "e-bike":{"speed_kmh": 20.0, "fixed_min": 1},
    "bus":   {"speed_kmh": 18.0, "fixed_min": 6},
    "metro": {"speed_kmh": 32.0, "fixed_min": 7},
    "car":   {"speed_kmh": 27.0, "fixed_min": 4},
    "taxi":  {"speed_kmh": 30.0, "fixed_min": 3},
}

# --- Transport fare table (CNY, based on Hangzhou 2024-2025 typical fares) ---
TRANSPORT_FARES = {
    "walk":   {"base": 0.0,  "per_km": 0.0,  "free_km": 0},
    "bike":   {"base": 0.0,  "per_km": 0.0,  "free_km": 0},       # shared bikes ~1.5/30min but simplified
    "e-bike": {"base": 0.0,  "per_km": 0.1,  "free_km": 0},       # electricity cost
    "bus":    {"base": 2.0,  "per_km": 0.0,  "free_km": 0},       # flat fare
    "metro":  {"base": 2.0,  "per_km": 0.45, "free_km": 4},       # 2 CNY for first 4km, +1 per ~2.2km
    "car":    {"base": 0.0,  "per_km": 0.6,  "free_km": 0,        # fuel + wear
               "parking_per_hour": 6.0},
    "taxi":   {"base": 13.0, "per_km": 2.5,  "free_km": 3},       # 13 CNY base (includes 3km)
}

# --- Rush hour periods (minutes from midnight) ---
RUSH_HOUR_PERIODS = [
    (7 * 60, 9 * 60),       # morning rush 07:00–09:00
    (17 * 60, 19 * 60),     # evening rush 17:00–19:00
]
RUSH_HOUR_TIME_MULT = 1.45   # travel time multiplier during rush hour
RUSH_HOUR_TAXI_SURCHARGE = 1.30  # taxi fare surcharge during rush hour

# --- Area price level by category ---
# Multiplier for local consumption costs (food, leisure, etc.)
AREA_PRICE_LEVEL = {
    "commerce":    1.35,   # CBD / commercial districts are pricier
    "transit":     1.15,   # station areas have markup
    "leisure":     1.20,   # tourist/leisure zones
    "education":   0.85,   # campus areas are cheaper
    "residential": 1.00,   # baseline
    "medical":     1.00,
    "government":  0.95,
    "industry":    0.80,   # industrial areas are cheapest
    "mixed":       1.00,
}

# --- Weather impact on transport mode preference ---
WEATHER_MODE_ADJUSTMENTS = {
    "rain":  {"walk": 0.3, "bike": 0.2, "e-bike": 0.4, "bus": 1.5, "metro": 1.4, "car": 1.2, "taxi": 1.8},
    "snow":  {"walk": 0.2, "bike": 0.1, "e-bike": 0.2, "bus": 1.4, "metro": 1.5, "car": 1.0, "taxi": 2.0},
    "hot":   {"walk": 0.5, "bike": 0.6, "e-bike": 0.8, "bus": 1.3, "metro": 1.3, "car": 1.2, "taxi": 1.3},
    "cold":  {"walk": 0.5, "bike": 0.4, "e-bike": 0.6, "bus": 1.3, "metro": 1.3, "car": 1.1, "taxi": 1.4},
    "clear": {"walk": 1.0, "bike": 1.0, "e-bike": 1.0, "bus": 1.0, "metro": 1.0, "car": 1.0, "taxi": 1.0},
}

CATEGORY_KEYWORDS = [
    ("residential", ["Block", "Building", "Dormitory", "Flat", "Family"]),
    ("education", ["School", "Library", "University", "Daycare", "Engineering", "Arts"]),
    ("medical", ["Hospital", "Clinic", "Pharmacy", "Department"]),
    ("transit", ["Station", "Metro", "Airport", "Bus", "Taxi", "Parking", "Loop", "Rd", "Ave", "Terminal"]),
    ("industry", ["Warehouse", "Logistics", "Manufacturing", "Depot", "Substation", "Cargo", "Yard"]),
    ("government", ["Police", "Fire", "City Hall", "Courthouse", "Archives", "Public Services"]),
    ("commerce", ["Market", "Mart", "Bank", "Plaza", "Finance", "Hotel", "Cinema", "Tower"]),
    ("leisure", ["Park", "Playground", "Fitness", "Picnic", "Promenade", "Museum", "Tea House", "Amphitheater", "Stadium", "Aquatic", "Training"]),
]

DEFAULT_RIVER = {
    "name": "Qiantang River",
    "path": [(0.2, 0.22), (0.35, 0.28), (0.52, 0.24), (0.7, 0.31), (0.92, 0.26)],
    "width": 0.085,
}

DEFAULT_METRO_LINES = [
    {"name": "M1", "color": "#8f5bd8", "stops": ["North Block", "Central Block", "Riverside Bus Station", "Financial District", "Central Station", "Airport District"]},
    {"name": "M2", "color": "#2b9ccf", "stops": ["University District", "Central Block", "City Hall", "Riverside Stadium", "Waterfront"]},
]

PROJECT_ROOT = Path(__file__).resolve().parent


def _resolve_existing_path(path):
    """Resolve moved data files while accepting legacy root-level paths."""
    target = Path(str(path))
    if target.exists():
        return str(target)
    if not target.is_absolute():
        repo_target = PROJECT_ROOT / target
        if repo_target.exists():
            return str(repo_target)
        data_target = PROJECT_ROOT / "data" / target.name
        if data_target.exists():
            return str(data_target)
    return str(target)


def _slug(text):
    return re.sub(r"\s+", " ", str(text or "").strip())


def _parse_directive_parts(text):
    parts = [part.strip() for part in str(text or "").split("|")]
    head = parts[0] if parts else ""
    attrs = {}
    for part in parts[1:]:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        attrs[key.strip().lower()] = value.strip()
    return head, attrs


def _float_attr(attrs, key, default=None):
    value = attrs.get(key)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def infer_category(name):
    label = _slug(name)
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword in label for keyword in keywords):
            return category
    return "mixed"


def _parse_map_file(map_path):
    map_path = _resolve_existing_path(map_path)
    parsed = {
        "hubs": [],
        "nodes": {},
        "roads": [],
        "metro_lines": [],
        "river": None,
    }
    if not os.path.exists(map_path):
        return parsed

    current_hub = None
    with open(map_path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("@"):  # explicit city-spec directives
                if line.startswith("@node:"):
                    head, attrs = _parse_directive_parts(line[len("@node:"):].strip())
                    name = _slug(head)
                    parsed["nodes"][name] = {
                        "name": name,
                        "kind": attrs.get("kind", "hub"),
                        "district": attrs.get("district", name),
                        "category": attrs.get("category", infer_category(name)),
                        "x": _float_attr(attrs, "x"),
                        "y": _float_attr(attrs, "y"),
                        "parent": attrs.get("parent", ""),
                    }
                elif line.startswith("@road:"):
                    head, attrs = _parse_directive_parts(line[len("@road:"):].strip())
                    if "->" in head:
                        source, target = [item.strip() for item in head.split("->", 1)]
                        parsed["roads"].append({
                            "source": _slug(source),
                            "target": _slug(target),
                            "road_type": attrs.get("type", "arterial"),
                            "bridge": attrs.get("bridge", "false").lower() == "true",
                        })
                elif line.startswith("@metro:"):
                    head, attrs = _parse_directive_parts(line[len("@metro:"):].strip())
                    stops = [ _slug(item) for item in attrs.get("stops", "").split(">") if _slug(item) ]
                    if stops:
                        parsed["metro_lines"].append({
                            "name": _slug(head) or f"M{len(parsed['metro_lines']) + 1}",
                            "color": attrs.get("color", "#8f5bd8"),
                            "stops": stops,
                        })
                elif line.startswith("@river:"):
                    head, attrs = _parse_directive_parts(line[len("@river:"):].strip())
                    raw_points = attrs.get("path", "")
                    points = []
                    for pair in raw_points.split(";"):
                        if not pair.strip() or "," not in pair:
                            continue
                        x_text, y_text = pair.split(",", 1)
                        try:
                            points.append((float(x_text.strip()), float(y_text.strip())))
                        except ValueError:
                            continue
                    parsed["river"] = {
                        "name": _slug(head) or DEFAULT_RIVER["name"],
                        "path": points or list(DEFAULT_RIVER["path"]),
                        "width": _float_attr(attrs, "width", DEFAULT_RIVER["width"]),
                    }
                continue

            hub_match = re.match(r"-\s*Hub:\s*(.+)", line)
            if hub_match:
                current_hub = {"name": _slug(hub_match.group(1).strip()), "nearby": []}
                parsed["hubs"].append(current_hub)
                continue
            nearby_match = re.match(r"-\s*Nearby:\s*(.+)", line)
            if nearby_match and current_hub is not None:
                current_hub["nearby"].append(_slug(nearby_match.group(1).strip()))
    return parsed


def load_city_map(map_path):
    parsed = _parse_map_file(map_path)
    return _build_city_map(
        parsed.get("hubs", []),
        explicit_nodes=parsed.get("nodes", {}),
        explicit_roads=parsed.get("roads", []),
        explicit_metro=parsed.get("metro_lines", []),
        explicit_river=parsed.get("river"),
    )


def load_city_map_text(map_path):
    map_path = _resolve_existing_path(map_path)
    if not os.path.exists(map_path):
        return ""
    try:
        with open(map_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _build_city_map(hubs, explicit_nodes=None, explicit_roads=None, explicit_metro=None, explicit_river=None):
    explicit_nodes = explicit_nodes or {}
    explicit_roads = explicit_roads or []
    explicit_metro = explicit_metro or []
    river = explicit_river or dict(DEFAULT_RIVER)
    nodes = {}
    hub_names = [item["name"] for item in hubs]
    cols = max(3, math.ceil(math.sqrt(max(len(hub_names), 1))))
    road_edges = []

    for index, hub in enumerate(hubs):
        row = index // cols
        col = index % cols
        default_x = 2.5 + col * 3.4
        default_y = 3.6 + row * 2.9
        node = _make_node_from_spec(
            hub["name"],
            explicit_nodes.get(hub["name"]),
            default_kind="hub",
            default_district=hub["name"],
            default_x=default_x,
            default_y=default_y,
        )
        nodes[node["id"]] = node

        nearby = hub.get("nearby", [])
        if not nearby:
            continue
        arc_step = (2 * math.pi) / max(len(nearby), 6)
        for near_index, place_name in enumerate(nearby):
            ring = near_index // 8
            radius = 0.75 + ring * 0.35
            angle = -math.pi / 2 + arc_step * near_index
            near_x = node["grid_x"] + math.cos(angle) * radius
            near_y = node["grid_y"] + math.sin(angle) * radius
            place_node = _make_node_from_spec(
                place_name,
                explicit_nodes.get(place_name),
                default_kind="place",
                default_district=node["name"],
                default_x=near_x,
                default_y=near_y,
                default_parent=node["id"],
            )
            nodes[place_node["id"]] = place_node
            road_edges.append(_make_edge(node["id"], place_node["id"], "local"))

    for name, spec in explicit_nodes.items():
        if _slug(name) in nodes:
            continue
        fallback_kind = spec.get("kind", "hub")
        district = spec.get("district", name)
        default_x = spec.get("x") if spec.get("x") is not None else 2.0
        default_y = spec.get("y") if spec.get("y") is not None else 2.0
        nodes[_slug(name)] = _make_node_from_spec(
            name,
            spec,
            default_kind=fallback_kind,
            default_district=district,
            default_x=default_x,
            default_y=default_y,
            default_parent=spec.get("parent", ""),
        )

    hub_ids = [node_id for node_id, node in nodes.items() if node["kind"] == "hub"]
    road_edges.extend(_connect_hubs(nodes, hub_ids))
    road_edges.extend(_normalize_explicit_roads(nodes, explicit_roads))
    road_edges = _dedupe_edges(road_edges)

    adjacency = _build_adjacency(nodes, road_edges)
    metro_lines = _normalize_metro_lines(nodes, explicit_metro or DEFAULT_METRO_LINES)
    bridges = _detect_bridges(nodes, road_edges, river)
    tile_map = _build_tile_map(nodes, road_edges, river=river, metro_lines=metro_lines, bridges=bridges)
    return {
        "nodes": nodes,
        "edges": road_edges,
        "adjacency": adjacency,
        "metro_lines": metro_lines,
        "river": river,
        "bridges": bridges,
        "tile_map": tile_map,
        "bounds": _compute_bounds(nodes),
        "scale": {"km_per_grid_x": KM_PER_GRID_X, "km_per_grid_y": KM_PER_GRID_Y},
    }


def _make_node_from_spec(name, spec, default_kind, default_district, default_x, default_y, default_parent=""):
    spec = spec or {}
    kind = spec.get("kind", default_kind)
    district = spec.get("district", default_district)
    grid_x = float(spec.get("x", default_x))
    grid_y = float(spec.get("y", default_y))
    parent = _slug(spec.get("parent", default_parent)) if spec.get("parent", default_parent) else ""
    x_km = grid_x * KM_PER_GRID_X
    y_km = grid_y * KM_PER_GRID_Y
    lat = BASE_LAT + y_km * LAT_PER_KM
    lng = BASE_LNG + x_km * LNG_PER_KM
    label = _slug(name)
    category = spec.get("category", infer_category(label))
    return {
        "id": label,
        "name": label,
        "label": label,
        "kind": kind,
        "district": district,
        "category": category,
        "parent": parent,
        "grid_x": round(grid_x, 3),
        "grid_y": round(grid_y, 3),
        "x_km": round(x_km, 3),
        "y_km": round(y_km, 3),
        "lat": round(lat, 6),
        "lng": round(lng, 6),
    }


def _euclidean_distance_km(a, b):
    dx = float(a["x_km"]) - float(b["x_km"])
    dy = float(a["y_km"]) - float(b["y_km"])
    return math.sqrt(dx * dx + dy * dy)


def _make_edge(source_id, target_id, road_type, bridge=False):
    return {"source": _slug(source_id), "target": _slug(target_id), "road_type": road_type, "bridge": bool(bridge)}


def _dedupe_edges(edges):
    seen = {}
    for edge in edges:
        key = (tuple(sorted((_slug(edge["source"]), _slug(edge["target"])))), edge.get("road_type", "road"))
        if key not in seen:
            seen[key] = edge
        elif edge.get("bridge"):
            seen[key]["bridge"] = True
    return list(seen.values())


def _connect_hubs(nodes, hub_ids):
    edges = []
    linked = set()
    sorted_hubs = sorted(hub_ids, key=lambda item: (nodes[item]["grid_y"], nodes[item]["grid_x"]))
    for idx, hub_id in enumerate(sorted_hubs):
        distances = []
        for other_id in sorted_hubs:
            if other_id == hub_id:
                continue
            dist = _euclidean_distance_km(nodes[hub_id], nodes[other_id])
            distances.append((dist, other_id))
        distances.sort(key=lambda item: item[0])
        for dist, other_id in distances[:3]:
            pair = tuple(sorted((hub_id, other_id)))
            if pair in linked:
                continue
            linked.add(pair)
            road_type = "arterial" if dist > 2.4 else "collector"
            edges.append(_make_edge(hub_id, other_id, road_type))
        if idx > 0:
            prev_id = sorted_hubs[idx - 1]
            pair = tuple(sorted((hub_id, prev_id)))
            if pair not in linked:
                linked.add(pair)
                edges.append(_make_edge(hub_id, prev_id, "arterial"))
    return edges


def _normalize_explicit_roads(nodes, roads):
    normalized = []
    for road in roads:
        source = _slug(road.get("source", ""))
        target = _slug(road.get("target", ""))
        if source in nodes and target in nodes and source != target:
            normalized.append(_make_edge(source, target, road.get("road_type", "arterial"), bridge=road.get("bridge", False)))
    return normalized


def _normalize_metro_lines(nodes, lines):
    normalized = []
    for idx, line in enumerate(lines or []):
        stops = []
        for stop in line.get("stops", []):
            stop_id = _slug(stop)
            if stop_id in nodes:
                stops.append(stop_id)
        if len(stops) >= 2:
            normalized.append({
                "name": _slug(line.get("name", f"M{idx + 1}")),
                "color": line.get("color", "#8f5bd8"),
                "stops": stops,
            })
    return normalized


def _build_adjacency(nodes, edges):
    adjacency = defaultdict(list)
    for edge in edges:
        source = nodes.get(edge["source"])
        target = nodes.get(edge["target"])
        if not source or not target:
            continue
        dist = _euclidean_distance_km(source, target)
        item = {"node": target["id"], "distance_km": round(dist, 3), "road_type": edge.get("road_type", "road"), "bridge": bool(edge.get("bridge", False))}
        adjacency[source["id"]].append(item)
        reverse = dict(item)
        reverse["node"] = source["id"]
        adjacency[target["id"]].append(reverse)
    return dict(adjacency)


def _compute_bounds(nodes):
    if not nodes:
        return {"min_x": 0.0, "min_y": 0.0, "max_x": 1.0, "max_y": 1.0}
    xs = [node["grid_x"] for node in nodes.values()]
    ys = [node["grid_y"] for node in nodes.values()]
    return {"min_x": min(xs) - 1.8, "min_y": min(ys) - 2.0, "max_x": max(xs) + 1.8, "max_y": max(ys) + 2.0}


def _river_polyline(bounds, river):
    points = river.get("path") or DEFAULT_RIVER["path"]
    out = []
    for px, py in points:
        x = bounds["min_x"] + float(px) * (bounds["max_x"] - bounds["min_x"])
        y = bounds["min_y"] + float(py) * (bounds["max_y"] - bounds["min_y"])
        out.append((x, y))
    return out


def _distance_point_to_segment(point, start, end):
    px, py = point
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def _distance_to_polyline(point, polyline):
    if len(polyline) < 2:
        return 999.0
    distances = []
    for idx in range(len(polyline) - 1):
        distances.append(_distance_point_to_segment(point, polyline[idx], polyline[idx + 1]))
    return min(distances) if distances else 999.0


def _edge_crosses_river(nodes, edge, river_polyline, river_width_grid):
    source = nodes.get(edge["source"])
    target = nodes.get(edge["target"])
    if not source or not target:
        return False
    mid = ((source["grid_x"] + target["grid_x"]) / 2.0, (source["grid_y"] + target["grid_y"]) / 2.0)
    return _distance_to_polyline(mid, river_polyline) <= river_width_grid * 1.2


def _detect_bridges(nodes, edges, river):
    bounds = _compute_bounds(nodes)
    river_polyline = _river_polyline(bounds, river)
    river_width_grid = float(river.get("width", DEFAULT_RIVER["width"])) * max(1.0, bounds["max_y"] - bounds["min_y"])
    bridges = []
    for edge in edges:
        if edge.get("bridge") or _edge_crosses_river(nodes, edge, river_polyline, river_width_grid):
            source = nodes.get(edge["source"])
            target = nodes.get(edge["target"])
            if not source or not target:
                continue
            bridges.append({
                "source": source["id"],
                "target": target["id"],
                "mid_x": round((source["grid_x"] + target["grid_x"]) / 2.0, 3),
                "mid_y": round((source["grid_y"] + target["grid_y"]) / 2.0, 3),
            })
    return bridges


def _build_tile_map(nodes, edges, river, metro_lines, bridges, width=160, height=112):
    terrain = [["ground" for _ in range(width)] for _ in range(height)]
    bounds = _compute_bounds(nodes)
    river_polyline = _river_polyline(bounds, river)
    river_width_tiles = max(3.0, float(river.get("width", DEFAULT_RIVER["width"])) * height)

    for row in range(height):
        for col in range(width):
            grid_x = bounds["min_x"] + (col / max(1, width - 1)) * (bounds["max_x"] - bounds["min_x"])
            grid_y = bounds["min_y"] + (row / max(1, height - 1)) * (bounds["max_y"] - bounds["min_y"])
            if _distance_to_polyline((grid_x, grid_y), river_polyline) <= river_width_tiles / max(1, height / (bounds["max_y"] - bounds["min_y"] + 1e-6)):
                terrain[row][col] = "water"
            elif row > height - 14:
                terrain[row][col] = "forest"

    for node in nodes.values():
        tx, ty = project_to_tile(node["grid_x"], node["grid_y"], bounds, width, height)
        terrain_type = _category_to_terrain(node["category"])
        _paint_blob(terrain, tx, ty, terrain_type, radius=5 if node["kind"] == "hub" else 3)

    for edge in edges:
        source = nodes.get(edge["source"])
        target = nodes.get(edge["target"])
        if not source or not target:
            continue
        start = project_to_tile(source["grid_x"], source["grid_y"], bounds, width, height)
        end = project_to_tile(target["grid_x"], target["grid_y"], bounds, width, height)
        symbol = "bridge" if edge.get("bridge") else "road"
        for col, row in _bresenham(start[0], start[1], end[0], end[1]):
            if 0 <= row < height and 0 <= col < width:
                if terrain[row][col] == "water" and not edge.get("bridge"):
                    continue
                terrain[row][col] = symbol

    metro_segments = []
    for line in metro_lines:
        for idx in range(len(line["stops"]) - 1):
            source = nodes.get(line["stops"][idx])
            target = nodes.get(line["stops"][idx + 1])
            if not source or not target:
                continue
            start = project_to_tile(source["grid_x"], source["grid_y"], bounds, width, height)
            end = project_to_tile(target["grid_x"], target["grid_y"], bounds, width, height)
            points = _bresenham(start[0], start[1], end[0], end[1])
            metro_segments.append({
                "line": line["name"],
                "color": line["color"],
                "points": points,
            })
            for col, row in points:
                if 0 <= row < height and 0 <= col < width and terrain[row][col] not in {"water", "bridge"}:
                    terrain[row][col] = "metro"

    bridge_tiles = []
    for bridge in bridges:
        tx, ty = project_to_tile(bridge["mid_x"], bridge["mid_y"], bounds, width, height)
        bridge_tiles.append({"x": tx, "y": ty, "source": bridge["source"], "target": bridge["target"]})

    return {
        "width": width,
        "height": height,
        "terrain": ["".join(_terrain_symbol(cell) for cell in row) for row in terrain],
        "bounds": bounds,
        "river_path": [project_to_tile(x, y, bounds, width, height) for x, y in river_polyline],
        "metro_segments": metro_segments,
        "bridge_tiles": bridge_tiles,
    }


def _terrain_symbol(value):
    return {
        "ground": ".",
        "road": "#",
        "bridge": "=",
        "water": "~",
        "forest": "*",
        "residential": "r",
        "commerce": "c",
        "education": "e",
        "medical": "m",
        "industry": "i",
        "government": "g",
        "leisure": "l",
        "transit": "t",
        "metro": "+",
        "mixed": "d",
    }.get(value, ".")


def _category_to_terrain(category):
    return {
        "residential": "residential",
        "commerce": "commerce",
        "education": "education",
        "medical": "medical",
        "industry": "industry",
        "government": "government",
        "leisure": "leisure",
        "transit": "transit",
    }.get(category, "mixed")


def _paint_blob(terrain, center_x, center_y, terrain_type, radius):
    height = len(terrain)
    width = len(terrain[0]) if height else 0
    for row in range(center_y - radius, center_y + radius + 1):
        for col in range(center_x - radius, center_x + radius + 1):
            if not (0 <= row < height and 0 <= col < width):
                continue
            dist = abs(col - center_x) + abs(row - center_y)
            if dist <= radius and terrain[row][col] not in {"road", "bridge", "water", "metro"}:
                terrain[row][col] = terrain_type


def _bresenham(x0, y0, x1, y1):
    points = []
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        points.append((x, y))
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy
    return points


def project_to_tile(grid_x, grid_y, bounds, width, height):
    span_x = max(0.001, bounds["max_x"] - bounds["min_x"])
    span_y = max(0.001, bounds["max_y"] - bounds["min_y"])
    px = int(round((float(grid_x) - bounds["min_x"]) / span_x * (width - 1)))
    py = int(round((float(grid_y) - bounds["min_y"]) / span_y * (height - 1)))
    return px, py


def all_locations(city_map):
    return list(city_map.get("nodes", {}).keys())


def node_by_name(city_map, name):
    if not name:
        return None
    nodes = city_map.get("nodes", {})
    key = _slug(name)
    if key in nodes:
        return nodes[key]
    for node in nodes.values():
        if node["name"] == key:
            return node
    return None


def distance_between(city_map, origin, target):
    source = node_by_name(city_map, origin)
    dest = node_by_name(city_map, target)
    if not source or not dest:
        return 0.0
    return round(_euclidean_distance_km(source, dest), 3)


def shortest_path(city_map, origin, target):
    nodes = city_map.get("nodes", {})
    adjacency = city_map.get("adjacency", {})
    start = node_by_name(city_map, origin)
    goal = node_by_name(city_map, target)
    if not start or not goal:
        return []
    if start["id"] == goal["id"]:
        return [start["name"]]
    pq = [(0.0, start["id"], [])]
    visited = set()
    while pq:
        cost, node_id, trail = heapq.heappop(pq)
        if node_id in visited:
            continue
        visited.add(node_id)
        next_trail = trail + [nodes[node_id]["name"]]
        if node_id == goal["id"]:
            return next_trail
        for edge in adjacency.get(node_id, []):
            if edge["node"] in visited:
                continue
            penalty = 0.0
            if edge.get("road_type") == "arterial":
                penalty = -0.03
            elif edge.get("road_type") == "local":
                penalty = 0.05
            heapq.heappush(pq, (cost + float(edge["distance_km"]) + penalty, edge["node"], next_trail))
    return [start["name"], goal["name"]]


def choose_transport_mode(agent, city_map, origin, target, activity=None,
                          weather=None):
    """Choose the best transport mode considering distance, profile, route,
    and weather conditions.

    Parameters
    ----------
    weather : str or None
        Weather key (rain/snow/hot/cold/clear).  When set, the initial
        rule-based mode choice is re-evaluated against weather-adjusted
        preference weights — if a sheltered alternative (bus/metro/taxi)
        scores significantly higher, the mode is upgraded.
    """
    distance_km = distance_between(city_map, origin, target)
    origin_node = node_by_name(city_map, origin)
    target_node = node_by_name(city_map, target)
    categories = {origin_node["category"] if origin_node else "",
                  target_node["category"] if target_node else ""}
    profile = " ".join([str(agent.get("job", "")),
                        str(agent.get("daily_life", "")),
                        str(agent.get("personality", ""))])
    route = shortest_path(city_map, origin, target)
    metro_stop_set = {stop for line in city_map.get("metro_lines", [])
                      for stop in line.get("stops", [])}
    route_uses_metro = (len(route) >= 2
                        and any(_slug(stop) in metro_stop_set for stop in route))

    # --- distance-based rule selection (baseline) ---
    if distance_km <= 0.35:
        mode = "walk"
    elif distance_km <= 1.2:
        mode = "walk" if any(k in profile for k in ["散步", "步行", "慢生活"]) else "bike"
    elif distance_km <= 3.2:
        mode = "e-bike"
    elif route_uses_metro and distance_km >= 3.0:
        mode = "metro"
    elif distance_km <= 6.0:
        mode = "bus" if "transit" in categories or "通勤" in str(activity or "") else "e-bike"
    elif distance_km <= 10.0:
        mode = "metro" if route_uses_metro or "transit" in categories else "car"
    else:
        mode = "taxi" if any(k in str(target or "") for k in ["Airport", "Rail", "Station"]) else "metro"

    # --- weather adjustment ---
    # If bad weather significantly penalises the chosen open-air mode,
    # upgrade to the best sheltered alternative that is feasible for the
    # distance.
    if weather and weather in WEATHER_MODE_ADJUSTMENTS:
        adj = WEATHER_MODE_ADJUSTMENTS[weather]
        mode_weight = adj.get(mode, 1.0)
        if mode_weight < 0.6:
            # Current mode is heavily penalised — find a better one.
            # Build a small candidate set appropriate for the distance.
            candidates = []
            if distance_km <= 6.0:
                candidates = ["bus", "metro", "taxi"]
            elif distance_km <= 15.0:
                candidates = ["metro", "car", "taxi"]
            else:
                candidates = ["metro", "taxi"]
            # Pick the candidate with the highest weather-adjusted weight
            # that is also reachable (metro needs stops on route).
            best_mode, best_w = mode, mode_weight
            for c in candidates:
                if c == "metro" and not route_uses_metro:
                    continue
                cw = adj.get(c, 1.0)
                if cw > best_w:
                    best_mode, best_w = c, cw
            mode = best_mode

    return mode, distance_km


def estimate_travel_minutes(mode, distance_km):
    spec = TRANSPORT_MODES.get(mode, TRANSPORT_MODES["walk"])
    travel = (max(0.05, float(distance_km)) / float(spec["speed_kmh"])) * 60.0
    return max(1, int(round(travel + float(spec["fixed_min"]))))


def travel_plan(agent, city_map, origin, target, activity=None,
                 time_str=None, weather=None):
    """Build a complete travel plan with cost, time, and route.

    Parameters
    ----------
    time_str : str or None
        Current time as "HH:MM" — used for rush-hour detection.
    weather : str or None
        Current weather condition key (rain/snow/hot/cold/clear).
    """
    mode, distance_km = choose_transport_mode(
        agent, city_map, origin, target, activity=activity, weather=weather)
    route = shortest_path(city_map, origin, target)
    minutes = estimate_travel_minutes(mode, distance_km)
    is_rush = is_rush_hour(time_str) if time_str else False
    if is_rush:
        minutes = max(1, int(round(minutes * RUSH_HOUR_TIME_MULT)))
    cost = calc_transport_cost(mode, distance_km, rush_hour=is_rush)
    return {
        "origin": _slug(origin),
        "destination": _slug(target),
        "distance_km": round(distance_km, 3),
        "mode": mode,
        "travel_minutes": minutes,
        "travel_cost": round(cost, 2),
        "rush_hour": is_rush,
        "route": route,
    }


# ===================================================================
# TRANSPORT COST CALCULATION
# ===================================================================

def calc_transport_cost(mode, distance_km, rush_hour=False, parking_hours=0.0):
    """Calculate the fare for a single trip in CNY.

    Parameters
    ----------
    mode : str
        Transport mode key (walk, bike, bus, metro, car, taxi, etc.).
    distance_km : float
        Trip distance in kilometres.
    rush_hour : bool
        Whether the trip occurs during rush hour (taxi surcharge).
    parking_hours : float
        For car mode, how many hours of parking to include.

    Returns
    -------
    float
        Total fare in CNY.
    """
    fare_spec = TRANSPORT_FARES.get(mode, TRANSPORT_FARES.get("walk", {}))
    base = float(fare_spec.get("base", 0.0))
    per_km = float(fare_spec.get("per_km", 0.0))
    free_km = float(fare_spec.get("free_km", 0.0))
    chargeable_km = max(0.0, float(distance_km) - free_km)
    cost = base + chargeable_km * per_km

    # Taxi rush-hour surcharge
    if mode == "taxi" and rush_hour:
        cost *= RUSH_HOUR_TAXI_SURCHARGE

    # Car parking cost
    if mode == "car" and parking_hours > 0:
        parking_rate = float(fare_spec.get("parking_per_hour", 6.0))
        cost += parking_hours * parking_rate

    return max(0.0, round(cost, 2))


def is_rush_hour(time_str):
    """Check if a HH:MM time string falls in a rush-hour period."""
    if not time_str or not isinstance(time_str, str):
        return False
    parts = time_str.strip().split(":")
    if len(parts) < 2:
        return False
    try:
        minutes = int(parts[0]) * 60 + int(parts[1])
    except (ValueError, TypeError):
        return False
    for start, end in RUSH_HOUR_PERIODS:
        if start <= minutes < end:
            return True
    return False


# ===================================================================
# SPATIAL QUERIES
# ===================================================================

def nearby_nodes(city_map, node_id, radius_km=2.0):
    """Return all nodes within *radius_km* of *node_id*, sorted by distance.

    Each result is a dict: {node, distance_km}.
    """
    nodes = city_map.get("nodes", {})
    origin = nodes.get(_slug(node_id))
    if not origin:
        return []
    results = []
    for nid, node in nodes.items():
        if nid == origin["id"]:
            continue
        dist = _euclidean_distance_km(origin, node)
        if dist <= radius_km:
            results.append({"node": nid, "distance_km": round(dist, 3)})
    results.sort(key=lambda x: x["distance_km"])
    return results


def nodes_by_category(city_map, category):
    """Return all node IDs matching a given category."""
    nodes = city_map.get("nodes", {})
    cat = category.lower().strip()
    return [nid for nid, node in nodes.items() if node.get("category", "").lower() == cat]


def nearest_by_category(city_map, node_id, category, top_k=3):
    """Find the closest *top_k* nodes of a given category to *node_id*.

    Returns list of (node_id, distance_km) tuples, sorted by distance.
    """
    nodes = city_map.get("nodes", {})
    origin = nodes.get(_slug(node_id))
    if not origin:
        return []
    cat = category.lower().strip()
    candidates = []
    for nid, node in nodes.items():
        if nid == origin["id"]:
            continue
        if node.get("category", "").lower() != cat:
            continue
        dist = _euclidean_distance_km(origin, node)
        candidates.append((nid, round(dist, 3)))
    candidates.sort(key=lambda x: x[1])
    return candidates[:top_k]


def area_price_level(city_map, node_id):
    """Return the consumption price-level multiplier for the area around *node_id*.

    Commerce / transit zones are pricier; industrial / education zones cheaper.
    """
    nodes = city_map.get("nodes", {})
    node = nodes.get(_slug(node_id))
    if not node:
        return 1.0
    category = node.get("category", "mixed")
    return AREA_PRICE_LEVEL.get(category, 1.0)


def area_price_level_by_name(city_map, location_name):
    """Convenience wrapper — look up price level by location name string."""
    node = node_by_name(city_map, location_name)
    if not node:
        return 1.0
    return AREA_PRICE_LEVEL.get(node.get("category", "mixed"), 1.0)


# ===================================================================
# ACTIVITY → CATEGORY MAPPING (for generic location resolution)
# ===================================================================

ACTIVITY_CATEGORY_MAP = {
    # activity keywords → preferred location categories, ordered by priority
    "工作":      ["commerce", "industry", "government"],
    "上班":      ["commerce", "industry", "government"],
    "加班":      ["commerce", "industry"],
    "开会":      ["commerce", "government"],
    "学习":      ["education"],
    "上课":      ["education"],
    "实验":      ["education", "industry"],
    "看病":      ["medical"],
    "医院":      ["medical"],
    "诊所":      ["medical"],
    "体检":      ["medical"],
    "健身":      ["leisure"],
    "锻炼":      ["leisure"],
    "晨练":      ["leisure"],
    "散步":      ["leisure", "residential"],
    "运动":      ["leisure"],
    "买菜":      ["commerce"],
    "购物":      ["commerce"],
    "逛街":      ["commerce"],
    "市场":      ["commerce"],
    "外卖":      ["commerce", "residential"],
    "电影":      ["leisure", "commerce"],
    "娱乐":      ["leisure", "commerce"],
    "休闲":      ["leisure"],
    "聚会":      ["leisure", "commerce"],
    "旅行":      ["leisure", "transit"],
    "通勤":      ["transit"],
    "出行":      ["transit"],
    "吃饭":      ["commerce", "residential"],
    "午饭":      ["commerce", "residential"],
    "晚饭":      ["commerce", "residential"],
    "咖啡":      ["commerce", "leisure"],
    "阅读":      ["education", "leisure"],
    "图书馆":    ["education"],
    "接送":      ["education", "residential"],
}

# Job keywords → workplace category preferences
JOB_WORKPLACE_CATEGORIES = {
    "学生":  ["education"],
    "硕士":  ["education"],
    "博士":  ["education"],
    "教师":  ["education"],
    "教授":  ["education"],
    "医生":  ["medical"],
    "护士":  ["medical"],
    "医疗":  ["medical"],
    "程序":  ["commerce", "industry"],
    "研发":  ["industry", "commerce"],
    "工程":  ["industry", "commerce"],
    "算法":  ["commerce", "industry"],
    "产品":  ["commerce"],
    "设计":  ["commerce"],
    "金融":  ["commerce"],
    "银行":  ["commerce"],
    "证券":  ["commerce"],
    "财务":  ["commerce"],
    "律师":  ["commerce", "government"],
    "公务":  ["government"],
    "警察":  ["government"],
    "消防":  ["government"],
    "物流":  ["industry"],
    "仓储":  ["industry"],
    "配送":  ["industry", "commerce"],
    "快递":  ["industry", "commerce"],
    "销售":  ["commerce"],
    "客服":  ["commerce"],
    "运营":  ["commerce"],
    "行政":  ["commerce", "government"],
    "退休":  ["residential", "leisure"],
    "无业":  ["residential"],
    "待业":  ["residential"],
    "失业":  ["residential"],
    "自由":  ["residential", "commerce"],
}


def activity_to_categories(activity_text):
    """Map an activity description to a list of preferred location categories."""
    text = str(activity_text or "")
    categories = []
    for keyword, cats in ACTIVITY_CATEGORY_MAP.items():
        if keyword in text:
            for c in cats:
                if c not in categories:
                    categories.append(c)
    return categories if categories else ["mixed"]


def job_to_workplace_categories(job_text):
    """Map a job description to workplace category preferences."""
    text = str(job_text or "")
    categories = []
    for keyword, cats in JOB_WORKPLACE_CATEGORIES.items():
        if keyword in text:
            for c in cats:
                if c not in categories:
                    categories.append(c)
    return categories if categories else ["commerce"]


def resolve_best_location(city_map, current_node_id, categories, top_k=5,
                          max_radius_km=15.0, prefer_closer=True):
    """Find the best location matching any of the given categories.

    Searches outward from *current_node_id*, preferring closer nodes.
    Returns a list of (node_id, distance_km) candidates.
    """
    nodes = city_map.get("nodes", {})
    origin = nodes.get(_slug(current_node_id))
    if not origin:
        return []

    candidates = []
    cat_set = set(c.lower().strip() for c in categories)
    for nid, node in nodes.items():
        if nid == origin["id"]:
            continue
        if node.get("category", "").lower() not in cat_set:
            continue
        dist = _euclidean_distance_km(origin, node)
        if dist <= max_radius_km:
            candidates.append((nid, round(dist, 3)))

    if prefer_closer:
        candidates.sort(key=lambda x: x[1])
    else:
        # Weighted random: closer nodes have higher weight
        import random as _rnd
        _rnd.shuffle(candidates)
        candidates.sort(key=lambda x: x[1] + _rnd.uniform(0, x[1] * 0.5))

    return candidates[:top_k]
