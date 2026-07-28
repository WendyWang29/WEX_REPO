"""WEX catalog manager — Streamlit entry point.

Run with:  streamlit run app/main.py

Three pages: browse the catalog, edit or create a product, export the
WooCommerce import file.
"""

import sys
from pathlib import Path

# `streamlit run` puts this directory on sys.path, but the test harness and a
# plain `python app/main.py` do not; adding it keeps every entry point working.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import streamlit as st

import export as exporter
import rules
import sku as sku_codes
import storage
from categories import NO_SUBCATEGORY, format_value, load_codes, load_tree, split_value
from schema import FIELDS_BY_NAME, IMAGES_COL, SECTIONS, TAGS_COL, empty_product

NEW = '__new__'
PAGES = ['Catalogo', 'Prodotto', 'Automazioni', 'Esporta']

st.set_page_config(page_title='WEX — Catalogo prodotti', page_icon='🪨', layout='wide')


# ---------------------------------------------------------------- data access

@st.cache_data
def cached_products() -> pd.DataFrame:
    """The catalog, reloaded only when the cache is cleared after a save."""
    return storage.load_products()


@st.cache_data
def cached_tree() -> dict[str, list[str]]:
    return load_tree()


@st.cache_data
def cached_codes() -> dict[str, str]:
    return load_codes()


@st.cache_data
def cached_tag_defaults() -> dict[str, list[str]]:
    return rules.load_tag_defaults()


@st.cache_data
def cached_image_groups() -> dict[str, list[str]]:
    return rules.load_image_groups()


@st.cache_data
def cached_group_members() -> dict[str, list[str]]:
    return rules.load_group_members()


def commit_rules(tag_defaults: dict[str, list[str]] | None = None,
                 image_groups: dict[str, list[str]] | None = None,
                 group_members: dict[str, list[str]] | None = None) -> None:
    """Persist shared rules and drop the matching caches."""
    if tag_defaults is not None:
        rules.save_tag_defaults(tag_defaults)
        cached_tag_defaults.clear()
    if image_groups is not None:
        rules.save_image_groups(image_groups)
        cached_image_groups.clear()
    if group_members is not None:
        rules.save_group_members(group_members)
        cached_group_members.clear()


def commit(df: pd.DataFrame) -> None:
    """Persist the catalog and invalidate the cached copy."""
    storage.save_products(df)
    cached_products.clear()


def go(page: str, sku: str | None = None) -> None:
    """Switch page, optionally selecting a product, and rerun immediately.

    The target is parked in ``pending_page`` rather than written straight to the
    navigation widget's key: Streamlit refuses assignments to a widget's key
    once that widget has been drawn, and the sidebar is drawn before any page
    body runs. main() applies the parked value at the top of the next run.
    """
    st.session_state.pending_page = page
    if sku is not None:
        st.session_state.editing = sku
    st.rerun()


# -------------------------------------------------------------------- helpers

def first_image(row: dict[str, str]) -> str | None:
    """Cover image, falling back to the product's image groups."""
    images = rules.effective_images(row['SKU'], row[IMAGES_COL],
                                    cached_image_groups(), cached_group_members())
    return images[0] if images else None


def sku_widget(product: dict[str, str], values: dict[str, str], parent: str, child: str,
               codes: dict[str, str], existing: list[str], is_new: bool, key) -> str:
    """Draw the SKU field: generated for new products, editable for existing ones.

    For a new product the generated code is rendered as text rather than a
    disabled input on purpose — a widget with a key keeps its first value across
    reruns, which would freeze the preview while category and size change.
    """
    category_code = codes.get(parent, '')
    subcategory_code = None if child == NO_SUBCATEGORY else codes.get(f'{parent} > {child}')
    # values already holds this run's dimensions: Dimensioni is drawn first.
    current = product | values

    if not is_new:
        value = st.text_input('SKU *', value=product['SKU'], key=key('SKU'),
                              help=FIELDS_BY_NAME['SKU'].help)
        if value.strip() != product['SKU'].strip():
            st.warning('Stai cambiando lo SKU: per WooCommerce diventerà un prodotto '
                       'nuovo, separato da quello già online.')
        else:
            st.caption(sku_codes.describe(value, codes))
        return value

    suggested = sku_codes.generate(category_code, subcategory_code, current, existing)

    if st.checkbox('Scrivi lo SKU manualmente', key=key('sku_manual')):
        return st.text_input('SKU *', value=suggested, key=key('SKU'),
                             help=FIELDS_BY_NAME['SKU'].help)

    st.markdown(f'**SKU** &nbsp; `{suggested}`')
    st.caption(f'{sku_codes.describe(suggested, codes)} — assegnato al salvataggio.')
    if sku_codes.major_size(current) == 0:
        st.caption('⚠️ Nessuna dimensione inserita: lo SKU conterrà 000.')

    return suggested


