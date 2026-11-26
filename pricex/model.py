from dataclasses import dataclass, field


@dataclass
class PriceRow:
    """One price for one size. Suppliers fill what they know; empty fields stay empty."""
    specie: str
    price: float
    variety: str = ""
    origin: str = ""
    size: object = ""          # number or text ("1XX", "250+", "Mix 12-16", "N/S")
    weight: object = None      # kg
    brand: str = ""
    cat: object = ""
    packaging: str = ""
    box_pp: object = None
    detail: str = ""
    type: str = ""
    group: str = ""            # original grouped size ("6/7") when it was split into one row per size
    flag: str = ""             # set when the price looks wrong (shown red in the Excel)
    not_final: bool = False    # printed in red in the price list: a price that isn't final yet
    guessed: tuple = ()        # columns filled with a default, not read ("WEIGHT (KG)",): red, to check


# Output column name -> PriceRow attribute
FIELDS = {
    "SPECIE": "specie",
    "VARIETY": "variety",
    "ORIGIN": "origin",
    "SIZE": "size",
    "WEIGHT (KG)": "weight",
    "BRAND": "brand",
    "CAT": "cat",
    "PACKAGING": "packaging",
    "BOX PP": "box_pp",
    "PRICE EUR": "price",
    "DETAIL": "detail",
    "TYPE": "type",
}

DEFAULT_COLUMNS = ["DATE", "SPECIE", "VARIETY", "ORIGIN", "SIZE", "WEIGHT (KG)", "BRAND",
                   "CAT", "PACKAGING", "BOX PP", "PRICE EUR", "DETAIL", "TYPE"]


@dataclass
class Result:
    """What one supplier file produced."""
    supplier: str
    file: str
    date: object
    rows: list = field(default_factory=list)
    skipped: list = field(default_factory=list)    # products with a price but not tracked
    warnings: list = field(default_factory=list)
    corrections: list = field(default_factory=list)  # prices dropped / flagged by the sanity check
    identified_by: str = ""                            # how the supplier was recognised
