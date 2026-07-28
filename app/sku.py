"""SKU generation.

An SKU encodes what the product is, how big it is, and which copy of that
combination it is:

    E   LR   080   0001
    │   │    │     └─ progressivo nel gruppo, 4 cifre
    │   │    └─ dimensione maggiore in cm, 3 cifre
    │   └─ codice sottocategoria
    └─ codice categoria

Codes come from categories.txt. Three digits are needed for the size because
products run past 200 cm, and the progressive counter restarts for each
category/subcategory/size combination.

An SKU is generated once, when the product is created, and then left alone:
changing it later would make WooCommerce treat the product as a brand new one
rather than an update. Recategorising a product therefore leaves its original
SKU in place, which is intended.
"""

import re

# Used when a product sits directly under a top-level category with no
# subcategory (Rubinetteria), keeping every SKU the same width.
NO_SUBCATEGORY_CODE = 'XX'

SIZE_DIGITS = 3
SEQUENCE_DIGITS = 4
MAX_SIZE = 10 ** SIZE_DIGITS - 1
MAX_SEQUENCE = 10 ** SEQUENCE_DIGITS - 1

DIMENSION_COLUMNS = ('Lunghezza (cm)', 'Larghezza (cm)', 'Altezza (cm)')

PATTERN = re.compile(rf'^(?P<prefix>[A-Z0-9]+?)(?P<size>\d{{{SIZE_DIGITS}}})'
                     rf'(?P<sequence>\d{{{SEQUENCE_DIGITS}}})$')


def major_size(product: dict[str, str]) -> int:
    """Largest of the three dimensions, rounded to whole cm.

    Returns 0 when no dimension is filled in, which shows up as 000 in the SKU
    and is a visible signal that the measurements are missing.
    """
    sizes = []
    for column in DIMENSION_COLUMNS:
        raw = product.get(column, '').strip().replace(',', '.')
        if not raw:
            continue
        try:
            sizes.append(float(raw))
        except ValueError:
            continue

    return min(round(max(sizes)), MAX_SIZE) if sizes else 0


def prefix(category_code: str, subcategory_code: str | None, size: int) -> str:
    """The part of an SKU shared by every product of the same kind and size."""
    return f'{category_code}{subcategory_code or NO_SUBCATEGORY_CODE}{size:0{SIZE_DIGITS}d}'


def next_sequence(group: str, existing: list[str]) -> int:
    """First unused progressive number for a prefix."""
    used = set()
    for sku in existing:
        match = PATTERN.match(sku.strip().upper())
        if match and match['prefix'] + match['size'] == group:
            used.add(int(match['sequence']))

    candidate = 1
    while candidate in used:
        candidate += 1

    return candidate


def generate(category_code: str, subcategory_code: str | None, product: dict[str, str],
             existing: list[str]) -> str:
    """Build the next free SKU for a product."""
    group = prefix(category_code, subcategory_code, major_size(product))
    sequence = next_sequence(group, existing)
    if sequence > MAX_SEQUENCE:
        raise ValueError(f'Esauriti i progressivi disponibili per {group}')

    return f'{group}{sequence:0{SEQUENCE_DIGITS}d}'


def labels_by_prefix(codes: dict[str, str]) -> dict[str, str]:
    """Map each category/subcategory code pair back to a readable name."""
    labels: dict[str, str] = {}
    for path, code in codes.items():
        parent, _, child = path.partition(' > ')
        if child:
            labels[codes[parent] + code] = child
        else:
            labels[code + NO_SUBCATEGORY_CODE] = parent

    return labels


def describe(sku: str, codes: dict[str, str]) -> str:
    """Human-readable breakdown of an SKU, for display under the field."""
    match = PATTERN.match(sku.strip().upper())
    if match is None:
        return 'formato non standard'

    label = labels_by_prefix(codes).get(match['prefix'], match['prefix'])
    size = int(match['size'])
    size_text = f'{size} cm' if size else 'dimensione mancante'

    return f'{label} · {size_text} · n. {int(match["sequence"])}'