def price_label(row: dict[str, str]) -> str:
    listino, offerta = row['Prezzo di listino'].strip(), row['Prezzo in offerta'].strip()
    if not listino:
        return '—'
    if offerta:
        return f'~~€ {listino}~~  **€ {offerta}**'
    return f'€ {listino}'


# --------------------------------------------------------------------- pagina

def page_catalogo(df: pd.DataFrame) -> None:
    st.title('Catalogo')

    tree = cached_tree()
    options = ['Tutte le categorie']
    for parent, children in tree.items():
        options.append(parent)
        options += [f'{parent} > {child}' for child in children]

    left, right = st.columns([3, 2])
    query = left.text_input('Cerca', placeholder='Nome, SKU o tag…').strip()
    chosen = right.selectbox('Categoria', options)

    results = df
    if query and not results.empty:
        # Search against the tags the product will actually be exported with, so
        # a category-level default is findable too.
        tags = rules.apply_tag_defaults(results, cached_tag_defaults())
        haystack = results['Nome'] + ' ' + results['SKU'] + ' ' + tags
        results = results[haystack.str.contains(query, case=False, regex=False)]
    if chosen != 'Tutte le categorie':
        results = results[results['Categorie'].str.contains(chosen, case=False, regex=False)]

    st.caption(f'{len(results)} prodotti su {len(df)}')

    if st.button('➕ Nuovo prodotto', type='primary'):
        go('Prodotto', NEW)

    if results.empty:
        st.info('Nessun prodotto trovato.')
        return

    rows = results.to_dict('records')
    for start in range(0, len(rows), 3):
        for column, row in zip(st.columns(3), rows[start:start + 3]):
            with column, st.container(border=True):
                url = first_image(row)
                if url:
                    st.image(url, width='stretch')
                else:
                    st.caption('— nessuna immagine —')
                st.markdown(f'**{row["Nome"] or "(senza nome)"}**')
                st.caption(f'{row["SKU"]} · {row["Categorie"].split(",")[0]}')
                st.markdown(price_label(row))
                if st.button('Modifica', key=f'edit::{row["SKU"]}::{start}'):
                    go('Prodotto', row['SKU'])


