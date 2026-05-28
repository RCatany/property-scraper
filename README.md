# property-scraper

Scraper for Spanish real estate listing portals (Idealista, Fotocasa, Habitaclia, Pisos.com, etc.). Given a listing URL, downloads all photos, structured data, and generates a human-readable markdown transcription.

## What it does

For each listing, the script creates:

```
YYYYMMDD_Portal_RefID_Municipio_Zona/
├── photos/          01.jpg, 02.jpg, ... + _index.md
├── fuentes/         YYYYMMDD_Anuncio_RefID.html  (raw HTML)
│                    YYYYMMDD_Anuncio_RefID.json  (structured data)
└── md_files/        YYYYMMDD_Anuncio_Portal_RefID.md  (readable transcription)
```

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

A shell alias is configured in `~/.zshrc` so the command works from any directory:

```bash
alias scrape-listing="python3 ~/GitHub/property-scraper/scrape_listing.py"
```

## Usage

The folder name is derived automatically from the URL and the scraped page content (see [Auto-derived folder name](#auto-derived-folder-name) below). Pass `--output` to override the destination completely.

### Basic (Playwright, headless)

```bash
scrape-listing --url "https://www.idealista.com/inmueble/110912235/"
```

### First run / captcha resolution (headed mode)

Idealista and other portals use DataDome anti-bot. Run headed mode once to solve the captcha, then reuse the browser profile. The script detects captchas automatically and waits up to 2 minutes for you to solve it in the browser window:

```bash
scrape-listing \
    --url "https://www.idealista.com/inmueble/110912235/" \
    --headed --user-data-dir ~/.cache/idealista_profile
```

### Explicit output folder

```bash
scrape-listing \
    --url "https://www.idealista.com/inmueble/110912235/" \
    --output "/path/to/20260520_Idealista_110912235_Mislata_CardenalBenlloch"
```

### Fallback with requests (no browser needed, likely blocked)

```bash
scrape-listing \
    --url "https://www.idealista.com/inmueble/110912235/" \
    --engine requests
```

## Worked examples (real listings)

Each command below has been used successfully against the production portals. Use a separate `--user-data-dir` per portal so the cookies from a solved captcha persist independently.

### Idealista

```bash
scrape-listing \
    --url "https://www.idealista.com/inmueble/111517532/" \
    --headed --user-data-dir ~/.cache/idealista_profile
```

Produces `20260521_Idealista_111517532_Mislata_LaConstitucionCanaleta/` with all photos, JSON metadata and a markdown transcription. The municipio + zona are derived from the listing's `ubicacion` field.

### Fotocasa

```bash
scrape-listing \
    --url "https://www.fotocasa.es/es/comprar/vivienda/mislata/aire-acondicionado/188796409/d" \
    --headed --user-data-dir ~/.cache/fotocasa_profile
```

Folder: `20260521_Fotocasa_188796409_Mislata_Pizarro/` — municipio from the URL slug, zona from the street name in the page header.

### Habitaclia

```bash
scrape-listing \
    --url "https://www.habitaclia.com/comprar-piso-tu_nuevo_hogar_te_espera_cardenal_benlloch-mislata-i8346004366125.htm" \
    --headed --user-data-dir ~/.cache/habitaclia_profile
```

Folder: `20260521_Habitaclia_8346004366125_Mislata_CardenalBenlloch/` — municipio from the URL slug, zona from the `h4.address` field.

> Tip: the first run on each portal will open a Chromium window if a DataDome captcha is triggered. Solve it once; subsequent runs reuse the profile and skip it.

## CLI options

| Flag | Default | Description |
|------|---------|-------------|
| `--url` | *required* | Listing URL |
| `--output` | auto-generated | Target folder (overrides `--base` and auto-derivation) |
| `--base` | `~/...Inmuebles` | Parent folder for auto-generated output |
| `--engine` | `playwright` | `playwright` or `requests` |
| `--headed` | off | Show browser window (for captcha) |
| `--user-data-dir` | none | Persistent Chromium profile path |
| `--max-photos` | 60 | Max photos to download |
| `--delay` | 0.4 | Seconds between photo downloads |
| `--wait` | 3.0 | Seconds to wait after page load |
| `--timeout` | 45 | Page load timeout (seconds) |
| `--fecha` | today | Date prefix override (YYYYMMDD) |
| `-v` | off | Verbose logging |

## Auto-derived folder name

When `--output` is not given, the folder is named `{YYYYMMDD}_{Portal}_{Ref}_{Municipio}_{Zona}`. Municipio and zona are extracted automatically:

| Portal | Municipio source | Zona source |
|--------|------------------|-------------|
| Idealista | Last segment of `ubicacion` (e.g. `…, Mislata` → `Mislata`) | First segments of `ubicacion`, CamelCased |
| Fotocasa | Token after `/vivienda/` in the URL path | Last meaningful word of the street in the page header |
| Habitaclia | Last hyphen-separated slug before `-i<ref>.htm` | `h4.address` value, CamelCased |
| Other | `Unknown` | `Unknown` |

If a field is missing (e.g. the page was a captcha and `ubicacion` is empty), the corresponding slot falls back to `Unknown`. Pass `--output` to override the entire path manually.

## Listing-status monitor (`check_listing_status.py`)

Companion script that watches every URL in a shortlist Excel (`Inmuebles_SHORTLIST.xlsx`, sheet `Inmuebles`) and writes the portal status back to the workbook in-place. Use it before any negotiation move to catch withdrawn, sold, reserved or reduced-price listings without manually clicking each link.

### What it does, per row

1. Visits the URL with Playwright (persistent profile per portal — captcha solved once).
2. Detects status from page banners: `Activo`, `Retirado`, `Caducado`, `Vendido`, `Reservado`, `Desconocido`.
3. Compares the live price to `Precio publicado` (col 12). If different, annotates the status with the delta and updates the cell.
4. Fills empty `Municipio` / `Barrio` / `m2 anuncio` cells from the scraped data (never overwrites existing values).
5. Refreshes `Ultima actualizacion` (col 4) to today.
6. Writes the result to a new column `Estado anuncio` (col 41).

Rows whose `Estado proceso` starts with `DESCARTADO` are skipped by default.

### Usage

```bash
# Dry run on every row (no Excel writes)
/opt/anaconda3/bin/python check_listing_status.py --dry-run -v

# Real run on the default Excel
/opt/anaconda3/bin/python check_listing_status.py

# Only a subset
/opt/anaconda3/bin/python check_listing_status.py --only-ids P001,P005

# Include discarded listings
/opt/anaconda3/bin/python check_listing_status.py --include-discarded
```

CLI options:

| Flag | Default | Description |
|------|---------|-------------|
| `--xlsx` | shortlist in Google Drive | Path to the workbook |
| `--only-ids` | all rows | Comma-separated subset, e.g. `P001,P005` |
| `--include-discarded` | off | Process rows with `Estado proceso` starting with `DESCARTADO` |
| `--dry-run` | off | Print actions, do not save |
| `--headed` / `--headless` | headed | Browser visibility (headed required for captchas) |
| `-v` | off | Verbose logging |

> The script reuses `scrape_listing.py` as a module — same captcha handling, same per-portal extraction. Output is non-destructive: formulas, conditional formatting, and the existing 40 columns are preserved.

## Supported portals

| Portal | Extraction level | Details |
|--------|-----------------|---------|
| Idealista | Full | Price, location, features, full description, max-res photos (JPG/WebP dedup by image ID) |
| Fotocasa | Full | Price, features, extras, full description, original-resolution photos (logo filtering, dedup by image ID) |
| Habitaclia | Full | Price, location, features, full description, energy cert, XL-res photos (gallery filtering, UUID dedup) |
| Pisos.com | Generic | OG tags + JSON-LD + image heuristics |
| Others | Generic | Any portal with standard meta tags |

## License

MIT
