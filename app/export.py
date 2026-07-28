"""Validation and generation of the WooCommerce import file.

The export is deliberately disposable: it is rebuilt from data/products.csv
every time, so the working catalog stays the only thing worth backing up.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from categories import canonicalize, load_tree
from rules import (apply_image_groups, apply_tag_defaults, effective_images,
                   load_group_members, load_image_groups, load_tag_defaults)
from schema import COLUMNS, DEFAULTS, IMAGES_COL
from storage import ENCODING, split_list

EXPORT_DIR = Path(__file__).resolve().parent.parent / 'export'

ERROR = 'error'
WARNING = 'warning'


@dataclass(frozen=True)
class Issue:
    """One validation problem, tied to the product it came from."""

    sku: str
    level: str
    message: str


def _is_number(value: str) -> bool:
    try:
        float(value.replace(',', '.'))
    except ValueError:
        return False
    return True


def validate(df: pd.DataFrame) -> list[Issue]:
    """Check every product. Errors block export; warnings do not."""
    issues: list[Issue] = []
    tree = load_tree()
    groups, members = load_image_groups(), load_group_members()

    seen: dict[str, int] = {}
    for position, row in enumerate(df.to_dict('records'), start=1):
        sku = row['SKU'].strip()
        label = sku or f'(riga {position} senza SKU)'

        if not sku:
            issues.append(Issue(label, ERROR, 'SKU mancante'))
        elif sku in seen:
            issues.append(Issue(label, ERROR, f'SKU duplicato (già usato alla riga {seen[sku]})'))
        else:
            seen[sku] = position

        if not row['Nome'].strip():
            issues.append(Issue(label, ERROR, 'Nome mancante'))

        link = row['URL esterno'].strip()
        if not link:
            issues.append(Issue(label, ERROR, 'Link affiliato mancante'))
        elif not link.startswith(('http://', 'https://')):
            issues.append(Issue(label, ERROR, f'Link affiliato non valido: {link}'))

        listino = row['Prezzo di listino'].strip()
        if not listino:
            issues.append(Issue(label, ERROR, 'Prezzo di listino mancante'))
        elif not _is_number(listino):
            issues.append(Issue(label, ERROR, f'Prezzo di listino non numerico: {listino!r}'))

        offerta = row['Prezzo in offerta'].strip()
        if offerta:
            if not _is_number(offerta):
                issues.append(Issue(label, ERROR, f'Prezzo in offerta non numerico: {offerta!r}'))
            elif _is_number(listino) and float(offerta) >= float(listino):
                issues.append(Issue(label, WARNING,
                                    'Prezzo in offerta maggiore o uguale al prezzo di listino'))

        _, problems = canonicalize(row['Categorie'], tree)
        issues += [Issue(label, ERROR, problem) for problem in problems]

        # Checked on the effective list: a product with no images of its own is
        # still fine if a group supplies them.
        images = effective_images(sku, row[IMAGES_COL], groups, members)
        if not images:
            issues.append(Issue(label, WARNING, 'Nessuna immagine'))
        for url in images:
            if not url.startswith(('http://', 'https://')):
                issues.append(Issue(label, ERROR, f'URL immagine non valido: {url}'))

        if not row['Breve descrizione'].strip():
            issues.append(Issue(label, WARNING, 'Breve descrizione mancante'))

    return issues


def check_image_urls(df: pd.DataFrame, timeout: float = 6.0) -> list[Issue]:
    """Request every image URL once and report the ones that do not resolve.

    Kept separate from validate() because it touches the network and takes a few
    seconds per product; the UI runs it only on demand.
    """
    issues: list[Issue] = []
    checked: dict[str, int | str] = {}
    groups, members = load_image_groups(), load_group_members()

    for row in df.to_dict('records'):
        sku = row['SKU'].strip() or '(senza SKU)'
        for url in effective_images(row['SKU'], row[IMAGES_COL], groups, members):
            if url not in checked:
                try:
                    response = requests.head(url, timeout=timeout, allow_redirects=True)
                    # Some hosts reject HEAD outright; retry those with a ranged GET.
                    if response.status_code >= 400:
                        response = requests.get(url, timeout=timeout, stream=True,
                                                headers={'Range': 'bytes=0-0'})
                    checked[url] = response.status_code
                except requests.RequestException as exc:
                    checked[url] = type(exc).__name__

            status = checked[url]
            if not (isinstance(status, int) and status < 400):
                issues.append(Issue(sku, WARNING, f'Immagine non raggiungibile ({status}): {url}'))

    return issues


def build(df: pd.DataFrame) -> pd.DataFrame:
    """Produce the import-ready frame.

    Fixed columns are filled in, categories are normalised, and the per-category
    default tags are merged into each product's own tags — the only place that
    merge happens, so editing the defaults changes every future export.
    """
    out = df.copy()
    tree = load_tree()

    for col, value in DEFAULTS.items():
        out[col] = value

    out['Categorie'] = [canonicalize(value, tree)[0] for value in out['Categorie']]
    if not out.empty:
        out['Tag'] = apply_tag_defaults(out, load_tag_defaults())
        out[IMAGES_COL] = apply_image_groups(out, load_image_groups(), load_group_members())

    return out[COLUMNS]


def write(df: pd.DataFrame, directory: Path | None = None) -> Path:
    """Write the import file and return its path."""
    directory = directory or EXPORT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'wex_import_{date.today():%Y-%m-%d}.csv'
    build(df).to_csv(path, index=False, encoding=ENCODING)
    return path