def page_prodotto(df: pd.DataFrame) -> None:
    skus = df['SKU'].tolist()
    selected = st.session_state.get('editing', NEW)
    if selected != NEW and selected not in skus:
        selected = NEW

    choice = st.sidebar.selectbox(
        'Prodotto da modificare',
        [NEW] + skus,
        index=0 if selected == NEW else skus.index(selected) + 1,
        format_func=lambda s: '➕ Nuovo prodotto' if s == NEW else s,
    )
    if choice != selected:
        go('Prodotto', choice)

    is_new = selected == NEW
    product = empty_product() if is_new else storage.get_product(df, selected)
    st.title('Nuovo prodotto' if is_new else product['Nome'] or selected)

    # Widget keys are scoped to the product so switching selection resets them
    # instead of carrying the previous product's text over.
    def key(name: str) -> str:
        return f'{selected}::{name}'

    # Category comes first: the SKU is built from it, so it has to be known
    # before the identification fields are drawn further down.
    st.subheader('Categoria')
    tree, codes = cached_tree(), cached_codes()
    parents = list(tree)
    current_parent, current_child = split_value(product['Categorie'])
    parent = st.selectbox(
        'Categoria principale', parents,
        index=parents.index(current_parent) if current_parent in parents else 0,
        key=key('parent'),
    )
    children = [NO_SUBCATEGORY] + tree[parent]
    child = st.selectbox(
        'Sottocategoria', children,
        index=children.index(current_child) if current_child in children else 0,
        key=key('child'),
    )
    st.caption(f'Verrà scritto: `{format_value(parent, child)}`')

    values: dict[str, str] = {}
    for section, fields in SECTIONS.items():
        st.subheader(section)
        columns = st.columns(len(fields)) if fields[0].kind in ('price', 'number') else [st]
        for index, field in enumerate(fields):
            if field.name == 'SKU':
                values['SKU'] = sku_widget(product, values, parent, child, codes, skus,
                                           is_new, key)
                continue
            target = columns[index % len(columns)]
            label = field.label + (' *' if field.required else '')
            widget = target.text_area if field.kind == 'textarea' else target.text_input
            kwargs = {'height': 120} if field.kind == 'textarea' else {}
            values[field.name] = widget(
                label, value=product[field.name], key=key(field.name),
                help=field.help or None, **kwargs,
            )

    # Images sit outside the field loop so the preview refreshes as they change.
    st.subheader('Immagini')
    st.caption('Un URL per riga. Il primo è l\'immagine principale, gli altri la galleria.')
    images_text = st.text_area(
        'URL immagini',
        value='\n'.join(storage.split_list(product[IMAGES_COL])),
        height=140,
        key=key('images'),
        label_visibility='collapsed',
    )
    images = [line.strip() for line in images_text.splitlines() if line.strip()]
    if images:
        for start in range(0, len(images), 6):
            for column, url in zip(st.columns(6), images[start:start + 6]):
                column.image(url, width='stretch')

    if not is_new:
        members = cached_group_members()
        belongs_to = rules.groups_of(selected, members)
        if belongs_to:
            from_groups = rules.group_images(selected, cached_image_groups(), members)
            st.caption(f'In coda arrivano {len(from_groups)} immagini dai gruppi ' +
                       ', '.join(f'«{name}»' for name in belongs_to) +
                       ' — si modificano da *Automazioni*.')
            for start in range(0, len(from_groups), 6):
                for column, url in zip(st.columns(6), from_groups[start:start + 6]):
                    column.image(url, width='stretch')

    st.subheader('Tag')
    inherited = rules.inherited_tags(format_value(parent, child), cached_tag_defaults())
    if inherited:
        st.caption('Ereditati dalla categoria: ' +
                   ' '.join(f'`{tag}`' for tag in inherited) +
                   ' — si aggiungono da soli, non serve riscriverli.')
    tags = st.text_area(
        'Tag specifici di questo prodotto, separati da virgola',
        value=product[TAGS_COL], height=80,
        key=key('tags'), label_visibility='collapsed',
    )

    values[IMAGES_COL] = storage.join_list(images)
    values['Categorie'] = format_value(parent, child)
    values[TAGS_COL] = storage.join_list(storage.split_list(tags))

    st.divider()
    save, remove = st.columns([1, 4])

    if save.button('💾 Salva', type='primary'):
        missing = [f.label for group in SECTIONS.values() for f in group
                   if f.required and not values[f.name].strip()]
        if missing:
            st.error('Campi obbligatori mancanti: ' + ', '.join(missing))
        elif is_new and values['SKU'].strip() in skus:
            st.error(f'Lo SKU {values["SKU"]} esiste già.')
        else:
            updated = product | values
            commit(storage.upsert(df, updated, original_sku='' if is_new else selected))
            # A hand-edited SKU must carry its image groups across with it.
            if not is_new and values['SKU'].strip() != selected:
                commit_rules(group_members=rules.rename_sku(
                    selected, values['SKU'].strip(), cached_group_members()))
            st.session_state.editing = values['SKU'].strip()
            st.success('Prodotto salvato.')
            st.rerun()

    if not is_new:
        with remove.popover('🗑 Elimina'):
            st.write(f'Eliminare **{selected}** dal catalogo?')
            if st.button('Conferma eliminazione'):
                commit(storage.delete(df, selected))
                commit_rules(group_members=rules.forget_sku(selected, cached_group_members()))
                go('Catalogo', NEW)


def section_tag_defaults(df: pd.DataFrame) -> None:
    """Editor for the per-category default tags."""
    st.subheader('Tag predefiniti per categoria')
    st.caption('Ogni prodotto eredita i tag della sua categoria e della sua '
               'sottocategoria, in aggiunta ai propri. I tag non vengono copiati nei '
               'prodotti: si uniscono al momento dell\'export, quindi modificarli qui '
               'aggiorna anche i prodotti già creati.')

    tree, defaults = cached_tree(), cached_tag_defaults()
    edited: dict[str, list[str]] = {}

    for parent, children in tree.items():
        counts = df['Categorie'].str.startswith(parent).sum() if not df.empty else 0
        with st.expander(f'{parent} — {counts} prodotti'):
            edited[parent] = storage.split_list(st.text_input(
                f'Tag di tutta la categoria «{parent}»',
                value=storage.join_list(defaults.get(parent, [])),
                key=f'tagdef::{parent}',
                placeholder='esterno, rustico, pietra naturale, giardino',
            ))
            for child in children:
                path = f'{parent} > {child}'
                edited[path] = storage.split_list(st.text_input(
                    f'↳ solo «{child}»',
                    value=storage.join_list(defaults.get(path, [])),
                    key=f'tagdef::{path}',
                    placeholder='lavello, lavandino, massello',
                ))

    if st.button('💾 Salva tag predefiniti', type='primary'):
        commit_rules(tag_defaults=edited)
        st.success('Tag predefiniti salvati.')
        st.rerun()

    example = next((r for r in df.to_dict('records') if r['Categorie']), None)
    if example:
        st.caption('Esempio su un prodotto reale — '
                   f'**{example["Nome"] or example["SKU"]}**: '
                   f'`{storage.join_list(rules.effective_tags(example["Categorie"], example["Tag"], defaults))}`')


