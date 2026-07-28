"""Category tree, read from categories.txt.

categories.txt is the single source of truth for category names *and* for the
letter codes that go into generated SKUs. Top-level names start at column 0,
subcategories are indented beneath their parent, and every name carries its code
in square brackets:

    Arredamento da Esterno [E]
        Lavelli rustici [LR]

Driving the UI from this file means a category name is never typed by hand,
which is what stops WooCommerce from silently creating near-duplicate terms that
differ only in casing. Codes are assigned here rather than derived from the
names because initials collide badly — Panchine, Piatti doccia and Pozzi would
all be P.

The value written to the CSV is "Parent > Child, Parent" — naming the parent as
well as the child assigns the product to both, matching how the catalog is
organised.
"""

import re
from pathlib import Path

CATEGORIES_FILE = Path(__file__).resolve().parent.parent / 'categories.txt'

NO_SUBCATEGORY = '— nessuna —'

# "Nome categoria [AB]" — the code is required so a typo surfaces immediately
# instead of quietly producing malformed SKUs.
LINE = re.compile(r'^(?P<name>.+?)\s*\[(?P<code>[A-Z0-9]+)\]$')


def _parse(path: Path) -> list[tuple[bool, str, str]]:
    """Read the file into (is_child, name, code) triples, in file order."""
    entries: list[tuple[bool, str, str]] = []

    for number, raw_line in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
        if not raw_line.strip():
            continue
        match = LINE.match(raw_line.strip())
        if match is None:
            raise ValueError(
                f'{path.name} riga {number}: manca il codice fra parentesi quadre '
                f'(es. "Fontane [FO]") in {raw_line.strip()!r}'
            )
        entries.append((raw_line[0].isspace(), match['name'], match['code']))

    return entries


def load_tree(path: Path | None = None) -> dict[str, list[str]]:
    """Parse categories.txt into {parent: [children]}, preserving file order."""
    tree: dict[str, list[str]] = {}
    current: str | None = None

    for is_child, name, _ in _parse(path or CATEGORIES_FILE):
        if is_child:
            if current is None:
                raise ValueError(f'Sottocategoria senza categoria padre: {name!r}')
            tree[current].append(name)
        else:
            current = name
            tree.setdefault(current, [])

    return tree


def load_codes(path: Path | None = None) -> dict[str, str]:
    """Map every category to its SKU code.

    Parents are keyed by name, children by "Parent > Child", so the two levels
    cannot shadow each other.
    """
    codes: dict[str, str] = {}
    current: str | None = None

    for is_child, name, code in _parse(path or CATEGORIES_FILE):
        if is_child:
            codes[f'{current} > {name}'] = code
        else:
            current = name
            codes[name] = code

    return codes


def format_value(parent: str, child: str | None) -> str:
    """Build the CSV cell for a parent/child pair."""
    if not parent:
        return ''
    if child and child != NO_SUBCATEGORY:
        return f'{parent} > {child}, {parent}'
    return parent


def split_value(value: str) -> tuple[str, str]:
    """Recover (parent, child) from a CSV cell. Child is '' when absent.

    Tolerates the variations found in hand-edited files: missing trailing
    parent, extra spacing, and the parent listed before the hierarchy.
    """
    parent, child = '', ''
    for part in (p.strip() for p in value.split(',')):
        if not part:
            continue
        if '>' in part:
            head, _, tail = part.partition('>')
            parent, child = head.strip(), tail.strip()
            break
        if not parent:
            parent = part

    return parent, child


def canonicalize(value: str, tree: dict[str, list[str]]) -> tuple[str, list[str]]:
    """Rewrite a cell using the exact casing from categories.txt.

    Returns the corrected value plus a list of problems; unknown names are left
    untouched so nothing is silently discarded.
    """
    parent, child = split_value(value)
    problems: list[str] = []

    if not parent:
        return '', ['categoria mancante']

    parents = {p.casefold(): p for p in tree}
    canonical_parent = parents.get(parent.casefold())
    if canonical_parent is None:
        problems.append(f'categoria sconosciuta: {parent!r}')
        canonical_parent = parent

    canonical_child = ''
    if child:
        children = {c.casefold(): c for c in tree.get(canonical_parent, [])}
        canonical_child = children.get(child.casefold())
        if canonical_child is None:
            problems.append(f'sottocategoria sconosciuta: {child!r}')
            canonical_child = child

    return format_value(canonical_parent, canonical_child), problems
