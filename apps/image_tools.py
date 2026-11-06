"""The edits of the Image Editor, without any window: same recipe for one preview or a whole batch."""
import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps

# name -> ratio (width / height); what the Image Editor offers
RATIOS = {"Keep": None, "1:1 square": 1, "4:3": 4 / 3, "3:4": 3 / 4, "3:2": 3 / 2, "2:3": 2 / 3,
          "16:9": 16 / 9, "9:16": 9 / 16, "A4 portrait": 210 / 297, "A4 landscape": 297 / 210}
# name -> (width, height); None = keep
RESOLUTIONS = {"Keep": None, "3840 x 2160 (4K)": (3840, 2160), "1920 x 1080 (Full HD)": (1920, 1080),
               "1280 x 720 (HD)": (1280, 720), "1600 x 1200": (1600, 1200), "1024 x 768": (1024, 768),
               "800 x 600": (800, 600), "1080 x 1080": (1080, 1080), "640 x 480": (640, 480)}
ANCHORS = {"Center": (0.5, 0.5), "Top": (0.5, 0), "Bottom": (0.5, 1), "Left": (0, 0.5), "Right": (1, 0.5)}
FORMATS = {"Same as original": None, "JPG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
FIT_MODES = ("Cut to fill", "Fit inside", "Stretch")


@dataclass
class Recipe:
    angle: float = 0              # degrees clockwise
    flip_h: bool = False
    flip_v: bool = False
    ratio: object = None          # width / height, or None
    anchor: str = "Center"        # which part stays when cutting
    size: object = None           # (width, height), or None
    fit: str = "Cut to fill"      # how a picture goes into `size`
    brightness: float = 1.0       # 1 = no change
    contrast: float = 1.0
    saturation: float = 1.0
    sharpness: float = 1.0


def cut_to_ratio(img, ratio, anchor="Center"):
    """Cut the picture to a width/height ratio, keeping as much of it as possible."""
    w, h = img.size
    ax, ay = ANCHORS[anchor]
    if w / h > ratio:
        new_w = max(1, round(h * ratio))
        left = round((w - new_w) * ax)
        return img.crop((left, 0, left + new_w, h))
    new_h = max(1, round(w / ratio))
    top = round((h - new_h) * ay)
    return img.crop((0, top, w, top + new_h))


def apply(img, recipe):
    """The picture with the recipe applied. Phone pictures are first turned the way they were taken."""
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGBA" if "transparency" in img.info or img.mode in ("LA", "PA") else "RGB")
    if recipe.flip_h:
        img = ImageOps.mirror(img)
    if recipe.flip_v:
        img = ImageOps.flip(img)
    angle = recipe.angle % 360
    if angle in (90, 180, 270):
        img = img.transpose({90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180,
                             270: Image.Transpose.ROTATE_90}[angle])       # no quality loss
    elif angle:
        img = img.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=_white(img))
    if recipe.ratio:
        img = cut_to_ratio(img, recipe.ratio, recipe.anchor)
    if recipe.size:
        img = _to_size(img, recipe.size, recipe.fit, recipe.anchor)
    for enhancer, amount in ((ImageEnhance.Brightness, recipe.brightness), (ImageEnhance.Contrast, recipe.contrast),
                             (ImageEnhance.Color, recipe.saturation), (ImageEnhance.Sharpness, recipe.sharpness)):
        if abs(amount - 1) > 0.001:
            img = enhancer(img).enhance(amount)
    return img


def _white(img):
    return {"L": 255, "RGBA": (255, 255, 255, 0)}.get(img.mode, (255, 255, 255))


def _to_size(img, size, fit, anchor):
    resample = Image.Resampling.LANCZOS
    if fit == "Stretch":
        return img.resize(size, resample)
    if fit == "Fit inside":                  # the whole picture, with white borders to reach the size
        inner = ImageOps.contain(img, size, resample)
        canvas = Image.new(img.mode, size, _white(img))
        canvas.paste(inner, ((size[0] - inner.width) // 2, (size[1] - inner.height) // 2))
        return canvas
    ax, ay = ANCHORS[anchor]
    return ImageOps.fit(img, size, resample, centering=(ax, ay))


def result_size(size, recipe):
    """Size of the result for a picture of this size, without doing the work (shown next to the preview)."""
    w, h = size
    angle = recipe.angle % 360
    if angle in (90, 270):
        w, h = h, w
    elif angle and angle != 180:
        rad = math.radians(angle)
        w, h = (round(abs(w * math.cos(rad)) + abs(h * math.sin(rad))),
                round(abs(w * math.sin(rad)) + abs(h * math.cos(rad))))
    if recipe.ratio:
        w, h = (max(1, round(h * recipe.ratio)), h) if w / h > recipe.ratio else (w, max(1, round(w / recipe.ratio)))
    return recipe.size or (w, h)


def output_path(source, out_dir, suffix, extension):
    """Where a picture goes. Never overwrites anything: originals and earlier results stay."""
    source = Path(source)
    ext = extension or source.suffix.lower()
    target = Path(out_dir) / f"{source.stem}{suffix}{ext}"
    n = 2
    while target.exists() or target.resolve() == source.resolve():
        target = Path(out_dir) / f"{source.stem}{suffix} ({n}){ext}"
        n += 1
    return target


def save(img, path, quality=92):
    path = Path(path)
    ext = path.suffix.lower()
    if ext in (".jpg", ".jpeg", ".bmp") and img.mode != "RGB":
        background = Image.new("RGB", img.size, (255, 255, 255))     # no transparency in JPG / BMP
        background.paste(img, mask=img.getchannel("A") if img.mode == "RGBA" else None)
        img = background
    options = {".jpg": {"quality": quality, "optimize": True}, ".jpeg": {"quality": quality, "optimize": True},
               ".webp": {"quality": quality}, ".png": {"optimize": True}}.get(ext, {})
    img.save(path, **options)


def process_batch(files, out_dir, recipe, suffix="_edited", extension=None, quality=92, progress=None):
    """Edit every file. One bad picture doesn't stop the rest. Returns (saved paths, [(file, error)])."""
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    saved, failed = [], []
    for i, f in enumerate(files):
        if progress:
            progress(i, len(files), Path(f).name)
        try:
            with Image.open(f) as img:
                result = apply(img, recipe)
                target = output_path(f, out_dir, suffix, extension)
                save(result, target, quality)
            saved.append(target)
        except Exception as e:
            failed.append((Path(f).name, str(e)))
    if progress:
        progress(len(files), len(files), "")
    return saved, failed
