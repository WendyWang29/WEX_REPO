# WEX — gestione catalogo prodotti

Interfaccia locale per creare, modificare e cercare i prodotti, e per generare il
CSV da importare in WooCommerce.

## Avvio

```
conda activate streamlit-app
streamlit run app/main.py
```

Si apre su <http://localhost:8501>. Per fermarlo: `Ctrl+C` nel terminale.

## Come funziona

`data/products.csv` è la **fonte di verità**: contiene tutti i prodotti ed è il
file principale da salvare e versionare. Accanto stanno le regole condivise:

```
data/products.csv              i prodotti
data/tag_defaults.csv          tag predefiniti per categoria
data/image_groups.csv          gruppi di immagini
data/image_group_members.csv   quali prodotti stanno in quali gruppi
```

L'app legge e scrive solo questi quattro file.

Il file in `export/` è **usa e getta**: viene rigenerato ogni volta dalla pagina
*Esporta* ed è quello da caricare in WooCommerce.

```
data/products.csv   →   [validazione]   →   export/wex_import_AAAA-MM-GG.csv
     (si modifica)                              (si importa, poi si scarta)
```

`data/originale_giugno_2026.csv` è l'export originale di giugno 2026, con i 46
prodotti e i vecchi SKU numerici. È tenuto intatto come archivio e non viene mai
letto né scritto dall'app: il catalogo è ripartito da zero con i nuovi SKU.

## Le tre pagine

- **Catalogo** — ricerca per nome, SKU o tag; filtro per categoria; griglia con
  anteprima immagini. Il pulsante *Modifica* apre il prodotto.
- **Prodotto** — creazione e modifica. Si parte dalla categoria e dalle
  dimensioni, da cui l'app ricava lo SKU; poi nome, link, prezzi, immagini e tag.
  Le categorie si scelgono da menu a tendina generati da `categories.txt`, mai
  scritte a mano. Le immagini si inseriscono un URL per riga, con anteprima
  immediata.
- **Automazioni** — tag predefiniti per categoria e gruppi di immagini condivisi
  fra più prodotti.
- **Esporta** — controlli di validità, poi download del CSV pronto per WooCommerce.

## Tag predefiniti

In *Automazioni* si assegnano dei tag a un'intera categoria o sottocategoria. Un
prodotto eredita quelli della sua categoria **più** quelli della sua
sottocategoria, in aggiunta ai tag scritti nella sua scheda.

```
Arredamento da Esterno              esterno, rustico, pietra naturale, giardino
  └ Lavelli rustici                 lavello, lavandino, massello
     prodotto ELR0800001            granito
     → esportato con:  esterno, rustico, pietra naturale, giardino,
                       lavello, lavandino, massello, granito
```

I tag **non vengono copiati** dentro i prodotti: restano una regola in
`data/tag_defaults.csv` e si uniscono solo al momento dell'export. Aggiungere un
tag a una categoria lo aggiunge quindi anche ai prodotti creati mesi prima, senza
doverli ritoccare. I duplicati vengono eliminati ignorando maiuscole e minuscole.

Nella scheda prodotto i tag ereditati sono mostrati sopra il campo Tag, così si
vede cosa verrà aggiunto senza doverlo riscrivere.

## Gruppi di immagini

Un gruppo è un insieme di immagini condiviso da più prodotti: le foto della
piletta, del rubinetto, di un accessorio. Si creano in *Automazioni*, si dà un
nome, si incollano gli URL e si scelgono i prodotti che ne fanno parte.

```
Accessori lavello   img1, img2, img3   →   A, B, C
Piletta e scarico   img1, img4, img7   →   S, Y, Z
```

Gruppi diversi possono avere immagini in comune, e un prodotto può stare in più
gruppi: le immagini si sommano senza doppioni.

Come i tag, le immagini dei gruppi **non vengono copiate nei prodotti**: restano
in `data/image_groups.csv` e si uniscono all'export. Questo è ciò che le rende
modificabili in un secondo momento:

- sostituire un URL nel gruppo lo sostituisce in tutti i prodotti che lo usano;
- togliere un'immagine dal gruppo la fa sparire da tutti quei prodotti;
- eliminare il gruppo la fa sparire ovunque, senza toccare le immagini proprie
  dei prodotti.

