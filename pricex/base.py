"""Base class for supplier parsers.

To add a supplier, copy one of the files in pricex/suppliers/, change the settings at the top
and write parse(). It's picked up automatically.
"""
import copy
import re

from . import normalize as N
from .model import FIELDS, PriceRow


class Supplier:
    # ---- identity
    name = ""                 # tab name in the combined file / name of the separate file
    final_file = ""           # the Excel the prices end up in (OneDrive); used to build the column template
    match_names = []          # lowercase words looked for in the file name
    match_text = []           # lowercase identifiers in the content (domain, e-mail, company, CoC number):
                              # if one is found the supplier is certain, whatever the file is called
    layout_hints = []         # regexes typical of this supplier's layout (used when there's no identifier)
    file_types = (".pdf",)

    # ---- output style
    layout = "long"           # "long": one row per size, a tab in the combined file
                              # "wide": a separate file with one tab per species and a column per size
    origin_style = "source"   # "source" (as written), "name" (Brazil), "NAME" (BRAZIL), "code" (BR)
    origin_overrides = {}     # country name -> text to write, e.g. {"Kenya": "KEN"}
    species_names = {}        # our species name -> how this supplier's Excel writes it
    sheet_names = {}          # wide only: species -> tab, e.g. {"Pomelos": "GRAPEFRUITS"}
    upper_species = False     # write SPECIE in capitals
    default_packaging = "Carton"
    default_cat = ""          # CAT written when the price list doesn't say (e.g. 1)
    default_brand = ""        # BRAND written when the price list doesn't say (e.g. "Generic")
    must_fill = ()            # columns that can't stay empty, e.g. ("WEIGHT (KG)",): an empty one is coloured
                              # red in the output and the report says so, for the person to fill in

    def parse(self, doc):
        """Return a list of PriceRow. `specie` may be any text naming the product
        (section title, product name...): it's resolved to a species afterwards."""
        raise NotImplementedError

    # ---- helpers for parsers
    @staticmethod
    def row(**kw):
        return PriceRow(**kw)

    # ---- post-processing shared by all suppliers
    def finalize(self, rows, result):
        out = []
        for r in rows:
            if r.price is None or r.price <= 0:
                continue
            if r.flag:                     # the parser wasn't sure about this row (e.g. read from a picture)
                result.corrections.append(f"CHECK {r.specie} {r.variety} {r.origin} size {r.size or '?'} "
                                          f"€{r.price:g}: {r.flag} (kept, marked red)")
            # supplier codes for a variety ("329-5" -> Gem), listed in species.json -> variety_codes
            r.specie, r.variety = N.replace_variety_codes(r.specie, r.variety)
            # "Fairtrade Limes" -> species Limes, TYPE FAIRTRADE (labels listed in species.json -> type_words)
            tags, (r.specie, r.variety, r.type) = N.take_type_words(r.specie, r.variety, r.type)
            if tags:
                r.type = " ".join([r.type] + [t for t in tags if t not in r.type.split()]).strip()
            raw = r.specie
            label = " ".join(str(x) for x in (raw, r.variety) if x).strip()
            if N.is_ignored(label):
                continue
            species = (N.find_species(raw) or N.species_from_variety(r.variety)
                       or N.species_from_variety(raw))
            if not species:
                result.skipped.append(f"{label} ({r.origin}, {r.size}, €{r.price:g})")
                continue
            r.specie = self.species_names.get(species, species)
            if self.upper_species:
                r.specie = r.specie.upper()
            r.variety = re.sub(r"\s+", " ", str(r.variety or "")).strip() or r.specie
            r.packaging = (N.packaging_rule(species, r.weight, r.packaging, f"{r.detail} {r.type} {r.variety}")
                           or r.packaging or self.default_packaging)
            r.cat = r.cat if r.cat not in ("", None) else self.default_cat
            r.brand = r.brand if r.brand not in ("", None) else self.default_brand
            sizes = N.split_sizes(r.size, species)
            # "Dom. Rep. / Colombia": one row per origin, like grouped sizes
            for origin in N.split_origins(r.origin):
                for s in sizes:
                    c = copy.copy(r)
                    c.origin = N.format_origin(origin, self.origin_style, self.origin_overrides)
                    c.group = str(r.size) if len(sizes) > 1 else ""
                    c.size = s if s not in ("", None) else "N/S"
                    out.append(c)
        out = remove_duplicates(check_per_kg(check_prices(out, result), result), result)
        for column in self.must_fill:
            empty = sum(1 for r in out if getattr(r, FIELDS[column], None) in ("", None))
            if empty:
                result.warnings.append(f"{column} missing on {empty} of {len(out)} rows: "
                                       f"the price list doesn't say it, fill in the red cells")
        return out


# ---------------------------------------------------------------- price sanity checks

OUTLIER = 3          # a price 3x above or below the usual price of the same product is suspicious


