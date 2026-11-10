"""Counting with an AI model that outlines things in a picture (MobileSAM, run on the computer's processor).

How it counts:
1. The model reads the picture once (about half a second).
2. Then it's asked "what is here?" at points across the picture. Each answer is the outline of the thing at
   that point, at up to three sizes: a part, the thing, or a group of things (about 0.03 s per question).
3. Outlines that look alike (size, colour, shape) are the things counted. With a measured example, the ones
   like the example; without one, the biggest family of alike outlines.

What counts as one (a berry or a whole bunch) is the count mode the person picks; it decides which of the
outline sizes are wanted, how irregular they may be, and how densely the picture is asked.

Tested on the team's 59 hand-counted pictures: with one fruit measured, 49 within 10% and 35 exact;
fully automatic, 44 within 10% (the counter without the model: 27 within 10%).
"""
import sys
import threading
from pathlib import Path

import cv2
import numpy as np

ENCODER = "mobile_sam_image_encoder.onnx"
DECODER = "sam_mask_decoder_multi.onnx"
SIDE = 1024             # the model reads pictures at this size (longest side)
LOW = 4                 # its outlines come at a quarter of that

# What to count: id -> (product, one, many, kind). The kind decides how the outlines are chosen.
MODES = {
    "pieces": ("Fruit & vegetables", "piece", "pieces", "whole"),
    "grape-berries": ("Grapes", "berry", "berries", "part"),
    "grape-bunches": ("Grapes", "bunch", "bunches", "group"),
    "banana-fingers": ("Bananas", "finger", "fingers", "part"),
    "banana-hands": ("Bananas", "hand", "hands", "group"),
    "vine-tomatoes": ("Tomatoes on the vine", "tomato", "tomatoes", "part"),
    "vine-trusses": ("Tomatoes on the vine", "truss", "trusses", "group"),
    "punnet-berries": ("Berries in punnets", "berry", "berries", "part"),
    "punnets": ("Berries in punnets", "punnet", "punnets", "group"),
    "asparagus": ("Asparagus, from the cut ends", "spear", "spears", "part"),
    "heads": ("Cauliflower, broccoli, lettuce", "head", "heads", "head"),
}
DEFAULT_MODE = "pieces"

# grid: questions across the longest side for the first look, when nothing is measured. step: when asking
# closely, points are this many sizes of one thing apart. solidity: how much of its convex hull an outline must
# fill (a bunch is ragged, an apple is not). biggest: the largest share of the picture one thing may take.
# prefer: which family wins without an example (many small ones, or most area covered).
# level: which of the outlines at a point are wanted (a berry is the smallest; groups: see below).
KINDS = {
    "part": {"grid": 12, "step": 0.9, "solidity": 0.75, "biggest": 0.06, "prefer": "many", "level": "smallest"},
    "whole": {"grid": 12, "step": 0.6, "solidity": 0.75, "biggest": 0.25, "prefer": "balanced", "level": "any"},
    "head": {"grid": 12, "step": 0.6, "solidity": 0.55, "biggest": 0.4, "prefer": "balanced", "level": "any"},
    "group": {"grid": 0, "step": 0.6, "solidity": 0.35, "biggest": 0.4, "prefer": "balanced", "level": "box"},
}
# A group (a bunch, a punnet) is asked about with a box of its size, not a point: at a point on touching bunches
# the model answers "this berry" or "all the grapes", never "this bunch". So a group needs one measured first,
# for its size. Its outline is ragged, so less sharp.
GROUP_SHARPNESS = 0.45
BOX_EDGE = 0.15                  # an outline along more of its box's edge than this is a cut piece, not a group
GREY_WEIGHT, FULL_COLOUR = 0.2, 12.0  # without an example, grey families count less, up to this much colour
SWEEP, SWEEP_MEASURED = 1.0, 1.6   # after the likely middles, a sweep this many steps apart finds any missed
                                  # (a measured example finds its likely middles better, so looser)
MIN_IOU, MIN_STABILITY = 0.7, 0.8      # the model's own confidence in an outline, and how sharp its edge is

_lock = threading.Lock()
_sessions = None


def _folder():
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "models"


