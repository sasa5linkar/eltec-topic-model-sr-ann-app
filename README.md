# ELTeC Topic Annotation Streamlit App (MVP)

MVP aplikacija za ručnu anotaciju tema nad segmentima romana, sa backendom na postojećoj Supabase bazi.

## Šta aplikacija radi

Aplikacija ima dve role:

- **Admin**
  - upload ELTeC/TEI XML romana
  - parsiranje metapodataka (naslov, autor, godina ako postoji)
  - segmentacija (po poglavljima ili fallback po broju reči)
  - upravljanje temama
  - dodela segmenata annotatorima
  - praćenje statusa dodela
  - export anotiranih podataka u ZIP (`metadata.tsv` + `texts/*.txt`)

- **Annotator**
  - pregled ličnih dodela
  - otvaranje segmenta
  - izbor jedne ili više tema
  - opcionalna beleška
  - čuvanje anotacije
  - označavanje dodele kao completed

## Struktura projekta

```text
app/
  streamlit_app.py
  pages/
    1_Admin.py
    2_Annotator.py
src/
  auth.py
  db.py
  eltec_parser.py
  segmentation.py
  export_utils.py
  models.py
.streamlit/
  secrets.toml.example
requirements.txt
README.md
.gitignore
```

## Instalacija

Preporuka: Python 3.11+

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Konfiguracija (`secrets.toml`)

Kreiraj fajl `.streamlit/secrets.toml` (lokalno, ne commit-ovati):

```toml
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_ANON_KEY = "your-anon-key"
SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"
```

U repou već postoji primer: `.streamlit/secrets.toml.example`.

## Pokretanje lokalno

Pokreni iz root foldera:

```bash
streamlit run app/streamlit_app.py
```

## Development user režim

MVP koristi jednostavan development auth sloj:

- korisnik se bira u sidebar-u iz `profiles` tabele
- opcionalno može query param `?user_id=<uuid>`
- arhitektura je pripremljena za kasniji prelazak na pravi Supabase auth/session flow

## Glavni moduli

- `src/models.py` – centralizovane konstante tabela/statusa/rola + pomoćne strukture parsera.
- `src/db.py` – sve funkcije pristupa bazi.
- `src/auth.py` – aktivni korisnik i dev mode logika.
- `src/eltec_parser.py` – robustnije parsiranje TEI XML sadržaja.
- `src/segmentation.py` – segmentacija po poglavljima ili po broju reči.
- `src/export_utils.py` – generisanje ZIP izvoza.

## Kako radi eksport

Admin stranica generiše ZIP sa strukturom:

```text
export/
  metadata.tsv
  texts/
    <document_id>_<segment_order>.txt
```

`metadata.tsv` sadrži tražene kolone:
- document_id
- title
- author
- publication_year
- segment_id
- segment_order
- segment_label
- relative_text_path
- annotator_id
- annotator_email
- status
- themes
- note

## Napomene za sledeću fazu

- Dodati pravi Supabase auth/session tok (umesto dev selector-a) kada bude potrebno.
- Dodati finije validacije i granularniji handling specifičnih razlika u šemi.
- Po potrebi dodati migrations/seed helper skripte za test okruženje.
