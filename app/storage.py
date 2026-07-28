"""Reading and writing data/products.csv, the working catalog.

products.csv carries the exact same columns as the WooCommerce import file, so
exporting is a validate-and-copy rather than a schema translation.

Two pandas details matter here and are easy to get wrong:

* ``dtype=str`` keeps SKUs like ``605970014-A`` as text and stops prices from
  being reformatted as floats.
* ``keep_default_na=False`` keeps empty cells as ``''`` instead of ``NaN``, so
  every value in the frame is a real string.
"""

from pathlib import Path

import pandas as pd

from schema import COLUMNS, empty_product

DATA_DIR = Path(__file__).resolve().parent.parent / 'data'
PRODUCTS_FILE = DATA_DIR / 'products.csv'

# WooCommerce and Excel both need the BOM to read accented text correctly.
ENCODING = 'utf-8-sig'


def load_products(path: Path | None = None) -> pd.DataFrame:
    """Load the catalog, adding any column the file happens to be missing."""
    path = path or PRODUCTS_FILE
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)

    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding=ENCODING)
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = ''

    return df[COLUMNS]


def save_products(df: pd.DataFrame, path: Path | None = None) -> None:
    """Write the catalog back, always in canonical column order."""
    path = path or PRODUCTS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    df[COLUMNS].to_csv(path, index=False, encoding=ENCODING)


def upsert(df: pd.DataFrame, product: dict[str, str], original_sku: str = '') -> pd.DataFrame:
    """Insert or replace a product, matching on SKU.

    ``original_sku`` identifies the row being edited, so that renaming a SKU
    updates the existing row instead of leaving a duplicate behind.
    """
    key = original_sku or product['SKU']
    df = df.copy()
    matches = df.index[df['SKU'] == key]

    if len(matches):
        for col, value in product.items():
            df.loc[matches[0], col] = value
    else:
        df = pd.concat([df, pd.DataFrame([product], columns=COLUMNS)], ignore_index=True)

    return df


def delete(df: pd.DataFrame, sku: str) -> pd.DataFrame:
    """Remove a product by SKU."""
    return df[df['SKU'] != sku].reset_index(drop=True)


def get_product(df: pd.DataFrame, sku: str) -> dict[str, str]:
    """Fetch one product as a plain dict, or a blank one if the SKU is unknown."""
    matches = df[df['SKU'] == sku]
    if matches.empty:
        return empty_product()
    return matches.iloc[0].to_dict()


def split_list(value: str) -> list[str]:
    """Split a comma-separated cell (tags, image URLs) into clean items."""
    return [item.strip() for item in value.split(',') if item.strip()]


def join_list(items: list[str]) -> str:
    """Join items back into the comma-separated form WooCommerce expects."""
    return ', '.join(item.strip() for item in items if item.strip())
