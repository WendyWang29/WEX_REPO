"""Column layout of the WooCommerce product import CSV (Italian locale).

The column order in COLUMNS is the export order and must not change: WooCommerce
matches on header names, but keeping the original order keeps diffs readable.

Of the 41 columns, only the 13 in FIELDS (plus the three special ones handled
directly by the UI) ever differ between products. The rest live in DEFAULTS and
are written verbatim on every row.
"""

from dataclasses import dataclass

# All columns, in export order.
COLUMNS = [
    'ID',
    'Tipo',
    'SKU',
    'GTIN, UPC, EAN, o ISBN',
    'Nome',
    'Pubblicato',
    'In primo piano?',
    'Visibilità nel catalogo',
    'Breve descrizione',
    'Descrizione',
    'Data di partenza del prezzo in saldo',
    "Data in cui termina l'offerta",
    'Stato delle imposte',
    'Aliquota di imposta',
    'In stock?',
    'Magazzino',
    'Quantità in magazzino bassa',
    'Abilita gli ordini arretrati?',
    'Venduto singolarmente?',
    'Peso (kg)',
    'Lunghezza (cm)',
    'Larghezza (cm)',
    'Altezza (cm)',
    'Permetti le recensioni clienti?',
    'Nota di acquisto',
    'Prezzo in offerta',
    'Prezzo di listino',
    'Categorie',
    'Tag',
    'Classe di spedizione',
    'Immagine',
    'Limite di download',
    'Scarica i giorni di scadenza',
    'Genitore',
    'Prodotti raggruppati',
    'Up-sell',
    'Cross-sell',
    'URL esterno',
    'Testo del pulsante',
    'Posizione',
    'Marchi',
]

# Columns identical for every product; filled in automatically.
DEFAULTS = {
    'ID': '',
    'Tipo': 'external',
    'GTIN, UPC, EAN, o ISBN': '',
    'Pubblicato': '1',
    'In primo piano?': '0',
    'Visibilità nel catalogo': 'visible',
    'Data di partenza del prezzo in saldo': '',
    "Data in cui termina l'offerta": '',
    'Stato delle imposte': 'taxable',
    'Aliquota di imposta': '',
    'In stock?': '1',
    'Magazzino': '',
    'Quantità in magazzino bassa': '1',
    'Abilita gli ordini arretrati?': '0',
    'Venduto singolarmente?': '0',
    'Permetti le recensioni clienti?': '0',
    'Nota di acquisto': '',
    'Classe di spedizione': '',
    'Limite di download': '',
    'Scarica i giorni di scadenza': '',
    'Genitore': '',
    'Prodotti raggruppati': '',
    'Up-sell': '',
    'Cross-sell': '',
    'Testo del pulsante': '',
    'Posizione': '0',
    'Marchi': '',
}

# Columns the UI renders with purpose-built widgets rather than a generic input.
CATEGORIES_COL = 'Categorie'
TAGS_COL = 'Tag'
IMAGES_COL = 'Immagine'


@dataclass(frozen=True)
class Field:
    """One editable column and how the form should render it."""

    name: str          # exact CSV column name
    label: str         # shown in the form
    kind: str          # text | textarea | price | number
    required: bool = False
    help: str = ''


# Editable columns, grouped as they appear in the form. Dimensions come before
# identification because the generated SKU depends on them: by the time the SKU
# is drawn, category and size are already known for this run.
SECTIONS: dict[str, list[Field]] = {
    'Dimensioni': [
        Field('Peso (kg)', 'Peso (kg)', 'number'),
        Field('Lunghezza (cm)', 'Lunghezza (cm)', 'number'),
        Field('Larghezza (cm)', 'Larghezza (cm)', 'number'),
        Field('Altezza (cm)', 'Altezza (cm)', 'number',
              help='La misura maggiore fra le tre finisce nello SKU.'),
    ],
    'Identificazione': [
        Field('SKU', 'SKU', 'text', required=True,
              help='Generato automaticamente alla creazione. Non va più cambiato: '
                   'per WooCommerce uno SKU diverso significa un prodotto diverso.'),
        Field('Nome', 'Nome prodotto', 'text', required=True),
        Field('URL esterno', 'Link affiliato', 'text', required=True,
              help='Pagina di vendita (es. subito.it) a cui punta il pulsante.'),
    ],
    'Prezzi': [
        Field('Prezzo di listino', 'Prezzo di listino (€)', 'price', required=True),
        Field('Prezzo in offerta', 'Prezzo in offerta (€)', 'price',
              help='Lasciare vuoto se il prodotto non è in saldo.'),
    ],
    'Descrizioni': [
        Field('Breve descrizione', 'Breve descrizione', 'textarea'),
        Field('Descrizione', 'Descrizione completa', 'textarea'),
    ],
}

FIELDS = [f for group in SECTIONS.values() for f in group]
FIELDS_BY_NAME = {f.name: f for f in FIELDS}


def empty_product() -> dict[str, str]:
    """A blank product row with every column present and defaults applied."""
    row = {col: '' for col in COLUMNS}
    row.update(DEFAULTS)
    return row