def product_key(r):
    """Same product = same species, variety, origin, weight, box pp, packing and detail (brand and size may differ)."""
    return (str(r.specie).lower(), str(r.variety).lower(), str(r.origin).lower(), r.weight, r.box_pp,
            str(r.packaging).lower(), str(r.detail).lower(), str(r.type).lower())


def check_prices(rows, result):
    """Catch typos like Palmer 6/7 at €76 when every other Palmer 4kg is €6-7.
    If the same size is already offered at a normal price the row is dropped, otherwise it's
    kept and flagged (red cell in the Excel). Both are listed in the report."""
    from statistics import median
    groups = {}
    for r in rows:
        groups.setdefault(product_key(r), []).append(r)
    drop = set()
    for group in groups.values():
        if len(group) < 3:
            continue
        for r in group:
            others = [o.price for o in group if o is not r and o.price != r.price]
            if len(others) < 2:
                continue
            usual = median(others)
            if usual <= 0 or 1 / OUTLIER < r.price / usual < OUTLIER:
                continue
            label = f"{r.specie} {r.variety} {r.origin} {r.weight or ''}kg size {r.size} at €{r.price:g}"
            same_size = [o for o in group if o is not r and str(o.size) == str(r.size)
                         and 1 / OUTLIER < o.price / usual < OUTLIER]
            if same_size:
                drop.add(id(r))
                result.corrections.append(
                    f"dropped {label}: the same product is €{min(others):g}-{max(others):g}, "
                    f"and size {r.size} is already there at €{same_size[0].price:g}")
            else:
                r.flag = f"usual price €{usual:g}"
                result.corrections.append(
                    f"CHECK {label}: the same product is usually €{usual:g} (kept, marked red)")
    return [r for r in rows if id(r) not in drop]


# "per kg" sense check: limits in euro
PER_KG_MAX = 25            # a price labelled per kg above this is probably the box price
PER_KG_BOX_MAX = 150       # ...or when price x box weight would be more than this
BOX_MIN_PER_KG = 0.15      # a box price below this per kg is probably a price per kg
LOW_PRICE = 1.0            # without a weight, a price below this is probably per kg
BIN_WEIGHT = 100           # a "box" this heavy is a bin, usually priced per kg


def is_per_kg(r):
    text = f"{r.detail} {r.type} {r.size} {r.packaging}".lower()
    return bool(re.search(r"price\s*/\s*kg|per\s*kg|/\s*kg\b|€\s*/\s*kg", text))


def check_per_kg(rows, result):
    """Flag prices whose unit looks wrong: labelled per kg but priced like a box, or priced
    like a kg without saying so (tiny price for the box weight, bins). Rows are never removed:
    the price cell is coloured red and the reason is listed in the report."""
    for r in rows:
        w = r.weight if isinstance(r.weight, (int, float)) and r.weight > 0 else None
        bin_text = re.search(r"\bbins?\b", f"{r.size} {r.packaging} {r.detail}".lower())
        reason = ""
        if is_per_kg(r):
            is_bin = bin_text or (w and w >= BIN_WEIGHT)          # bins are priced per kg: that's normal
            if r.price > PER_KG_MAX or (w and not is_bin and r.price * w > PER_KG_BOX_MAX):
                box = f" (x {w:g} kg = €{r.price * w:,.0f} a box)" if w else ""
                reason = f"labelled per kg, but €{r.price:g}/kg{box} looks like the price of the whole box"
        elif w and w >= BIN_WEIGHT:
            reason = f"{w:g} kg bin at €{r.price:g}: probably a price per kg"
        elif bin_text:
            reason = f"bin at €{r.price:g}: probably a price per kg"
        elif w and r.price / w < BOX_MIN_PER_KG:
            reason = f"€{r.price:g} for a {w:g} kg box is €{r.price / w:.2f}/kg: probably a price per kg"
        elif not w and r.price < LOW_PRICE:
            reason = f"€{r.price:g} with no weight: probably a price per kg"
        if reason:
            r.flag = r.flag or reason
            result.corrections.append(
                f"CHECK {r.specie} {r.variety} {r.origin} size {r.size}: {reason} (kept, marked red)")
    return rows


def remove_duplicates(rows, result):
    seen, out = set(), []
    for r in rows:
        key = tuple(getattr(r, f) for f in ("specie", "variety", "origin", "size", "weight", "brand", "cat",
                                            "packaging", "box_pp", "price", "detail", "type"))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    if len(out) < len(rows):
        result.corrections.append(f"removed {len(rows) - len(out)} identical row(s)")
    return out


_REGISTRY = []


def register(cls):
    _REGISTRY.append(cls())
    return cls


def suppliers():
    if not _REGISTRY:
        from . import suppliers as _pkg  # noqa: F401  (imports every module, which registers itself)
    return list(_REGISTRY)
