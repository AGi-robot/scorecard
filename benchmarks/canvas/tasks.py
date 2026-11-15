"""CanvasBench-style task set for Grace's vector canvas.

Each task is a brief a user could actually send Grace, plus per-task checks
that run against the resulting scene graph (the list of normalised objects the
canvas renderer replays). Checks return (ok, detail) so failures explain
themselves in the report.
"""
from __future__ import annotations

import colorsys

CANVAS_W, CANVAS_H = 1000, 650


# ---------------------------------------------------------------- colour ---
def _rgb(hex_colour):
    h = hex_colour.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def hue_of(hex_colour):
    r, g, b = _rgb(hex_colour)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360, s, l


def has_hue(colours, low, high, min_sat=0.15, min_light=0.06, max_light=0.97):
    """True when any colour in the scene sits in the given hue band."""
    for c in colours:
        try:
            hue, sat, light = hue_of(c)
        except Exception:
            continue
        if sat < min_sat or light < min_light or light > max_light:
            continue
        if low <= hue <= high:
            return True
    return False


def is_warm(colours):
    return has_hue(colours, 0, 45) or has_hue(colours, 330, 360)


# ------------------------------------------------------------ scene graph ---
def bounds_of(obj):
    """(x, y, w, h) for any canvas object, or None when it has no geometry.

    Only curve/path/polygon are described by points. A rectangle or ellipse
    may carry a stray points array too -- trust its rect, not the points.
    """
    kind = obj.get("kind")
    if kind in ("curve", "path", "polygon") and obj.get("points"):
        xs = [p[0] for p in obj["points"]]
        ys = [p[1] for p in obj["points"]]
        return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
    if "x" in obj and "y" in obj:
        w = obj.get("width", obj.get("size", 10))
        h = obj.get("height", obj.get("size", 10))
        return (obj["x"], obj["y"], w, h)
    if obj.get("points"):
        xs = [p[0] for p in obj["points"]]
        ys = [p[1] for p in obj["points"]]
        return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
    return None


def scene_colours(scene):
    out = []
    for obj in scene["objects"]:
        for key in ("fill_color", "color", "gradient_color"):
            if isinstance(obj.get(key), str) and obj[key].startswith("#"):
                out.append(obj[key])
    return out


def scene_kinds(scene):
    return [o.get("kind", "?") for o in scene["objects"]]


def scene_texts(scene):
    return [o.get("text", "") for o in scene["objects"] if o.get("text")]


def coverage(scene):
    """Fraction of the canvas covered by object bounding boxes (clipped)."""
    total = 0.0
    for obj in scene["objects"]:
        b = bounds_of(obj)
        if not b:
            continue
        x, y, w, h = b
        x0, y0 = max(0.0, x), max(0.0, y)
        x1, y1 = min(CANVAS_W, x + w), min(CANVAS_H, y + h)
        if x1 > x0 and y1 > y0:
            total += (x1 - x0) * (y1 - y0)
    return total / (CANVAS_W * CANVAS_H)


def mean_overlap(scene):
    """Mean pairwise IoU of object bounding boxes."""
    boxes = [b for b in (bounds_of(o) for o in scene["objects"]) if b]
    if len(boxes) < 2:
        return 0.0
    total, pairs = 0.0, 0
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            ax, ay, aw, ah = boxes[i]
            bx, by, bw, bh = boxes[j]
            ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
            iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
            inter = ix * iy
            union = aw * ah + bw * bh - inter
            total += inter / union if union > 0 else 0.0
            pairs += 1
    return total / pairs if pairs else 0.0


def shared_baseline(scene, tolerance=10):
    """Largest group of objects whose top edges agree -- a rhythm proxy."""
    tops = []
    for obj in scene["objects"]:
        b = bounds_of(obj)
        if b and obj.get("kind") not in ("select", "style", "front", "back"):
            tops.append(round(b[1]))
    if not tops:
        return 0
    best = 1
    for anchor in set(tops):
        group = sum(1 for t in tops if abs(t - anchor) <= tolerance)
        best = max(best, group)
    return best