L'ordine è sempre **prima le immagini del prodotto, poi quelle dei gruppi**, così
l'immagine principale resta quella scelta sul prodotto. Un prodotto senza
immagini proprie prende come principale la prima del gruppo.

Per scegliere i prodotti si usa una tabella con una casella per riga. I filtri
per categoria, sottocategoria e dimensione servono solo a restringere la vista:
un prodotto già nel gruppo ma nascosto da un filtro **resta nel gruppo**, e il
conteggio sotto la tabella lo segnala. I pulsanti *Seleziona tutti i filtrati* e
*Deseleziona i filtrati* agiscono solo sulle righe visibili.

Le appartenenze stanno in `data/image_group_members.csv`, per SKU. Se un prodotto
viene eliminato o gli si cambia lo SKU a mano, i gruppi vengono aggiornati da
soli.

Nota: l'appartenenza è esplicita, non una regola. Un prodotto creato dopo non
entra da solo in un gruppo, anche se corrisponde agli stessi filtri: va aggiunto.

## Categorie e codici

`categories.txt` è l'unico posto dove si definiscono le categorie: nomi a inizio
riga, sottocategorie indentate sotto, e fra parentesi quadre il codice usato
negli SKU.

```
Arredamento da Esterno [E]
    Lavelli rustici [LR]
    Fontane [FO]
```

Per aggiungere una categoria basta modificare il file e ricaricare la pagina. Il
codice è obbligatorio: se manca, l'app si ferma con un errore invece di generare
SKU sbagliati. I codici sono assegnati a mano e non ricavati dalle iniziali,
perché queste si sovrappongono (Panchine, Piatti doccia e Pozzi sarebbero tutti P).

Nel CSV la categoria viene scritta come `Categoria > Sottocategoria, Categoria`,
così il prodotto risulta assegnato sia alla sottocategoria che alla principale.

## SKU

Lo SKU viene generato automaticamente e descrive il prodotto:

```
E   LR   080   0001
│   │    │     └─ progressivo nel gruppo, 4 cifre
│   │    └─ dimensione maggiore in cm, 3 cifre
│   └─ codice sottocategoria (XX se assente)
└─ codice categoria
```

Il progressivo riparte da 0001 per ogni combinazione categoria/sottocategoria/
dimensione: due lavelli rustici da esterno di 80 cm sono `ELR0800001` e
`ELR0800002`, mentre uno da 120 cm è `ELR1200001`.

Lo SKU si vede aggiornarsi in tempo reale mentre si scelgono categoria e
dimensioni, e viene assegnato al salvataggio. **Da quel momento non va più
cambiato**: per WooCommerce uno SKU diverso significa un prodotto diverso, quindi
modificarlo creerebbe un doppione invece di aggiornare quello online. Per questo
ricategorizzare un prodotto non ne cambia lo SKU.

Se serve uno SKU particolare, la casella *Scrivi lo SKU manualmente* sblocca il
campo in fase di creazione.

## Controlli prima dell'export

Bloccanti: SKU mancante o duplicato, nome mancante, link affiliato mancante o
malformato, prezzo mancante o non numerico, categoria sconosciuta, URL immagine
malformato.

Avvisi: nessuna immagine, breve descrizione mancante, prezzo in offerta maggiore
del listino. Il pulsante *Controlla anche le immagini online* verifica che ogni
URL immagine risponda davvero (richiede qualche secondo).

## Struttura

```
app/
  main.py        interfaccia (le tre pagine)
  schema.py      le 41 colonne, i valori fissi, i campi del form
  categories.py  lettura di categories.txt (nomi + codici)
  sku.py         generazione degli SKU
  rules.py       tag predefiniti per categoria, gruppi di immagini
  storage.py     lettura/scrittura di data/products.csv
  export.py      validazione e generazione del file WooCommerce
```

I valori uguali per tutti i prodotti (`Tipo=external`, `Pubblicato=1`,
`Stato delle imposte=taxable`, …) stanno in `DEFAULTS` dentro `app/schema.py`:
non compaiono nel form e vengono riscritti a ogni export.