def available():
    """True when the model files are there (the counter falls back to the plain one otherwise)."""
    return all((_folder() / name).exists() for name in (ENCODER, DECODER))


def _models():
    global _sessions
    with _lock:
        if _sessions is None:
            import onnxruntime as ort
            options = ort.SessionOptions()
            options.add_session_config_entry("session.set_denormal_as_zero", "1")
            make = lambda name: ort.InferenceSession(str(_folder() / name), options, providers=["CPUExecutionProvider"])
            _sessions = make(ENCODER), make(DECODER)
        return _sessions


def mode_list():
    """The modes for the screen: [{id, product, one, many}] in order."""
    return [{"id": k, "product": p, "one": one, "many": many, "measure": needs_example(k)}
            for k, (p, one, many, _) in MODES.items()]


def needs_example(mode):
    """Groups (bunches, punnets...) are only counted with one of them measured."""
    return KINDS[MODES.get(mode, MODES[DEFAULT_MODE])[3]]["level"] == "box"


class Picture:
    """A picture as the model has read it; asking it about points is quick, and answers are kept."""

    def __init__(self, rgb):
        encoder, self._decoder = _models()
        h, w = rgb.shape[:2]
        self.scale = SIDE / max(h, w)
        rw, rh = round(w * self.scale), round(h * self.scale)
        small = cv2.resize(rgb, (rw, rh), interpolation=cv2.INTER_AREA)
        self.embedding = encoder.run(None, {"input_image": small.astype(np.float32)})[0]
        self.lw, self.lh = -(-rw // LOW), -(-rh // LOW)
        self.lab = cv2.cvtColor(cv2.resize(rgb, (self.lw, self.lh), interpolation=cv2.INTER_AREA),
                                cv2.COLOR_RGB2LAB).astype(np.float32)
        self.area = self.lw * self.lh
        self._answers = {}

    def outlines(self, x, y, box=None):
        """The outlines at a point, or in a box (w, h) centred there (outline pixels), as dicts, smallest first;
        only confident ones."""
        key = (int(x), int(y)) + ((int(box[0]), int(box[1])) if box else ())
        if key not in self._answers:
            if box:
                x0, y0 = (key[0] - key[2] / 2) * LOW, (key[1] - key[3] / 2) * LOW
                x1, y1 = (key[0] + key[2] / 2) * LOW, (key[1] + key[3] / 2) * LOW
                points, labels = [[x0, y0], [x1, y1]], [2, 3]          # a box: its corners
            else:
                points, labels = [[key[0] * LOW + 2, key[1] * LOW + 2], [0, 0]], [1, -1]
            feed = {"image_embeddings": self.embedding,
                    "point_coords": np.array([points], np.float32),
                    "point_labels": np.array([labels], np.float32),
                    "mask_input": np.zeros((1, 1, 256, 256), np.float32),
                    "has_mask_input": np.zeros(1, np.float32),
                    "orig_im_size": np.array([64, 64], np.float32)}
            _, iou, low = self._decoder.run(None, feed)
            found = []
            for i in range(low.shape[1]):
                logit = low[0, i, :self.lh, :self.lw]
                mask = logit > 0
                area = int(mask.sum())
                if area < 3:
                    continue
                sharp = (logit > 1).sum() / max(1, (logit > -1).sum())
                if iou[0, i] >= MIN_IOU and sharp >= (GROUP_SHARPNESS if box else MIN_STABILITY):
                    found.append(self._shape(mask, area, float(iou[0, i]) * float(sharp)))
            found.sort(key=lambda s: s["area"])
            self._answers[key] = found
        return self._answers[key]

    def _shape(self, mask, area, score):
        ys, xs = np.nonzero(mask)
        contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        hull = cv2.contourArea(cv2.convexHull(max(contours, key=cv2.contourArea)))
        return {"mask": mask, "area": area, "score": score, "lab": self.lab[mask].mean(0),
                "x": xs.mean(), "y": ys.mean(), "solidity": area / max(1.0, hull),
                "w": xs.max() - xs.min() + 1, "h": ys.max() - ys.min() + 1}


def _overlap(a, b):
    return np.count_nonzero(a["mask"] & b["mask"]) / min(a["area"], b["area"])


def _one_each(shapes, limit=0.3):
    """Drop outlines that mostly overlap a better one, so each thing is counted once."""
    kept = []
    for s in sorted(shapes, key=lambda s: -s["score"]):
        if all(_overlap(s, k) <= limit for k in kept):
            kept.append(s)
    return kept


def _colour_distance(a, b):
    return float(np.linalg.norm((a - b) * np.array([0.5, 1, 1])))       # lightness matters less than colour


def _like(shapes, ref, kind, sensitivity):
    size_range = 1.6 + sensitivity
    colour_range = 14 + 20 * sensitivity
    out = [s for s in shapes
           if ref["area"] / size_range <= s["area"] <= ref["area"] * size_range
           and _colour_distance(s["lab"], ref["lab"]) <= colour_range
           and s["solidity"] >= kind["solidity"]]
    return _one_each(out)


def _on_box_edge(mask, x, y, box):
    """How much of a box's edge (inside the picture) the outline runs along. A cut piece of the table or of a
    pile runs along it; a thing that fits in the box doesn't."""
    h, w = mask.shape
    x0, x1 = int(round(x - box[0] / 2)), int(round(x + box[0] / 2))
    y0, y1 = int(round(y - box[1] / 2)), int(round(y + box[1] / 2))
    on = total = 0
    for row in (y0, y1):
        if 0 < row < h - 1 and max(0, x0) < min(w, x1):
            line = mask[row, max(0, x0):min(w, x1)]
            on, total = on + line.sum(), total + line.size
    for col in (x0, x1):
        if 0 < col < w - 1 and max(0, y0) < min(h, y1):
            line = mask[max(0, y0):min(h, y1), col]
            on, total = on + line.sum(), total + line.size
    return on / total if total else 0.0


def _grid(pic, step):
    return [(int(x), int(y)) for y in np.arange(step / 2, pic.lh, step) for x in np.arange(step / 2, pic.lw, step)]


def _likely_centres(pic, ref, sensitivity):
    """Where things like the example probably are: the middles of round spots of its colour and size (each
    thing is lit from above, so its middle is the brightest). Cheap; the model then checks each one."""
    distance = np.linalg.norm((pic.lab - ref["lab"]) * np.array([0.5, 1, 1]), axis=2)
    similar = np.exp(-(distance / (14 + 20 * sensitivity)) ** 2) * (0.3 + 0.7 * pic.lab[..., 0] / 255)
    r = max(1.0, np.sqrt(ref["area"] / np.pi))
    blobs = cv2.GaussianBlur(similar, (0, 0), max(0.7, r * 0.5)) - cv2.GaussianBlur(similar, (0, 0), max(1.4, r * 1.2))
    size = max(3, int(r * 1.2) | 1)
    peaks = (blobs >= cv2.dilate(blobs, np.ones((size, size), np.uint8))) & (blobs > 0.02)
    ys, xs = np.nonzero(peaks)
    order = np.argsort(-blobs[ys, xs])
    return [(int(xs[i]), int(ys[i])) for i in order]


def _ask_across(pic, kind, points, wanted=None, box=None):
    """Ask about points (or a grid `points` low-res pixels apart) in turn; a point inside an outline found
    already is skipped. wanted: optional mask of where asking is worth it (the example's colour). box: (w, h)
    to ask about boxes of that size instead of points (groups)."""
    if not isinstance(points, list):
        points = _grid(pic, points)
    covered = np.zeros((pic.lh, pic.lw), bool)
    biggest = kind["biggest"] * pic.area
    found = []
    for x, y in points:
        if covered[y, x] or (wanted is not None and not wanted[y, x]):
            continue
        shapes = [s for s in pic.outlines(x, y, box) if s["area"] <= biggest]
        if box:
            # the outline that fills the box best; small things inside it (a berry) aren't the group
            shapes = [s for s in shapes if s["area"] >= 0.2 * box[0] * box[1]
                      and _on_box_edge(s["mask"], x, y, box) <= BOX_EDGE]
            shapes = sorted(shapes, key=lambda s: abs(np.log(s["area"] / (0.7 * box[0] * box[1]))))[:1]
        if shapes:
            # a group is skipped as a whole once found; a single thing only by its smallest outline
            covered |= shapes[0]["mask"]
            if kind["level"] == "smallest":
                shapes = shapes[:1]
        covered[max(0, y - 1):y + 2, max(0, x - 1):x + 2] = True
        found += shapes
    return found


def _typical(shapes, kind, sensitivity):
    """Without an example: the outline at the heart of the biggest family of alike outlines, to use as one."""
    shapes = [s for s in shapes if s["solidity"] >= kind["solidity"] and s["area"] >= 6]
    if len(shapes) < 2:
        return None
    area = np.array([s["area"] for s in shapes], float)
    lab = np.array([s["lab"] for s in shapes])
    size_alike = np.abs(np.log(area[:, None] / area[None, :])) <= np.log(1.6 + sensitivity * 0.7)
    colour_alike = np.linalg.norm((lab[:, None] - lab[None, :]) * np.array([0.5, 1, 1]), axis=2) <= 14 + 14 * sensitivity
    alike = size_alike & colour_alike
    n = alike.sum(1).astype(float)
    cover = alike @ area
    value = {"many": n * np.sqrt(cover), "balanced": cover * np.sqrt(n), "area": cover}[kind["prefer"]]
    # trays, crates, cells and shadows are grey; produce nearly always has some colour (cauliflower too)
    colour = np.hypot(lab[:, 1] - 128, lab[:, 2] - 128)
    value *= np.clip(colour / FULL_COLOUR, GREY_WEIGHT, 1.0) ** 2
    value[n < 2] = 0
    best = int(np.argmax(value))
    return shapes[best] if value[best] > 0 else None


def count(pic, mode=DEFAULT_MODE, example=None, sensitivity=0.7):
    """Count on a Picture. example: (x0, y0, x1, y1) across one thing, in the picture's pixels.
    Without it, a quick look across the picture finds the most common kind of thing, which then serves as
    the example (not for groups: see needs_example). Returns ([(x, y)] in the picture's pixels, diameter of
    one thing in the picture's pixels)."""
    kind = KINDS[MODES.get(mode, MODES[DEFAULT_MODE])[3]]
    k = pic.scale / LOW                                              # picture pixels -> outline pixels
    if example:
        x0, y0, x1, y1 = (float(v) * k for v in example)
        cx, cy = min(pic.lw - 1, (x0 + x1) / 2), min(pic.lh - 1, (y0 + y1) / 2)
        r = max(1.0, np.hypot(x1 - x0, y1 - y0) / 2)
        box = (2 * r, 2 * r) if kind["level"] == "box" else None
        here = [s for s in pic.outlines(cx, cy, box) if s["area"] <= kind["biggest"] * pic.area] or pic.outlines(cx, cy, box)
        if not here:
            return [], 2 * r / k
        ref = min(here, key=lambda s: abs(np.log(s["area"] / (np.pi * r * r))))
    elif kind["level"] == "box":
        return [], 0.0
    else:
        ref = _typical(_ask_across(pic, kind, max(pic.lw, pic.lh) / kind["grid"]), kind, sensitivity)
    if ref is None:
        return [], 0.0
    # ask again more closely, only where the colour is anything like the example's (not for groups:
    # a bunch's outline holds stems and gaps too)
    wanted = None
    if kind["level"] != "box":
        distance = np.linalg.norm((pic.lab - ref["lab"]) * np.array([0.5, 1, 1]), axis=2)
        wanted = cv2.dilate((distance <= 2 * (14 + 20 * sensitivity)).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    step = float(np.clip(np.sqrt(ref["area"]) * kind["step"], pic.lw / 80, pic.lw / 12))
    if kind["level"] == "box":
        points, box = _grid(pic, step), (ref["w"] * 1.1, ref["h"] * 1.1)
    else:   # first where things probably are, then a looser sweep for any missed
        points, box = _likely_centres(pic, ref, sensitivity) + _grid(pic, step * (SWEEP_MEASURED if example else SWEEP)), None
    found = _like(_ask_across(pic, kind, points, wanted, box) + [ref], ref, kind, sensitivity)
    points = [((s["x"] + 0.5) / k, (s["y"] + 0.5) / k) for s in found]
    diameter = 2 * np.sqrt(np.median([s["area"] for s in found]) / np.pi) / k
    return points, float(diameter)