def even_spacing(scene, tolerance=14):
    """Largest run of objects with even horizontal gaps -- spacing rhythm."""
    boxes = sorted((b for b in (bounds_of(o) for o in scene["objects"])
                    if b and b[2] > 0), key=lambda b: b[0])
    if len(boxes) < 3:
        return 0
    best = 2
    for i in range(len(boxes) - 2):
        gaps = []
        for j in range(i, len(boxes) - 1):
            gap = boxes[j + 1][0] - (boxes[j][0] + boxes[j][2])
            gaps.append(gap)
            if len(gaps) >= 2:
                lo, hi = min(gaps[-2:]), max(gaps[-2:])
                if hi - lo <= tolerance:
                    best = max(best, len(gaps) + 1)
    return best


def _named(fn, name):
    fn.check_name = name
    return fn


# ----------------------------------------------------------------- checks ---
def _objects_at_least(n):
    def check(scene):
        count = len(scene["objects"])
        return count >= n, f"{count} objects (need >= {n})"
    return _named(check, f"objects_at_least_{n}")


def _has_hue(low, high, label):
    def check(scene):
        colours = scene_colours(scene)
        ok = has_hue(colours, low, high)
        return ok, f"colours={colours} ({label} band {low}-{high})"
    return _named(check, f"has_hue_{label}")


def _coverage_between(lo, hi):
    def check(scene):
        cov = coverage(scene)
        return lo <= cov <= hi, f"coverage {cov:.1%} (want {lo:.0%}-{hi:.0%})"
    return _named(check, 'coverage_between')


def _overlap_below(limit):
    def check(scene):
        ov = mean_overlap(scene)
        return ov <= limit, f"mean bbox overlap {ov:.2f} (limit {limit})"
    return _named(check, 'overlap_below')


def _baseline_at_least(n):
    def check(scene):
        group = shared_baseline(scene)
        return group >= n, f"{group} objects share a baseline (need {n})"
    return _named(check, 'baseline_at_least')


def _spacing_at_least(n):
    def check(scene):
        run = even_spacing(scene)
        return run >= n, f"evenly spaced run of {run} (need {n})"
    return _named(check, 'spacing_at_least')


def _wide_element(fraction=0.5):
    def check(scene):
        wide = [o for o in scene["objects"]
                if (b := bounds_of(o)) and b[2] >= CANVAS_W * fraction]
        return bool(wide), f"{len(wide)} element(s) spanning >= {fraction:.0%} of width"
    return _named(check, 'wide_element')


def _has_text(fragment=None):
    def check(scene):
        texts = scene_texts(scene)
        if not texts:
            return False, "no text objects"
        if fragment:
            hit = any(fragment.lower() in t.lower() for t in texts)
            return hit, f"texts={texts}"
        return True, f"texts={texts}"
    return _named(check, 'has_text')


def _no_white_background():
    def check(scene):
        for obj in scene["objects"]:
            c = (obj.get("fill_color") or obj.get("color") or "").lower()
            if c.startswith("#") and c in ("#ffffff", "#fdfdfd", "#fefefe"):
                r, g, b = _rgb(c)
                if min(r, g, b) > 0.97:
                    return False, "drew a near-white background (canvas is already white)"
        return True, "ok"
    return _named(check, 'no_white_background')


def _edit_referenced_ids(ids):
    def check(scene, actions=None):
        used = {a.get("id") for a in (actions or []) if a.get("kind") in
                ("style", "move", "delete", "select", "front", "back")}
        hit = used & set(ids)
        return bool(hit), f"edited ids={sorted(used)} (want one of {ids})"
    return _named(check, 'edit_referenced_ids')


def _no_clear():
    def check(scene, actions=None):
        clears = [a for a in (actions or []) if a.get("kind") == "clear"]
        return not clears, f"{len(clears)} clear action(s)"
    return _named(check, 'no_clear')


# ------------------------------------------------------------------ tasks ---
# Tier 1: single subject -- does it produce a real silhouette?
# Tier 2: multi-object scene -- composition and light.
# Tier 3: layout -- the Framer-Navigation analog: rhythm, alignment, hierarchy.
# Tier 4: edit -- modify existing work instead of repainting it.
# Tier 5: self-critique -- draft, look at the render, improve it (scored on delta).

