"""Shared data that applies to many products at once: default tags and image
groups.

Both are stored as rules rather than copied into the products themselves. The
tags of "Arredamento da Esterno" belong to whatever is in that category right
now, and the photos of a "piletta" belong to whatever products share that
accessory — so editing either has to reach products created months ago. The
merge happens only when the WooCommerce file is generated; data/products.csv
keeps just what was typed for that specific product.

That is what makes the groups editable after the fact: swap a URL in a group and
every product in it follows, remove one and it disappears everywhere.

Files, all plain CSV so they can be inspected or fixed by hand:

    data/tag_defaults.csv          categoria -> tag
    data/image_groups.csv          gruppo    -> URL immagini
    data/image_group_members.csv   gruppo    -> SKU (una riga per appartenenza)
"""

from pathlib import Path

import pandas as pd

from categories import split_value
from storage import DATA_DIR, ENCODING, join_list, split_list

TAG_DEFAULTS_FILE = DATA_DIR / 'tag_defaults.csv'
IMAGE_GROUPS_FILE = DATA_DIR / 'image_groups.csv'
IMAGE_MEMBERS_FILE = DATA_DIR / 'image_group_members.csv'

# Column names of the shared files, kept readable so they can be edited in Excel.
CATEGORY_COLUMN = 'Categoria'
TAGS_COLUMN = 'Tag'
GROUP_COLUMN = 'Gruppo'
IMAGES_COLUMN = 'Immagini'
SKU_COLUMN = 'SKU'


def load_tag_defaults(path: Path | None = None) -> dict[str, list[str]]:
    """Map each category path to its default tags.

    Keys match the form used by categories.load_codes: "Parent" for a top-level
    category, "Parent > Child" for a subcategory.
    """
    path = path or TAG_DEFAULTS_FILE
    if not path.exists():
        return {}

    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding=ENCODING)
    return {
        row[CATEGORY_COLUMN].strip(): split_list(row[TAGS_COLUMN])
        for row in frame.to_dict('records')
        if row[CATEGORY_COLUMN].strip()
    }


def save_tag_defaults(defaults: dict[str, list[str]], path: Path | None = None) -> None:
    """Write the defaults back, dropping categories left empty."""
    path = path or TAG_DEFAULTS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{CATEGORY_COLUMN: category, TAGS_COLUMN: join_list(tags)}
            for category, tags in defaults.items() if tags]
    frame = pd.DataFrame(rows, columns=[CATEGORY_COLUMN, TAGS_COLUMN])
    frame.to_csv(path, index=False, encoding=ENCODING)


def _merge(*sources: list[str]) -> list[str]:
    """Concatenate tag lists, dropping repeats case-insensitively."""
    merged: list[str] = []
    seen: set[str] = set()
    for source in sources:
        for tag in source:
            if tag.casefold() not in seen:
                seen.add(tag.casefold())
                merged.append(tag)

    return merged


def inherited_tags(categories_value: str, defaults: dict[str, list[str]]) -> list[str]:
    """Default tags a product picks up from its category and subcategory."""
    parent, child = split_value(categories_value)
    if not parent:
        return []

    from_child = defaults.get(f'{parent} > {child}', []) if child else []
    return _merge(defaults.get(parent, []), from_child)


def effective_tags(categories_value: str, own_tags: str,
                   defaults: dict[str, list[str]]) -> list[str]:
    """Everything a product ends up tagged with: inherited first, then its own."""
    return _merge(inherited_tags(categories_value, defaults), split_list(own_tags))


def apply_tag_defaults(frame: pd.DataFrame, defaults: dict[str, list[str]]) -> pd.Series:
    """Effective Tag column for a whole catalog."""
    return pd.Series(
        [join_list(effective_tags(row['Categorie'], row['Tag'], defaults))
         for row in frame.to_dict('records')],
        index=frame.index,
        dtype=str,
    )


# ------------------------------------------------------------- gruppi immagini

def load_image_groups(path: Path | None = None) -> dict[str, list[str]]:
    """Map each group name to its image URLs, in the order they were entered."""
    path = path or IMAGE_GROUPS_FILE
    if not path.exists():
        return {}

    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding=ENCODING)
    return {row[GROUP_COLUMN].strip(): split_list(row[IMAGES_COLUMN])
            for row in frame.to_dict('records') if row[GROUP_COLUMN].strip()}


def save_image_groups(groups: dict[str, list[str]], path: Path | None = None) -> None:
    path = path or IMAGE_GROUPS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{GROUP_COLUMN: name, IMAGES_COLUMN: join_list(urls)}
            for name, urls in groups.items()]
    pd.DataFrame(rows, columns=[GROUP_COLUMN, IMAGES_COLUMN]).to_csv(
        path, index=False, encoding=ENCODING)


def load_group_members(path: Path | None = None) -> dict[str, list[str]]:
    """Map each group name to the SKUs assigned to it."""
    path = path or IMAGE_MEMBERS_FILE
    if not path.exists():
        return {}

    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding=ENCODING)
    members: dict[str, list[str]] = {}
    for row in frame.to_dict('records'):
        group, sku = row[GROUP_COLUMN].strip(), row[SKU_COLUMN].strip()
        if group and sku and sku not in members.setdefault(group, []):
            members[group].append(sku)

    return members


def save_group_members(members: dict[str, list[str]], path: Path | None = None) -> None:
    path = path or IMAGE_MEMBERS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{GROUP_COLUMN: group, SKU_COLUMN: sku}
            for group, skus in members.items() for sku in skus]
    pd.DataFrame(rows, columns=[GROUP_COLUMN, SKU_COLUMN]).to_csv(
        path, index=False, encoding=ENCODING)


def groups_of(sku: str, members: dict[str, list[str]]) -> list[str]:
    """Names of the groups a product belongs to."""
    return [group for group, skus in members.items() if sku in skus]


def group_images(sku: str, groups: dict[str, list[str]],
                 members: dict[str, list[str]]) -> list[str]:
    """Images a product inherits from every group it belongs to."""
    return _merge(*(groups.get(group, []) for group in groups_of(sku, members)))


def effective_images(sku: str, own_images: str, groups: dict[str, list[str]],
                     members: dict[str, list[str]]) -> list[str]:
    """Every image a product is exported with.

    Its own images come first, so the main image stays whatever was chosen on the
    product itself; group images are appended. A product with no images of its
    own takes the group's first image as its main one.
    """
    return _merge(split_list(own_images), group_images(sku, groups, members))


def apply_image_groups(frame: pd.DataFrame, groups: dict[str, list[str]],
                       members: dict[str, list[str]]) -> pd.Series:
    """Effective Immagine column for a whole catalog."""
    return pd.Series(
        [join_list(effective_images(row['SKU'], row['Immagine'], groups, members))
         for row in frame.to_dict('records')],
        index=frame.index,
        dtype=str,
    )


def forget_sku(sku: str, members: dict[str, list[str]]) -> dict[str, list[str]]:
    """Drop a deleted product from every group."""
    return {group: [s for s in skus if s != sku] for group, skus in members.items()}


def rename_sku(old: str, new: str, members: dict[str, list[str]]) -> dict[str, list[str]]:
    """Follow a product whose SKU was edited by hand, so it keeps its groups."""
    return {group: [new if s == old else s for s in skus] for group, skus in members.items()}
