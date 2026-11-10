"""Finds round fruit in a picture, without any window. Used by the Fruit Counter.

It looks for round bright bumps of about one fruit's size, which also works in a full box where no
background is visible: every fruit is lit from above and the gaps between them are darker. When the
fruit does stand out from a background, the shape of that area is used too, so touching fruit separate
and things on the table don't count.

It's a first count to correct, not a final answer: the person checks the marks on the picture.
"""
import math

import cv2
import numpy as np

MAX_SIDE = 1600        # bigger pictures are reduced for detection, the marks are scaled back
SPACING = 0.72         # two marks are at least this many fruit diameters apart
KEEP_STRICT, KEEP_LOOSE = 0.85, 0.10   # a mark must reach this share of a typical fruit, at sensitivity 0 and 1


def load_rgb(path):
    """A picture as an RGB array, turned the way it was taken (phone pictures)."""
    from PIL import Image, ImageOps
    with Image.open(path) as img:
        return np.array(ImageOps.exif_transpose(img).convert("RGB"))


def foreground(lab):
    """(mask of what isn't background, True if a background was found). A full box has none: its edge
    is a mix of fruit and gaps, while a real table or tray looks the same all along the edge."""
    h, w = lab.shape[:2]
    band = max(2, min(h, w) // 40)
    border = np.concatenate([lab[:band].reshape(-1, 3), lab[-band:].reshape(-1, 3),
                             lab[:, :band].reshape(-1, 3), lab[:, -band:].reshape(-1, 3)]).astype(np.float32)
    background = np.median(border, axis=0)
    if (np.linalg.norm(border - background, axis=1) < 14).mean() < 0.5:
        return np.ones((h, w), np.uint8) * 255, False
    # light counts for less than colour, so that shadows on the table aren't fruit
    difference = (lab.astype(np.float32) - background) * np.array([0.5, 1, 1], np.float32)
    mask = (np.linalg.norm(difference, axis=2) > 16).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    coverage = (mask > 0).mean()
    if not 0.02 < coverage < 0.97:
        return np.ones((h, w), np.uint8) * 255, False
    return mask, True


def _blob_response(gray, diameter):
    """How much each point looks like the centre of a bright round bump of this diameter."""
    sigma = max(0.8, diameter / (2 * math.sqrt(2)))
    return -sigma ** 2 * cv2.Laplacian(cv2.GaussianBlur(gray, (0, 0), sigma), cv2.CV_32F)


def _peaks(score, min_distance, floor):
    """Local maxima of the score at least min_distance apart: [(x, y, value)], strongest first."""
    size = max(3, int(min_distance) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
    is_peak = (score >= cv2.dilate(score, kernel)) & (score > floor)
    ys, xs = np.nonzero(is_peak)
    order = np.argsort(-score[ys, xs])
    taken, cell = [], {}
    grid = max(1.0, min_distance)
    for i in order:                                      # flat tops give several maxima: keep one
        x, y = float(xs[i]), float(ys[i])
        cx, cy = int(x // grid), int(y // grid)
        near = (cell.get((cx + a, cy + b), []) for a in (-1, 0, 1) for b in (-1, 0, 1))
        if any((x - p[0]) ** 2 + (y - p[1]) ** 2 < min_distance ** 2 for ps in near for p in ps):
            continue
        cell.setdefault((cx, cy), []).append((x, y))
        taken.append((x, y, float(score[int(y), int(x)])))
    return taken


def _repeat_distance(gray):
    """Distance at which the picture repeats itself: the spacing of fruit packed together."""
    factor = min(1.0, 700 / max(gray.shape))                               # this much detail is enough, and fast
    if factor < 1:
        gray = cv2.resize(gray, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
    h, w = gray.shape
    values = gray - gray.mean()
    values = values - cv2.GaussianBlur(values, (0, 0), min(h, w) / 6)     # uneven light is not fruit
    values = values * np.outer(np.hanning(h), np.hanning(w))
    spectrum = np.fft.fft2(values, s=(2 * h, 2 * w))
    correlation = np.fft.fftshift(np.real(np.fft.ifft2(np.abs(spectrum) ** 2)))
    yy, xx = np.indices(correlation.shape)
    radius = np.hypot(yy - h, xx - w).astype(int)
    limit = min(h, w) // 2
    totals = np.bincount(radius.ravel(), correlation.ravel())[:limit]
    counts = np.bincount(radius.ravel())[:limit]
    profile = cv2.GaussianBlur((totals / counts).reshape(-1, 1).astype(np.float32), (0, 0), 1.5).ravel()
    start = int(np.argmin(profile[: limit // 2]))                          # the first dip: half a fruit
    if start + 2 >= limit:
        return None
    return float(start + np.argmax(profile[start:min(limit, start * 4 + 4)])) / factor


def estimate_diameter(gray, mask, has_background):
    """Fruit size in pixels, guessed from the picture."""
    if has_background:
        # no point of a round fruit is further from the edge than its radius
        distance = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
        inside = distance[mask > 0]
        if inside.size:
            return float(np.percentile(inside, 99) * 2)
    repeat = _repeat_distance(gray)
    return repeat if repeat and repeat >= 6 else float(min(gray.shape) / 10)


def detect(rgb, diameter=None, sensitivity=0.7):
    """Find the fruit. Returns ([(x, y)] in the picture's pixels, fruit diameter in pixels).

    diameter: size of one fruit in pixels (None = guess it).
    sensitivity: 0 to 1; higher finds more, lower is stricter.
    """
    h, w = rgb.shape[:2]
    scale = min(1.0, MAX_SIDE / max(h, w))
    small = cv2.resize(rgb, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else rgb
    lab = cv2.cvtColor(small, cv2.COLOR_RGB2LAB)
    mask, has_background = foreground(lab)

    gray = cv2.GaussianBlur(lab[:, :, 0], (0, 0), 1.0).astype(np.float32)
    if has_background and gray[mask > 0].mean() < gray[mask == 0].mean():
        gray = 255 - gray                                # dark fruit on a light table
    d = diameter * scale if diameter else estimate_diameter(gray, mask, has_background)

    # on the logarithm of the light, a fruit in the shade looks as round as one in the sun
    response = _blob_response(np.log1p(gray), d)
    response = response / (np.percentile(np.abs(response), 99) + 1e-6)
    if has_background:
        # inside a fruit on a background, the distance to the edge marks the centre well
        distance = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
        shape = cv2.GaussianBlur(np.minimum(distance / (d / 2), 1.0), (0, 0), max(1.0, d / 8))
        score = shape + 0.5 * np.clip(response, 0, 1)
        score[mask == 0] = 0
    else:
        score = cv2.GaussianBlur(response, (0, 0), max(1.0, d / 12))

    peaks = _peaks(score, d * SPACING, 0)
    if not peaks:
        return [], d / scale
    values = np.array([p[2] for p in peaks])
    typical = np.median(values[: max(1, len(values) // 2)])
    keep = typical * (KEEP_STRICT - (KEEP_STRICT - KEEP_LOOSE) * sensitivity)
    points = [(p[0] / scale, p[1] / scale) for p in peaks if p[2] >= keep]
    return points, d / scale


# ---------------------------------------------------------------- counting from one example fruit
# Tuned on the team's 130 example pictures (59 of them counted by hand): with one fruit marked, about half of the
# counts are within 10% and the typical error is 14% (counting without an example: 25%).
EXAMPLE_SIZE = 40.0     # the picture is scaled so one fruit is this many pixels across
COLOUR_SPREAD = 1.5     # how different from the example a fruit's colour may be
SHADING = 0.8           # how much the light on each fruit (brighter in the middle) helps to separate them
SHAPE = 0.4             # weight of the shape of the coloured areas, against round blobs of the right size
EXAMPLE_SPACING = 0.55  # two marks are at least this many fruit diameters apart
CENTRE_COLOUR = 0.3     # the middle of a mark must be at least this close to the example's colour (0 to 1)


def _example_view(rgb, diameter):
    """The picture scaled so one fruit is EXAMPLE_SIZE pixels, as smoothed Lab (light counts half). (lab, scale)"""
    h, w = rgb.shape[:2]
    scale = min(EXAMPLE_SIZE / diameter, 1400 / max(h, w), 3.0)
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    small = cv2.resize(rgb, size, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    small = cv2.GaussianBlur(small, (0, 0), max(0.8, diameter * scale / 25))
    return cv2.cvtColor(small, cv2.COLOR_RGB2LAB).astype(np.float32) * np.array([0.5, 1, 1], np.float32), scale


def _disk(shape, cx, cy, r):
    """(slice of the picture around a circle, mask of the circle inside it)"""
    h, w = shape
    x0, x1, y0, y1 = max(0, int(cx - r)), min(w, int(cx + r) + 1), max(0, int(cy - r)), min(h, int(cy + r) + 1)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    return (slice(y0, y1), slice(x0, x1)), (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r


def _fill_holes(mask, diameter):
    """Clean a mask: remove specks, close gaps and fill holes smaller than half a fruit (shine, stems, spots)."""
    k = max(3, int(diameter * 0.12) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    mask = cv2.morphologyEx(cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel), cv2.MORPH_CLOSE, kernel)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(255 - mask, connectivity=4)
    h, w = mask.shape
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if area < 0.4 * diameter * diameter and x > 0 and y > 0 and x + bw < w and y + bh < h:
            mask[labels == i] = 255
    return mask


def detect_like(rgb, line, sensitivity=0.7):
    """Find fruit like the one the person measured. line = (x0, y0, x1, y1) across that fruit, in the picture's pixels.

    Its colour says what is fruit (whatever the background) and its length the size. Every place that looks like a
    round blob of that colour and size, about as clearly as the example, is a fruit.
    Returns ([(x, y)] in the picture's pixels, fruit diameter in pixels).
    """
    x0, y0, x1, y1 = line
    diameter = max(4.0, math.hypot(x1 - x0, y1 - y0))
    lab, scale = _example_view(rgb, diameter)
    d = diameter * scale
    cx, cy, r = (x0 + x1) / 2 * scale, (y0 + y1) / 2 * scale, d / 2

    # the example's colours (body, shine, shadow) and how far every pixel is from them
    where, inside = _disk(lab.shape[:2], cx, cy, 0.7 * r)
    sample = lab[where][inside]
    groups = 3 if len(sample) > 30 else 1
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5)
    _, _, colours = cv2.kmeans(sample.reshape(-1, 3), groups, None, criteria, 2, cv2.KMEANS_PP_CENTERS)
    distance = np.min(np.linalg.norm(lab.reshape(-1, 1, 3) - colours[None], axis=2), axis=1).reshape(lab.shape[:2])
    spread = float(np.percentile(np.min(np.linalg.norm(sample[:, None] - colours[None], axis=2), axis=1), 90))
    similar = np.exp(-(distance / (spread * COLOUR_SPREAD + 5)) ** 2).astype(np.float32)

    # light: each fruit is brightest in the middle, which separates fruit that touch
    light = lab[:, :, 0] / 0.5
    where, inside = _disk(light.shape, cx, cy, 0.8 * r)
    low, high = np.percentile(light[where][inside], [5, 95])
    light = np.clip((light - low) / (high - low + 1e-6), 0, 1).astype(np.float32)
    weighted = similar * ((1 - SHADING) + SHADING * light)
    sigma = d / 2 / math.sqrt(2)
    blobs = cv2.GaussianBlur(weighted, (0, 0), sigma * 0.8) - cv2.GaussianBlur(weighted, (0, 0), sigma * 1.9)
    where, _ = _disk(blobs.shape, cx, cy, d / 4)
    example = float(blobs[where].max()) + 1e-6

    # shape: inside a fruit, the distance to the edge of the coloured area
    mask = _fill_holes((similar > 0.5).astype(np.uint8) * 255, d)
    edge = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    shape = cv2.GaussianBlur(np.minimum(edge, r) / r, (0, 0), max(1.0, d / 10))

    score = (1 - SHAPE) * blobs / example + SHAPE * shape
    floor = 0.2 + (0.7 - sensitivity) * 0.5             # sensitivity 0.7 = the tuned value
    centre = cv2.GaussianBlur(similar, (0, 0), max(1.0, d / 8))      # a fruit's middle has the fruit's colour
    points = [(x / scale, y / scale) for x, y, _ in _peaks(score, d * EXAMPLE_SPACING, floor)
              if centre[int(y), int(x)] >= CENTRE_COLOUR]
    return points, diameter


def annotated(rgb, points, diameter):
    """A copy of the picture with every mark numbered and the total written on it (PIL image)."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.fromarray(rgb)
    draw = ImageDraw.Draw(img)
    r = max(4, diameter * 0.12)
    width = max(1, round(r / 3))
    size = max(11, round(diameter * 0.22))
    try:
        font, title = ImageFont.truetype("arial.ttf", size), ImageFont.truetype("arial.ttf", max(20, img.width // 30))
    except OSError:
        font = title = ImageFont.load_default()
    for i, (x, y) in enumerate(sorted(points, key=lambda p: (round(p[1] / max(diameter, 1)), p[0])), 1):
        draw.ellipse((x - r, y - r, x + r, y + r), outline=(255, 40, 40), width=width, fill=(255, 255, 255))
        draw.text((x, y), str(i), fill=(0, 0, 0), font=font, anchor="mm")
    text = f"Total: {len(points)}"
    box = draw.textbbox((12, 12), text, font=title)
    draw.rectangle((box[0] - 8, box[1] - 8, box[2] + 8, box[3] + 8), fill=(0, 0, 0))
    draw.text((12, 12), text, fill=(255, 255, 255), font=title)
    return img