TASKS = [
    {
        "id": "T1-apple",
        "tier": 1,
        "brief": "Draw a single red apple with a short brown stem and one green leaf, "
                 "sitting slightly left of centre.",
        "checks": [
            _objects_at_least(3),
            _has_hue(340, 20, "red"),
            _has_hue(70, 160, "green"),
            _coverage_between(0.01, 0.35),
            _overlap_below(0.45),
            _no_white_background(),
        ],
    },
    {
        "id": "T1-lighthouse",
        "tier": 1,
        "brief": "Draw a lighthouse standing on a rocky headland at dusk, with a "
                 "warm lamp glow at the top.",
        "checks": [
            _objects_at_least(4),
            _has_hue(20, 50, "warm lamp"),
            _has_hue(200, 260, "cool dusk"),
            _coverage_between(0.02, 0.6),
            _overlap_below(0.5),
        ],
    },
    {
        "id": "T2-still-life",
        "tier": 2,
        "brief": "A still life: a red apple and a ceramic cup on a wooden table, soft "
                 "morning light from the left casting a warm shadow to the right.",
        "checks": [
            _objects_at_least(4),
            _has_hue(340, 20, "apple red"),
            _has_hue(20, 45, "warm wood"),
            _wide_element(0.45),
            _coverage_between(0.03, 0.7),
            _overlap_below(0.5),
        ],
    },
    {
        "id": "T2-robot-mascot",
        "tier": 2,
        "brief": "A friendly little robot mascot standing on a workbench in a garage, "
                 "with a teal body, an amber status light and cables trailing off the bench.",
        "checks": [
            _objects_at_least(5),
            _has_hue(150, 200, "teal"),
            _has_hue(30, 60, "amber"),
            _coverage_between(0.03, 0.7),
            _overlap_below(0.5),
        ],
    },
    {
        "id": "T3-navbar",
        "tier": 3,
        "brief": "A navigation bar across the top of the canvas: a round logo mark on the "
                 "far left, then four evenly spaced menu items reading Home, Work, Journal "
                 "and Contact.",
        "checks": [
            _objects_at_least(6),
            _baseline_at_least(5),
            _spacing_at_least(4),
            _has_text("Home"),
            _has_text("Contact"),
            _wide_element(0.5),
            _coverage_between(0.01, 0.5),
        ],
    },
    {
        "id": "T3-poster",
        "tier": 3,
        "brief": "A minimal event poster: a bold title word high on the canvas, a thin "
                 "horizontal rule beneath it, and a small date line lower down.",
        "checks": [
            _objects_at_least(4),
            _has_text(),
            _baseline_at_least(2),
            _coverage_between(0.005, 0.4),
            _overlap_below(0.4),
        ],
    },
    {
        "id": "T4-recolour-leaf",
        "tier": 4,
        "brief": "Make the leaf a brighter green.",
        "seed_actions": [
            {"kind": "curve", "id": "apple_body",
             "points": [[430, 300], [350, 200], [400, 120], [520, 110], [560, 220], [520, 320], [430, 300]],
             "fill": True, "stroke": False, "fill_color": "#c0392b"},
            {"kind": "curve", "id": "leaf",
             "points": [[500, 140], [540, 80], [620, 70], [600, 130], [530, 160], [500, 140]],
             "fill": True, "stroke": False, "fill_color": "#4a6b3a"},
            {"kind": "rectangle", "id": "stem", "x": 470, "y": 80, "width": 14, "height": 45,
             "fill": True, "stroke": False, "fill_color": "#6b4a2f"},
        ],
        "checks": [
            _edit_referenced_ids(["leaf"]),
            _no_clear(),
            _objects_at_least(3),
            _has_hue(70, 170, "green leaf"),
        ],
    },
    {
        "id": "T5-critique-self",
        "tier": 5,
        "brief": "Draw a small cabin in a snowy pine forest at night, with warm light "
                 "spilling from one window.",
        "checks": [
            _objects_at_least(4),
            _has_hue(20, 55, "warm window light"),
            _has_hue(200, 265, "cold night"),
            _coverage_between(0.02, 0.6),
        ],
    },
]

TIERS = {1: "single subject", 2: "multi-object scene", 3: "layout & hierarchy",
         4: "edit existing work", 5: "draft then self-critique"}