NEW_GROUP = '➕ Nuovo gruppo'


def section_image_groups(df: pd.DataFrame) -> None:
    """Editor for named image groups and the products assigned to them."""
    st.subheader('Gruppi di immagini')
    st.caption('Un gruppo è un insieme di immagini condiviso da più prodotti — per '
               'esempio le foto di piletta e rubinetto. Le immagini non vengono copiate '
               'nei prodotti: cambiando il gruppo cambiano tutti i prodotti che ne fanno '
               'parte, e togliendo un\'immagine sparisce ovunque.')

    groups, members = cached_image_groups(), cached_group_members()
    names = list(groups)
    chosen = st.selectbox('Gruppo', [NEW_GROUP] + names, key='group_choice')
    is_new = chosen == NEW_GROUP

    name = st.text_input('Nome del gruppo', value='' if is_new else chosen,
                         key=f'group_name::{chosen}',
                         placeholder='Accessori lavello')

    urls_text = st.text_area(
        'Immagini del gruppo, un URL per riga', height=140,
        value='' if is_new else '\n'.join(groups[chosen]),
        key=f'group_urls::{chosen}',
        placeholder='https://mondopietra.it/piletta.jpg\n'
                    'https://mondopietra.it/rubinetto.jpg',
    )
    urls = [line.strip() for line in urls_text.splitlines() if line.strip()]
    if urls:
        for start in range(0, len(urls), 6):
            for column, url in zip(st.columns(6), urls[start:start + 6]):
                column.image(url, width='stretch')

    current_members = [] if is_new else members.get(chosen, [])
    selected = membership_editor(df, current_members, chosen)

    invalid = [u for u in urls if not u.startswith(('http://', 'https://'))]
    if invalid:
        st.error('URL non validi: ' + ', '.join(invalid))

    save, delete = st.columns([1, 4])
    if save.button('💾 Salva gruppo', type='primary', disabled=bool(invalid)):
        if not name.strip():
            st.error('Il gruppo deve avere un nome.')
        elif is_new and name.strip() in groups:
            st.error(f'Esiste già un gruppo «{name.strip()}».')
        else:
            updated_groups = {k: v for k, v in groups.items() if k != chosen}
            updated_members = {k: v for k, v in members.items() if k != chosen}
            updated_groups[name.strip()] = urls
            updated_members[name.strip()] = selected
            commit_rules(image_groups=updated_groups, group_members=updated_members)
            st.session_state.pop(f'gm_picked::{chosen}', None)
            st.success(f'Gruppo «{name.strip()}» salvato su {len(selected)} prodotti.')
            st.rerun()

    if not is_new:
        with delete.popover('🗑 Elimina gruppo'):
            st.write(f'Eliminare «{chosen}»? Le sue immagini spariranno dai '
                     f'{len(current_members)} prodotti che lo usano.')
            if st.button('Conferma eliminazione gruppo'):
                commit_rules(
                    image_groups={k: v for k, v in groups.items() if k != chosen},
                    group_members={k: v for k, v in members.items() if k != chosen},
                )
                st.rerun()


