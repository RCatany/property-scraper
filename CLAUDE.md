# CLAUDE.md

## Project Overview

**property-scraper** is a CLI tool that downloads photos, structured data, and markdown transcriptions from Spanish real estate listing URLs. It supports Idealista, Fotocasa, and Habitaclia with portal-specific extraction, plus generic extraction for any other portal.

**Repo:** https://github.com/RCatany/property-scraper
**Owner:** Rafael Catany (RCatany)

## Architecture

Single-file script (`scrape_listing.py`) with these stages:

1. **Portal detection** (`detect_portal_and_ref`) — identifies portal and extracts listing ref from URL
2. **HTML fetch** (`fetch_with_playwright` / `fetch_with_requests`) — Playwright preferred, with captcha detection and interactive wait
3. **Image extraction** (`extract_image_urls`) — portal-specific dedup, resolution upgrade, and filtering
4. **Data extraction** (`extract_listing_data`) — portal-specific CSS selectors for price, features, description
5. **Photo download** (`download_photos`) — sequential with content-type validation
6. **Markdown output** (`build_markdown`) — human-readable transcription for AI consumption

## Portal-Specific Extraction

Each portal has its own block in `extract_listing_data` and `extract_image_urls`:

| Portal | Data selectors | Image strategy |
|--------|---------------|----------------|
| **Idealista** | `.info-data-price`, `.main-info__title-minor`, `.details-property_features li`, `.commentsContainer .comment` | CDN regex, normalize to `WEB_DETAIL-XL-L`, dedup by numeric image ID, prefer JPG over WebP |
| **Fotocasa** | `.re-DetailHeader-price`, `li.re-DetailHeader-featuresItem`, `li.re-DetailExtras-listItem`, `.re-DetailDescription` | Filter to `/images/anuncio/` CDN, upgrade to `?rule=original`, dedup by image ID |
| **Habitaclia** | `[itemprop=price]`, `h4.address`, `ul.feature-container li.feature`, `.detail-description`, `.energy-container` | Filter by listing habimg ref (from `.gallery img`), dedup by UUID, upgrade to XL suffix |

## Output Structure

```
YYYYMMDD_Portal_RefID_Municipio_Zona/
  photos/       01.jpg, 02.jpg, ... + _index.md
  fuentes/      YYYYMMDD_Anuncio_RefID.html + .json
  md_files/     YYYYMMDD_Anuncio_Portal_RefID.md
```

Default output base: `~/Library/CloudStorage/GoogleDrive-.../Mortgage/Inmuebles/`
Naming conventions: see `Inmuebles/_CONVENCIONES_CARPETAS.md` in the Mortgage project.

## Running

```bash
# Shell alias (defined in ~/.zshrc):
scrape-listing --url <URL> --headed --user-data-dir ~/.cache/<portal>_profile

# Or directly:
python3 scrape_listing.py --url <URL>
```

Municipio and zona are derived automatically by `derive_location` from the URL + scraped data; pass `--output <path>` to override the destination entirely.

## Dependencies

- `playwright` (+ `playwright install chromium`) — browser automation
- `beautifulsoup4` — HTML parsing
- `requests` — photo downloads

All listed in `requirements.txt`.

## Anti-Bot / Captcha Handling

Idealista and Fotocasa use DataDome. The script:
1. Detects captcha pages by checking for `captcha-delivery.com` in the HTML
2. In `--headed` mode, waits up to 2 minutes polling every 2s for resolution
3. In headless mode, prints an error suggesting `--headed`
4. `--user-data-dir` persists cookies so captchas are skipped on subsequent runs

Use a separate profile per portal: `~/.cache/idealista_profile`, `~/.cache/fotocasa_profile`, etc.

## Adding a New Portal

1. Add detection in `detect_portal_and_ref` (hostname check + ref regex)
2. Add an `elif portal == "NewPortal":` block in `extract_listing_data` with CSS selectors for price, features, description
3. Add a portal block in `extract_image_urls` for CDN filtering, resolution upgrade, and dedup
4. Test with a real listing, inspect the saved HTML in `fuentes/` to find selectors
5. Update README.md supported portals table

## Coding Conventions

- Spanish comments and user-facing output (CLI messages, markdown)
- Lazy imports for `requests`, `bs4`, `playwright` so the script starts even if a dep is missing
- `pathlib.Path` for all file operations
- `logging` module for warnings (`-v` for debug), `print` for progress output
