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

## Usage

### Basic (Playwright, headless)

```bash
python scrape_listing.py \
    --url "https://www.idealista.com/inmueble/110912235/" \
    --municipio Mislata --zona CardenalBenlloch
```

### First run / captcha resolution (headed mode)

Idealista and other portals use DataDome anti-bot. Run headed mode once to solve the captcha, then reuse the browser profile:

```bash
python scrape_listing.py \
    --url "https://www.idealista.com/inmueble/110912235/" \
    --headed --user-data-dir ~/.cache/idealista_profile \
    --municipio Mislata --zona CardenalBenlloch
```

### Explicit output folder

```bash
python scrape_listing.py \
    --url "https://www.idealista.com/inmueble/110912235/" \
    --output "/path/to/20260520_Idealista_110912235_Mislata_CardenalBenlloch"
```

### Fallback with requests (no browser needed, likely blocked)

```bash
python scrape_listing.py \
    --url "https://www.idealista.com/inmueble/110912235/" \
    --engine requests
```

## CLI options

| Flag | Default | Description |
|------|---------|-------------|
| `--url` | *required* | Listing URL |
| `--output` | auto-generated | Target folder (overrides `--base`) |
| `--base` | `~/...Inmuebles` | Parent folder for auto-generated output |
| `--municipio` | `Municipio` | Municipality name for folder naming |
| `--zona` | `Zona` | Zone/street in CamelCase for folder naming |
| `--engine` | `playwright` | `playwright` or `requests` |
| `--headed` | off | Show browser window (for captcha) |
| `--user-data-dir` | none | Persistent Chromium profile path |
| `--max-photos` | 60 | Max photos to download |
| `--delay` | 0.4 | Seconds between photo downloads |
| `--wait` | 3.0 | Seconds to wait after page load |
| `--timeout` | 45 | Page load timeout (seconds) |
| `--fecha` | today | Date prefix override (YYYYMMDD) |
| `-v` | off | Verbose logging |

## Supported portals

| Portal | Extraction level |
|--------|-----------------|
| Idealista | Full (price, features, description, max-res photos) |
| Fotocasa | Generic (OG tags + JSON-LD + image heuristics) |
| Habitaclia | Generic |
| Pisos.com | Generic |
| Others | Generic (any portal with standard meta tags) |

## License

MIT