def membership_editor(df: pd.DataFrame, current: list[str], group_key: str) -> list[str]:
    """Checkbox grid for choosing which products belong to a group.

    Filters only narrow which rows are shown; products hidden by a filter keep
    whatever membership they already had, so filtering can never silently drop
    a product out of the group.
    """
    st.markdown('**Prodotti nel gruppo**')
    if df.empty:
        st.info('Nessun prodotto in catalogo.')
        return current

    tree = cached_tree()
    sizes = pd.Series([sku_codes.major_size(row) for row in df.to_dict('records')],
                      index=df.index)

    left, middle, right = st.columns(3)
    parent = left.selectbox('Filtra per categoria', ['Tutte'] + list(tree),
                            key=f'gm_parent::{group_key}')
    chosen_children = middle.multiselect('Sottocategorie', tree.get(parent, []),
                                         key=f'gm_children::{group_key}',
                                         placeholder='tutte')
    chosen_sizes = right.multiselect('Dimensione (cm)', sorted({int(s) for s in sizes}),
                                     key=f'gm_sizes::{group_key}', placeholder='tutte')

    visible = pd.Series(True, index=df.index)
    if parent != 'Tutte':
        visible &= df['Categorie'].str.startswith(parent)
    if chosen_children:
        visible &= df['Categorie'].str.contains(
            '|'.join(f'> {child},' for child in chosen_children), regex=True)
    if chosen_sizes:
        visible &= sizes.isin(chosen_sizes)

    shown = df[visible]
    if shown.empty:
        st.caption('Nessun prodotto corrisponde ai filtri.')
        return current

    # "Select all" cannot write into the data editor's own key once the editor
    # has been drawn, so the checked set is held in a plain session value and the
    # editor is rebuilt from it under a fresh key each time it changes.
    picked_key = f'gm_picked::{group_key}'
    version_key = f'gm_version::{group_key}'
    checked = st.session_state.get(picked_key, current)
    version = st.session_state.setdefault(version_key, 0)

    table = pd.DataFrame({
        'Nel gruppo': shown['SKU'].isin(checked),
        'SKU': shown['SKU'],
        'Nome': shown['Nome'],
        'cm': sizes[visible],
    })
    edited = st.data_editor(
        table, hide_index=True, width='stretch', key=f'gm_table::{group_key}::{version}',
        column_config={'Nel gruppo': st.column_config.CheckboxColumn(required=True)},
        disabled=['SKU', 'Nome', 'cm'],
    )

    hidden_members = [sku for sku in checked if sku not in set(shown['SKU'])]
    selected = hidden_members + edited.loc[edited['Nel gruppo'], 'SKU'].tolist()

    st.caption(f'**{len(selected)}** prodotti nel gruppo' +
               (f' — {len(hidden_members)} nascosti dai filtri, comunque inclusi'
                if hidden_members else ''))

    everything, nothing = st.columns([1, 4])
    if everything.button('Seleziona tutti i filtrati', key=f'gm_all::{group_key}'):
        st.session_state[picked_key] = hidden_members + shown['SKU'].tolist()
        st.session_state[version_key] = version + 1
        st.rerun()
    if nothing.button('Deseleziona i filtrati', key=f'gm_none::{group_key}'):
        st.session_state[picked_key] = hidden_members
        st.session_state[version_key] = version + 1
        st.rerun()

    return selected


def page_automazioni(df: pd.DataFrame) -> None:
    st.title('Automazioni')
    section_tag_defaults(df)
    st.divider()
    section_image_groups(df)


def page_esporta(df: pd.DataFrame) -> None:
    st.title('Esporta')
    st.caption(f'{len(df)} prodotti nel catalogo.')

    issues = exporter.validate(df)
    if st.button('🔗 Controlla anche le immagini online'):
        with st.spinner('Verifica URL immagini…'):
            st.session_state.image_issues = exporter.check_image_urls(df)
    issues = issues + st.session_state.get('image_issues', [])

    errors = [i for i in issues if i.level == exporter.ERROR]
    warnings = [i for i in issues if i.level == exporter.WARNING]

    if errors:
        st.error(f'{len(errors)} errori bloccanti.')
        st.dataframe(pd.DataFrame([(i.sku, i.message) for i in errors],
                                  columns=['SKU', 'Problema']), width='stretch')
    else:
        st.success('Nessun errore bloccante.')

    if warnings:
        with st.expander(f'{len(warnings)} avvisi (non bloccanti)'):
            st.dataframe(pd.DataFrame([(i.sku, i.message) for i in warnings],
                                      columns=['SKU', 'Avviso']), width='stretch')

    st.divider()
    if errors:
        st.info('Correggi gli errori per abilitare l\'export.')
        return

    csv = exporter.build(df).to_csv(index=False).encode(storage.ENCODING)
    st.download_button('⬇️ Scarica CSV per WooCommerce', csv,
                       file_name='wex_import.csv', mime='text/csv', type='primary')
    if st.button('Salva una copia in export/'):
        st.success(f'Salvato in `{exporter.write(df)}`')


# ------------------------------------------------------------------------ app

def main() -> None:
    st.session_state.setdefault('nav', 'Catalogo')
    st.session_state.setdefault('editing', NEW)
    if 'pending_page' in st.session_state:
        st.session_state.nav = st.session_state.pop('pending_page')

    df = cached_products()
    st.sidebar.title('WEX')
    page = st.sidebar.radio('Sezione', PAGES, key='nav')
    st.sidebar.caption(f'{len(df)} prodotti · data/products.csv')

    {'Catalogo': page_catalogo, 'Prodotto': page_prodotto,
     'Automazioni': page_automazioni, 'Esporta': page_esporta}[page](df)


main()
