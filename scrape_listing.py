#!/usr/bin/env python3
"""
scrape_listing.py — Descarga TODA la informacion de un anuncio inmobiliario
(fotos + datos) y la guarda en la estructura estandar de la skill.

Portales soportados con extraccion especifica: Idealista.
Resto de portales (Fotocasa, Habitaclia, Pisos.com, etc.): extraccion generica
via Open Graph + JSON-LD + heuristicas de imagenes.

Que genera dentro de --output (la carpeta del inmueble):
    photos/                01.jpg, 02.jpg, ...  + _index.md
    fuentes/               <YYYYMMDD>_Anuncio_<RefID>.html   (HTML en bruto)
                           <YYYYMMDD>_Anuncio_<RefID>.json   (datos estructurados)
    md_files/              <YYYYMMDD>_Anuncio_<Portal>_<RefID>.md  (transcripcion legible)

El prefijo de fecha usado es la fecha de captura (hoy), salvo --fecha.

------------------------------------------------------------------------------
ANTI-BOT (IMPORTANTE):
Idealista, Fotocasa y otros usan DataDome / captchas. Una peticion HTTP plana
(requests) casi siempre recibe 403. Por eso el motor por defecto es Playwright
(navegador real). La primera vez:

    pip install playwright --break-system-packages
    playwright install chromium

y, si salta captcha, ejecuta en modo visible y resuelvelo a mano una vez:

    python scrape_listing.py --url <URL> --output <carpeta> --headed \\
        --user-data-dir ~/.cache/idealista_profile

El --user-data-dir guarda las cookies para que las siguientes ejecuciones no
vuelvan a pedir captcha.
------------------------------------------------------------------------------

Uso basico:
    python scrape_listing.py \\
        --url "https://www.idealista.com/inmueble/110912235/" \\
        --output "/ruta/Inmuebles/20260520_Idealista_110912235_Mislata_CardenalBenlloch"

Si no pasas --output, se crea una carpeta con el patron estandar dentro de --base
(o del directorio por defecto de Inmuebles).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, urljoin

# requests/bs4 se importan de forma perezosa para que el script arranque aun sin ellos.

log = logging.getLogger("scrape_listing")

# Default output base — Google Drive Inmuebles folder (macOS)
DEFAULT_BASE = (
    Path.home()
    / "Library/CloudStorage/GoogleDrive-rjaumecatany@gmail.com"
    / "My Drive/my_folder/01_Family/Mortgage/Inmuebles"
)

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
HTTP_HEADERS = {
    "User-Agent": DEFAULT_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.6",
    "Referer": "https://www.google.com/",
}
IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".avif")


# --------------------------------------------------------------------------- #
# Deteccion de portal + ref del anuncio
# --------------------------------------------------------------------------- #
def detect_portal_and_ref(url: str) -> tuple[str, str]:
    host = urlparse(url).netloc.lower()
    path = urlparse(url).path
    portal = "Desconocido"
    ref = ""
    if "idealista" in host:
        portal = "Idealista"
        m = re.search(r"/inmueble/(\d+)", path)
        ref = m.group(1) if m else ""
    elif "fotocasa" in host:
        portal = "Fotocasa"
        m = re.search(r"(\d{6,})", path)
        ref = m.group(1) if m else ""
    elif "habitaclia" in host:
        portal = "Habitaclia"
        m = re.search(r"(\d{6,})", path)
        ref = m.group(1) if m else ""
    elif "pisos.com" in host:
        portal = "Pisos"
        m = re.search(r"(\d{6,})", path)
        ref = m.group(1) if m else ""
    else:
        m = re.search(r"(\d{6,})", path)
        ref = m.group(1) if m else ""
    if not ref:
        ref = "sinref"
    return portal, ref


# --------------------------------------------------------------------------- #
# Descarga del HTML: Playwright (preferido) o requests (fallback)
# --------------------------------------------------------------------------- #
def _page_has_captcha(page) -> bool:
    """Detect DataDome / captcha-delivery blocking pages."""
    try:
        content = page.content()
        return ("captcha-delivery.com" in content
                or "datadome" in content.lower()
                or "geo.captcha-delivery.com" in content)
    except Exception:
        return False


def _wait_for_captcha_resolution(page, max_wait: int = 120) -> None:
    """Poll until captcha disappears or timeout. User solves it in the headed browser."""
    print("\n*** CAPTCHA DETECTADO ***")
    print(f"Resuelve el captcha en la ventana del navegador (tienes {max_wait}s)...")
    start = time.time()
    while time.time() - start < max_wait:
        if not _page_has_captcha(page):
            print("Captcha resuelto — continuando.\n")
            return
        time.sleep(2)
    print("Timeout esperando captcha — continuando con lo que haya.\n", file=sys.stderr)


def fetch_with_playwright(url: str, headed: bool, user_data_dir: str | None,
                          wait: float, timeout: int) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "Playwright no instalado. Instala con:\n"
            "    pip install playwright --break-system-packages && playwright install chromium\n"
            "O usa --engine requests (probablemente bloqueado en Idealista)."
        )

    with sync_playwright() as p:
        launch_kwargs = dict(headless=not headed, args=["--disable-blink-features=AutomationControlled"])
        if user_data_dir:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir, locale="es-ES", user_agent=DEFAULT_UA, **launch_kwargs
            )
            page = ctx.new_page()
        else:
            browser = p.chromium.launch(**launch_kwargs)
            ctx = browser.new_context(locale="es-ES", user_agent=DEFAULT_UA)
            page = ctx.new_page()

        page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
        time.sleep(wait)

        # Detect and wait for captcha resolution (headed mode)
        if _page_has_captcha(page):
            if headed:
                _wait_for_captcha_resolution(page, max_wait=120)
            else:
                print(
                    "\nCAPTCHA detectado en modo headless. Reintenta con:\n"
                    "  --headed --user-data-dir ~/.cache/idealista_profile\n",
                    file=sys.stderr,
                )

        # auto-scroll para forzar lazy-load de fotos
        try:
            for _ in range(12):
                page.mouse.wheel(0, 2200)
                time.sleep(0.4)
            page.mouse.wheel(0, -100000)
        except Exception as e:
            log.warning("Error during auto-scroll: %s", e)
        time.sleep(1.0)
        html = page.content()
        try:
            ctx.close()
        except Exception:
            pass
        return html


def fetch_with_requests(url: str, timeout: int) -> str:
    import requests  # lazy
    sess = requests.Session()
    sess.headers.update(HTTP_HEADERS)
    r = sess.get(url, timeout=timeout)
    if r.status_code == 403 or "datadome" in r.text.lower() or "captcha" in r.text.lower():
        raise RuntimeError(
            f"Bloqueado por anti-bot (HTTP {r.status_code}). Reintenta con el motor "
            "Playwright en modo visible:  --engine playwright --headed --user-data-dir <dir>"
        )
    r.raise_for_status()
    return r.text


# --------------------------------------------------------------------------- #
# Extraccion de imagenes
# --------------------------------------------------------------------------- #
def _normalize_idealista_size(u: str) -> str:
    # Sube a la mayor resolucion conocida cuando aparece el token de tamano.
    return re.sub(r"/(WEB_DETAIL[A-Z\-]*)/", "/WEB_DETAIL-XL-L/", u)


def extract_image_urls(html: str, base_url: str, portal: str) -> list[str]:
    urls: list[str] = []

    # 1) URLs de CDN de Idealista directamente en el HTML/JS
    if portal == "Idealista":
        for m in re.findall(r"https://img\d+\.idealista\.com/[^\s\"'\\<>]+", html):
            if m.lower().split("?")[0].endswith(IMG_EXTS):
                urls.append(_normalize_idealista_size(m))

    # 2) Open Graph + atributos de imagen via BeautifulSoup (si esta disponible)
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for og in soup.find_all("meta", attrs={"property": "og:image"}):
            c = og.get("content")
            if c:
                urls.append(c)
        for tag in soup.find_all(["img", "source"]):
            for attr in ("src", "data-src", "data-ondemand-img", "data-service", "srcset"):
                v = tag.get(attr)
                if not v:
                    continue
                cand = v.split()[0] if attr == "srcset" else v
                if cand.lower().split("?")[0].endswith(IMG_EXTS):
                    urls.append(urljoin(base_url, cand))
        # JSON-LD (image puede ser lista o string)
        for sc in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                data = json.loads(sc.string or "{}")
            except Exception:
                continue
            for block in (data if isinstance(data, list) else [data]):
                img = block.get("image") if isinstance(block, dict) else None
                if isinstance(img, str):
                    urls.append(img)
                elif isinstance(img, list):
                    urls.extend([x for x in img if isinstance(x, str)])
    except ImportError:
        # sin bs4: heuristica generica por regex
        for m in re.findall(r"https?://[^\s\"'\\<>]+?\.(?:jpg|jpeg|png|webp)", html):
            urls.append(m)

    # Dedupe: collapse size variants AND format variants (jpg/webp) of the same
    # image into a single entry. For Idealista, the unique image identifier is the
    # numeric ID at the end of the path (e.g. 1439083087). We prefer JPG over WebP.
    if portal == "Idealista":
        # Filter to CDN images only and normalize size tokens
        urls = [_normalize_idealista_size(u) for u in urls
                if "img" in urlparse(u).netloc]
        # Group by image ID (last numeric path segment before extension)
        best: dict[str, str] = {}  # image_id -> preferred URL
        for u in urls:
            m = re.search(r"/(\d{7,})\.\w+", u.split("?")[0])
            if not m:
                continue
            img_id = m.group(1)
            if img_id not in best:
                best[img_id] = u
            elif u.split("?")[0].lower().endswith(".jpg") and best[img_id].split("?")[0].lower().endswith(".webp"):
                best[img_id] = u  # prefer jpg
        return list(dict.fromkeys(best.values()))  # preserve insertion order

    # Generic portal: dedupe by full URL path (no format collapsing)
    seen, out = set(), []
    for u in urls:
        key = u.split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(u)
    return out


# --------------------------------------------------------------------------- #
# Extraccion de datos del anuncio
# --------------------------------------------------------------------------- #
def text_or_none(node) -> str | None:
    if node is None:
        return None
    t = node.get_text(" ", strip=True)
    return t or None


def extract_listing_data(html: str, url: str, portal: str, ref: str) -> dict:
    data: dict = {"url": url, "portal": portal, "ref_anuncio": ref}
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
    except ImportError:
        # sin bs4: solo og: tags por regex
        def og(p):
            m = re.search(rf'<meta[^>]+property=["\']og:{p}["\'][^>]+content=["\']([^"\']+)', html)
            return m.group(1) if m else None
        data.update({"titulo": og("title"), "descripcion": og("description")})
        return data

    def og(p):
        n = soup.find("meta", attrs={"property": f"og:{p}"})
        return n.get("content") if n else None

    data["titulo"] = (text_or_none(soup.find("h1")) or og("title"))
    data["descripcion_og"] = og("description")

    if portal == "Idealista":
        data["precio_publicado"] = text_or_none(soup.select_one(".info-data-price")) or \
                                   text_or_none(soup.select_one("[class*='price']"))
        data["ubicacion"] = text_or_none(soup.select_one(".main-info__title-minor"))
        feats = [text_or_none(li) for li in soup.select(".info-features span, .details-property-feature-one li")]
        data["caracteristicas"] = [f for f in feats if f]
        # .comment is the actual description div; avoid [class*='comment'] which
        # matches the "Añadir tu nota" UI widget that appears earlier in the DOM.
        desc_node = (
            soup.select_one(".commentsContainer .comment")
            or soup.select_one("div.comment")
            or soup.select_one(".adCommentsLanguage p")
        )
        data["descripcion"] = text_or_none(desc_node)
        # bloque "Caracteristicas basicas"
        basic = [text_or_none(li) for li in soup.select(".details-property_features li")]
        data["caracteristicas_basicas"] = [b for b in basic if b]
        # utag_data embebido
        m = re.search(r"utag_data\s*=\s*(\{.*?\});", html, re.DOTALL)
        if m:
            try:
                data["utag_data"] = json.loads(m.group(1))
            except Exception:
                pass

    # JSON-LD generico (vale para casi todos los portales)
    for sc in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            block = json.loads(sc.string or "{}")
        except Exception:
            continue
        for b in (block if isinstance(block, list) else [block]):
            if isinstance(b, dict) and b.get("@type") in ("Product", "Residence", "Apartment", "House", "Offer", "RealEstateListing"):
                data.setdefault("json_ld", b)

    if not data.get("descripcion"):
        data["descripcion"] = data.get("descripcion_og")
    return data


# --------------------------------------------------------------------------- #
# Descarga de fotos
# --------------------------------------------------------------------------- #
def download_photos(urls: list[str], photos_dir: Path, delay: float, max_photos: int) -> int:
    import requests  # lazy
    photos_dir.mkdir(parents=True, exist_ok=True)
    sess = requests.Session()
    sess.headers.update(HTTP_HEADERS)
    index = ["# Photos index", ""]
    saved = 0
    for i, u in enumerate(urls[:max_photos], start=1):
        ext = next((e for e in IMG_EXTS if u.split("?")[0].lower().endswith(e)), ".jpg")
        target = photos_dir / f"{i:02d}{ext}"
        ok = False
        try:
            r = sess.get(u, timeout=25)
            # Validate response is actually an image
            content_type = r.headers.get("Content-Type", "")
            if r.ok and r.content and ("image/" in content_type or content_type == ""):
                target.write_bytes(r.content)
                ok = True
                saved += 1
            elif r.ok:
                log.warning("Skipping %s: unexpected Content-Type %s", u, content_type)
        except Exception as e:
            log.warning("FALLO %s: %s", u, e)
        index.append(f"- `{target.name}` — {u}  ({'OK' if ok else 'FALLO'})")
        print(f"[{i:02d}] {'OK ' if ok else 'XX '} {target.name}  <-  {u}")
        if delay:
            time.sleep(delay)
    (photos_dir / "_index.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    return saved


# --------------------------------------------------------------------------- #
# Salida markdown (transcripcion legible / token-cheap)
# --------------------------------------------------------------------------- #
def build_markdown(data: dict, n_photos: int, fecha: str) -> str:
    L = [f"# Anuncio {data.get('portal','')} {data.get('ref_anuncio','')} — captura {fecha}", ""]
    L.append(f"**URL:** {data.get('url','')}")
    if data.get("titulo"):
        L.append(f"**Titulo:** {data['titulo']}")
    if data.get("ubicacion"):
        L.append(f"**Ubicacion:** {data['ubicacion']}")
    if data.get("precio_publicado"):
        L.append(f"**Precio publicado:** {data['precio_publicado']}")
    L.append(f"**Fotos descargadas:** {n_photos}")
    L.append("")
    if data.get("caracteristicas_basicas"):
        L += ["## Caracteristicas basicas", ""] + [f"- {c}" for c in data["caracteristicas_basicas"]] + [""]
    if data.get("caracteristicas"):
        L += ["## Caracteristicas", ""] + [f"- {c}" for c in data["caracteristicas"]] + [""]
    if data.get("descripcion"):
        L += ["## Descripcion", "", data["descripcion"], ""]
    L += ["---", "", "_Transcripcion generada por scrape_listing.py. El HTML/JSON en bruto esta en `../fuentes/`._"]
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Scraper de anuncios inmobiliarios (fotos + datos).")
    ap.add_argument("--url", required=True, help="URL del anuncio.")
    ap.add_argument("--output", help="Carpeta del inmueble (se crea si no existe).")
    ap.add_argument("--base", default=str(DEFAULT_BASE),
                    help="Si no das --output, carpeta base donde crear la del inmueble.")
    ap.add_argument("--municipio", default="Municipio", help="Para el nombre de carpeta auto.")
    ap.add_argument("--zona", default="Zona", help="Para el nombre de carpeta auto (CamelCase).")
    ap.add_argument("--engine", choices=["playwright", "requests"], default="playwright")
    ap.add_argument("--headed", action="store_true", help="Playwright en modo visible (para resolver captcha).")
    ap.add_argument("--user-data-dir", help="Perfil persistente de Chromium (guarda cookies anti-captcha).")
    ap.add_argument("--max-photos", type=int, default=60)
    ap.add_argument("--delay", type=float, default=0.4, help="Segundos entre descargas de fotos.")
    ap.add_argument("--wait", type=float, default=3.0, help="Segundos de espera tras cargar (Playwright).")
    ap.add_argument("--timeout", type=int, default=45)
    ap.add_argument("--fecha", help="Prefijo YYYYMMDD a usar (por defecto: hoy).")
    ap.add_argument("-v", "--verbose", action="store_true", help="Activar logs detallados.")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    portal, ref = detect_portal_and_ref(args.url)
    fecha = args.fecha or _dt.date.today().strftime("%Y%m%d")

    if args.output:
        out = Path(args.output)
    else:
        folder = f"{fecha}_{portal}_{ref}_{args.municipio}_{args.zona}"
        out = Path(args.base) / folder
    (out / "fuentes").mkdir(parents=True, exist_ok=True)
    (out / "md_files").mkdir(parents=True, exist_ok=True)
    (out / "photos").mkdir(parents=True, exist_ok=True)

    print(f"Portal={portal}  Ref={ref}  ->  {out}")

    # 1) HTML
    try:
        if args.engine == "playwright":
            html = fetch_with_playwright(args.url, args.headed, args.user_data_dir, args.wait, args.timeout)
        else:
            html = fetch_with_requests(args.url, args.timeout)
    except Exception as e:
        print(f"\nERROR al descargar la pagina: {e}", file=sys.stderr)
        return 2

    html_path = out / "fuentes" / f"{fecha}_Anuncio_{ref}.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"HTML guardado: {html_path}")

    # 2) Datos
    data = extract_listing_data(html, args.url, portal, ref)
    data["fecha_captura"] = fecha
    json_path = out / "fuentes" / f"{fecha}_Anuncio_{ref}.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Datos guardados: {json_path}")

    # 3) Fotos
    imgs = extract_image_urls(html, args.url, portal)
    print(f"Imagenes detectadas: {len(imgs)}")
    n_photos = download_photos(imgs, out / "photos", args.delay, args.max_photos) if imgs else 0

    # 4) Markdown legible
    md_path = out / "md_files" / f"{fecha}_Anuncio_{portal}_{ref}.md"
    md_path.write_text(build_markdown(data, n_photos, fecha), encoding="utf-8")
    print(f"Markdown guardado: {md_path}")

    print(f"\nLISTO. Fotos: {n_photos}  | Carpeta: {out}")
    if n_photos == 0:
        print("Aviso: 0 fotos. Probable anti-bot. Reintenta: --engine playwright --headed --user-data-dir <dir>",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
