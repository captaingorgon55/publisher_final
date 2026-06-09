"""
app.py - EE Publisher
App que extrae contenido de URLs de El Espectador y genera la tarjeta
estilo plantilla automaticamente.

Incluye 2 pestanas:
- Tarjetas de noticias (flujo original)
- Resultados Elecciones 2026 (hasta 5 candidatos)

REDISEÑO UX v2:
  - Selector de plantillas como grid visual con iconos
  - Opciones avanzadas colapsadas en expander
  - Hootsuite e IA al final, solo cuando hay tarjeta generada
"""
from scraper_registraduria import get_candidatos_resultados, get_candidatos_manual, get_resultados_territoriales
from map_generator_sv import render_carrusel_segunda_vuelta as render_carrusel_electoral, carrusel_a_zip
import ai_helper
import hootsuite_helper
from datetime import datetime, timedelta
import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from io import BytesIO
from PIL import Image

from generator import (
    generate_card_from_image,
    fetch_image,
    FORMATS,
    TEMPLATES,
    list_fondos,
    suggest_fondo_for_section,
    list_section_logos,
    find_section_logo,
    list_logo_variants,
    render_resultados_candidatos,
    BAR_COLORS,
    list_candidatos,
    load_candidato_image,
)

st.set_page_config(
    page_title="EE Publisher",
    page_icon=":newspaper:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ============================================================
# Configuracion de Gemini (IA)
# ============================================================
import os as _os_env

def _get_gemini_key():
    try:
        return st.secrets.get("GEMINI_API_KEY", None)
    except Exception:
        pass
    return _os_env.environ.get("GEMINI_API_KEY", None)

GEMINI_KEY = _get_gemini_key()
AI_ENABLED = bool(GEMINI_KEY) and ai_helper.is_available()

# ============================================================
# Credenciales Hootsuite
# ============================================================
def _get_hootsuite_creds():
    try:
        c_id = st.secrets.get("HOOTSUITE_CLIENT_ID", "")
        c_secret = st.secrets.get("HOOTSUITE_CLIENT_SECRET", "")
        r_uri = st.secrets.get("HOOTSUITE_REDIRECT_URI", "")
    except Exception:
        c_id = c_secret = r_uri = ""
    if not c_id:
        c_id = _os_env.environ.get("HOOTSUITE_CLIENT_ID", "")
    if not c_secret:
        c_secret = _os_env.environ.get("HOOTSUITE_CLIENT_SECRET", "")
    if not r_uri:
        r_uri = _os_env.environ.get("HOOTSUITE_REDIRECT_URI", "")
    return {"client_id": c_id, "client_secret": c_secret, "redirect_uri": r_uri}

HS_CREDS = _get_hootsuite_creds()
HOOTSUITE_ENABLED = bool(
    HS_CREDS.get("client_id") and HS_CREDS.get("client_secret") and HS_CREDS.get("redirect_uri")
)

st.session_state.setdefault("hs_token", None)
st.session_state.setdefault("hs_profiles", None)
st.session_state.setdefault("hs_last_publish", None)

if HOOTSUITE_ENABLED:
    try:
        _qp = st.query_params
        _code = _qp.get("code", None)
    except Exception:
        _code = None
    if _code and st.session_state.get("hs_token") is None:
        try:
            with st.spinner("Conectando con Hootsuite..."):
                token_data = hootsuite_helper.exchange_code_for_token(
                    code=_code,
                    client_id=HS_CREDS["client_id"],
                    client_secret=HS_CREDS["client_secret"],
                    redirect_uri=HS_CREDS["redirect_uri"],
                )
                st.session_state["hs_token"] = token_data
                st.query_params.clear()
                st.success("✅ Hootsuite conectado")
                st.rerun()
        except Exception as e:
            st.error("Error conectando Hootsuite: " + str(e))

if AI_ENABLED:
    try:
        ai_helper.configure(GEMINI_KEY)
    except Exception as e:
        AI_ENABLED = False
        st.sidebar.warning("IA desactivada: " + str(e))

st.session_state.setdefault("ai_result", None)
st.session_state.setdefault("ai_title_override", None)
st.session_state.setdefault("ai_template_override", None)


# ============================================================
# ESTILOS GLOBALES
# ============================================================
st.markdown("""
<style>
:root {
    --ee-red: #E31B23;
    --ee-red-hover: #B81519;
    --ee-bg: #F5F6F8;
    --ee-card: #FFFFFF;
    --ee-text: #1A1A1A;
    --ee-text-muted: #6B7280;
    --ee-border: #E5E7EB;
}

.stApp { background: var(--ee-bg); }

.main .block-container {
    max-width: 1400px;
    padding-top: 1.5rem;
    padding-bottom: 3rem;
}

.ee-header {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 18px 24px;
    background: white;
    border-radius: 14px;
    border: 1px solid var(--ee-border);
    margin-bottom: 20px;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}
.ee-header-bar { width: 6px; height: 38px; background: var(--ee-red); border-radius: 3px; }
.ee-header-title { font-size: 1.6rem; font-weight: 700; color: var(--ee-text); margin: 0; line-height: 1; }
.ee-header-sub { font-size: 0.9rem; color: var(--ee-text-muted); margin-top: 4px; }

.stSubheader, h3 {
    color: var(--ee-text) !important;
    font-weight: 700 !important;
    border-left: 4px solid var(--ee-red);
    padding-left: 12px;
    margin-top: 1.6rem !important;
    margin-bottom: 0.8rem !important;
}

.stTextInput input, .stTextArea textarea, .stSelectbox > div > div {
    border-radius: 8px !important;
    border: 1px solid var(--ee-border) !important;
    background: white !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: var(--ee-red) !important;
    box-shadow: 0 0 0 2px rgba(227,27,35,0.12) !important;
}

.stButton > button {
    border-radius: 8px !important;
    border: 1px solid var(--ee-border);
    font-weight: 600;
    transition: all .15s ease;
}
.stButton > button[kind="primary"],
.stButton > button:first-child:hover {
    background: var(--ee-red) !important;
    color: white !important;
    border-color: var(--ee-red) !important;
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 10px rgba(0,0,0,0.08);
}

.stDownloadButton > button {
    background: var(--ee-red) !important;
    color: white !important;
    border-radius: 8px !important;
    border: none !important;
    font-weight: 600 !important;
    padding: 0.6rem 1.2rem !important;
}
.stDownloadButton > button:hover {
    background: var(--ee-red-hover) !important;
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(227,27,35,0.25);
}

.stRadio > div {
    background: white;
    padding: 12px 16px;
    border-radius: 10px;
    border: 1px solid var(--ee-border);
}
[data-testid="stFileUploader"] {
    background: white;
    border-radius: 10px;
    border: 1px dashed var(--ee-border);
    padding: 8px;
}

.streamlit-expanderHeader, [data-testid="stExpander"] summary {
    background: white !important;
    border-radius: 10px !important;
    border: 1px solid var(--ee-border) !important;
    font-weight: 600 !important;
}

.stSlider [data-baseweb="slider"] [role="slider"] {
    background-color: var(--ee-red) !important;
}

.stCaption, [data-testid="stCaptionContainer"] { color: var(--ee-text-muted) !important; }

header[data-testid="stHeader"] { background: transparent; }
footer { visibility: hidden; }

@media (min-width: 992px) {
    .main [data-testid="stHorizontalBlock"] { align-items: flex-start !important; }
    .main > div > [data-testid="stHorizontalBlock"]:first-of-type
        > [data-testid="column"]:nth-child(2),
    .main [data-testid="stHorizontalBlock"]:first-of-type
        > [data-testid="stColumn"]:nth-child(2),
    .main [data-testid="stHorizontalBlock"]:first-of-type
        > div:nth-child(2) {
        position: sticky !important;
        top: 1rem !important;
        align-self: flex-start !important;
        max-height: calc(100vh - 2rem);
        overflow-y: auto;
        overflow-x: hidden;
    }
}

.ee-preview-card {
    background: white;
    padding: 18px;
    border-radius: 14px;
    border: 1px solid var(--ee-border);
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}
.ee-preview-empty {
    background: white;
    padding: 60px 20px;
    border-radius: 14px;
    border: 1px dashed var(--ee-border);
    text-align: center;
    color: var(--ee-text-muted);
}
.ee-preview-empty-icon { font-size: 3rem; margin-bottom: 14px; opacity: 0.4; }

/* ── NUEVO: grid visual de plantillas ── */
.tpl-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
    margin-top: 6px;
}
.tpl-card {
    background: white;
    border: 1.5px solid var(--ee-border);
    border-radius: 10px;
    padding: 10px 8px;
    text-align: center;
    cursor: pointer;
    transition: all .15s ease;
}
.tpl-card:hover { border-color: var(--ee-red); transform: translateY(-1px); }
.tpl-card.active { border-color: var(--ee-red); background: #FFF5F5; }
.tpl-card .tpl-emoji { font-size: 1.5rem; display: block; margin-bottom: 4px; }
.tpl-card .tpl-name { font-size: 0.75rem; font-weight: 600; color: var(--ee-text); }
.tpl-card .tpl-desc { font-size: 0.65rem; color: var(--ee-text-muted); margin-top: 2px; line-height: 1.3; }

@media (max-width: 768px) {
    .main .block-container { padding-left: 1rem; padding-right: 1rem; }
    .ee-header-title { font-size: 1.3rem; }
    .tpl-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>

<div class="ee-header">
    <div class="ee-header-bar"></div>
    <div>
        <div class="ee-header-title">EE Publisher</div>
        <div class="ee-header-sub">Pega una URL y obtén la tarjeta lista para publicar</div>
    </div>
</div>
""", unsafe_allow_html=True)


# ============================================================
# FUNCIONES DE EXTRACCION DE URL
# ============================================================

def extract_from_url(url):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
            },
            timeout=20,
            allow_redirects=True,
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise Exception(f"No se pudo cargar la URL: {e}")

    soup = BeautifulSoup(resp.text, "html.parser")

    def meta(sel):
        tag = soup.select_one(sel)
        return (tag.get("content", "") if tag else "") or ""

    title = (
        meta('meta[property="og:title"]')
        or meta('meta[name="twitter:title"]')
        or meta('meta[name="title"]')
        or (soup.title.string if soup.title else "")
        or (soup.h1.get_text() if soup.h1 else "")
    )
    title = title.strip()
    for separator in [" | ", " - "]:
        if separator in title:
            parts = title.rsplit(separator, 1)
            if len(parts[1]) < 40 and not any(c in parts[1] for c in ".?!,;:"):
                title = parts[0].strip()
                break

    image = ""
    main_img_selectors = [
        "article figure img", "article header img",
        "figure.lead img", "figure[class*='hero'] img",
        "figure[class*='main'] img", "figure[class*='cover'] img",
        ".article-image img", ".post-thumbnail img",
        "article img", "main img",
    ]
    for selector in main_img_selectors:
        main_img = soup.select_one(selector)
        if main_img:
            srcset = main_img.get("srcset") or main_img.get("data-srcset")
            if srcset:
                best = parse_srcset_max(srcset)
                if best:
                    image = best
                    break
            src = (
                main_img.get("data-src")
                or main_img.get("data-original")
                or main_img.get("data-lazy-src")
                or main_img.get("src")
            )
            if src and not src.startswith("data:"):
                image = src
                break
    if not image:
        image = (
            meta('meta[property="og:image:secure_url"]')
            or meta('meta[property="og:image"]')
            or meta('meta[name="twitter:image"]')
            or meta('meta[name="twitter:image:src"]')
            or meta('link[rel="image_src"]')
        )
    if image:
        if image.startswith("//"):
            image = "https:" + image
        elif image.startswith("/"):
            from urllib.parse import urljoin
            image = urljoin(url, image)

    section = ""
    KNOWN_BRANDS = {
        "las-igualadas", "el-hilo", "bibo", "colombia-20", "vea",
        "claro-oscuro", "echemos-cuentas", "en-foco", "gastronomia",
        "impacto-mujer", "la-red-zoocial", "la-sede", "lado-a-lado",
        "ok", "perfil-sonoro", "rad", "region-en-accion",
        "usted-no-sabe-quien-soy-yo", "zona-z",
        "el-refugio-de-los-tocados",
    }
    try:
        parts = [p for p in urlparse(url).path.split("/") if p]
        skip = {"articulo", "article", "post", "noticia", "noticias",
                "news", "story", "stories", "amp", "video", "videos",
                "blog", "tag", "tags", "categoria", "category"}
        for part in parts:
            if part.lower() in KNOWN_BRANDS:
                section = part.replace("-", " ")
                break
        if not section:
            for part in parts:
                part_lower = part.lower()
                if part.replace("-", "").isdigit():
                    continue
                if part_lower in skip:
                    continue
                if len(part) == 4 and part.isdigit() and part.startswith("20"):
                    continue
                section = part.replace("-", " ")
                break
    except Exception:
        pass
    if not section:
        section = (
            meta('meta[property="article:section"]')
            or meta('meta[name="section"]')
            or meta('meta[name="category"]')
            or meta('meta[property="article:tag"]')
        )
    if not section:
        breadcrumb = soup.select_one(
            '[class*="breadcrumb"] a, nav.breadcrumb a, ol[itemtype*="BreadcrumbList"] a'
        )
        if breadcrumb:
            section = breadcrumb.get_text(strip=True)

    author = ""
    try:
        parts = [p for p in urlparse(url).path.split("/") if p]
        if "columnistas" in parts:
            idx = parts.index("columnistas")
            if idx + 1 < len(parts):
                slug = parts[idx + 1]
                lower_words = {"de", "del", "la", "las", "el", "los", "y", "da", "do"}
                words = slug.split("-")
                author = " ".join(
                    w if w in lower_words else w.capitalize()
                    for w in words
                )
                if author:
                    author = author[0].upper() + author[1:]
    except Exception:
        pass
    if not author:
        author_sel = soup.select_one(
            '[class*="author-name"], [class*="autor"], [rel="author"], '
            '[itemprop="author"], .byline a, .byline'
        )
        if author_sel:
            author = author_sel.get_text(strip=True)
    if not author:
        author = (
            meta('meta[name="author"]')
            or meta('meta[property="article:author"]')
            or meta('meta[name="twitter:creator"]')
        )
    GENERIC_AUTHORS = {
        "el espectador", "elespectador", "redaccion", "redacción",
        "@elespectador", "espectador",
    }
    if author and author.lower().strip() in GENERIC_AUTHORS:
        author = ""
    if author:
        for prefix in ("Por ", "POR ", "por "):
            if author.startswith(prefix):
                author = author[len(prefix):]
                break

    author_image = ""
    for sel in ['[class*="author"] img', '[class*="autor"] img',
                '[rel="author"] img', '[itemprop="author"] img',
                '.byline img']:
        ai = soup.select_one(sel)
        if ai:
            src = (ai.get("data-src") or ai.get("data-original")
                   or ai.get("data-lazy-src") or ai.get("src"))
            if src and not src.startswith("data:"):
                author_image = src
                break
    if author_image:
        if author_image.startswith("//"):
            author_image = "https:" + author_image
        elif author_image.startswith("/"):
            from urllib.parse import urljoin
            author_image = urljoin(url, author_image)

    summary = (
        meta('meta[property="og:description"]')
        or meta('meta[name="description"]')
        or meta('meta[name="twitter:description"]')
    )
    body_paragraphs = []
    for p in soup.select(
        'article p, [class*="article-body"] p, [class*="content"] p, main p'
    ):
        text = p.get_text(strip=True)
        if text and len(text) > 40:
            body_paragraphs.append(text)
        if len(body_paragraphs) >= 6:
            break
    if not summary and body_paragraphs:
        summary = body_paragraphs[0]
    TARGET_SUMMARY_LEN = 300
    if summary and len(summary) < TARGET_SUMMARY_LEN and body_paragraphs:
        seen_in_summary = summary.lower()
        for para in body_paragraphs:
            if para.lower()[:80] in seen_in_summary:
                continue
            summary = (summary + " " + para).strip()
            if len(summary) >= TARGET_SUMMARY_LEN:
                break
    if summary:
        summary = summary.strip()
        for q in ('"', '\u201c', '\u201d', '\u00ab', '\u00bb'):
            summary = summary.replace(q, "")
        summary = summary.strip()
        if ":" in summary:
            head, _, tail = summary.rpartition(":")
            if (tail and len(tail.strip()) < 50 and "." not in tail
                    and len(head.strip()) > 30):
                summary = head.strip()
        if len(summary) > 380:
            cut = summary[:380]
            last_period = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
            if last_period > 200:
                summary = cut[:last_period + 1]
            else:
                last_space = cut.rfind(" ")
                if last_space > 200:
                    summary = cut[:last_space] + "..."
                else:
                    summary = cut + "..."

    return {
        "title": title.strip(),
        "image": (image or "").strip(),
        "section": (section or "").upper().strip(),
        "author": (author or "").strip(),
        "author_image": (author_image or "").strip(),
        "summary": (summary or "").strip(),
        "url": url,
    }


def parse_srcset_max(srcset):
    if not srcset:
        return None
    best_url = None
    best_width = 0
    for item in srcset.split(","):
        item = item.strip()
        if not item:
            continue
        parts = item.rsplit(" ", 1)
        if len(parts) == 2:
            url_part, width_part = parts
            try:
                width = int("".join(c for c in width_part if c.isdigit()))
                if width > best_width:
                    best_width = width
                    best_url = url_part.strip()
            except ValueError:
                pass
        elif len(parts) == 1:
            if not best_url:
                best_url = parts[0].strip()
    return best_url


# ============================================================
# CONFIGURACION DE PLANTILLAS
# ============================================================

ALL_TEMPLATES = {
    **TEMPLATES,
    "generic": {
        "name": "Genérica",
        "description": "Fondos PNG con detección automática de color",
        "category": "Clásicas",
    },
}

TEMPLATE_FOOTER_INFO = {
    "classic":                         "Iconos sociales + logo EE",
    "card":                            "Iconos sociales + logo EE",
    "with_cta":                        "CTA Lea la noticia + logo EE",
    "attention":                       "CTA Lea la noticia + logo EE",
    "lo_ultimo":                       "Solo foto + overlay + título",
    "atencion":                        "Solo foto + overlay + título",
    "atencion_simple":                 "Solo foto + overlay + título",
    "ultima_hora":                     "Solo foto + overlay + título",
    "en_vivo":                         "Logo EN VIVO arriba derecha, sin footer",
    "en_vivo_simple":                  "Solo foto + overlay + título",
    "story_minimal":                   "Sin logo ni iconos sociales",
    "echemos_cuentas":                 "Logo de marca grande arriba + logo EE abajo",
    "elecciones_2026_post":            "Solo foto + overlay + título",
    "elecciones_2026_story":           "Solo foto + overlay + título",
    "elecciones_2026_ultima_hora_post":"Foto + overlay ultima-hora + título",
    "elecciones_2026_ultima_hora_story":"Foto + overlay ultima-hora + título",
    "envivo_elecciones_post":          "Solo foto + overlay + título",
    "envivo_elecciones_story":         "Solo foto + overlay + título",
    "columnista":                      "Iconos sociales + CTA + logo EE",
    "generic":                         "Configurable (ver opciones)",
    "elecciones_2026_card_post":       "Foto enmarcada + texto negro sin línea roja",
}

# Icono emoji y descripción corta para el grid visual
TEMPLATE_VISUAL = {
    "classic":                          ("🖼️",  "Clásica"),
    "card":                             ("🃏",  "Card"),
    "with_cta":                         ("🔗",  "Con CTA"),
    "attention":                        ("🟣",  "Atención"),
    "lo_ultimo":                        ("🔴",  "Lo Último"),
    "atencion":                         ("⚠️",  "Atención (simple)"),
    "ultima_hora":                      ("🚨",  "Última Hora"),
    "en_vivo":                          ("📡",  "En Vivo Story"),
    "en_vivo_simple":                   ("🔴",  "En Vivo"),
    "story_minimal":                    ("📱",  "Story Minimal"),
    "echemos_cuentas":                  ("📊",  "Echemos Cuentas"),
    "columnista":                       ("✍️",  "Columnista"),
    "generic":                          ("🎨",  "Genérica"),
    "elecciones_2026_post":             ("🗳️",  "Elecciones Post"),
    "elecciones_2026_story":            ("🗳️",  "Elecciones Story"),
    "elecciones_2026_ultima_hora_post": ("⚡",  "Últ. Hora Post"),
    "elecciones_2026_ultima_hora_story":("⚡",  "Últ. Hora Story"),
    "envivo_elecciones_post":           ("📡",  "En Vivo Elecc. Post"),
    "envivo_elecciones_story":          ("📡",  "En Vivo Elecc. Story"),
    "elecciones_2026_card_post":        ("🖼️",  "Card Elecciones"),
}


# ============================================================
# PESTAÑAS
# ============================================================
tab_noticias, tab_resultados = st.tabs([
    "📰 Tarjetas de noticias",
    "🗳️ Resultados Elecciones 2026",
])


# =====================================================
# PESTAÑA 1: TARJETAS DE NOTICIAS
# =====================================================
with tab_noticias:
    col_controls, col_preview = st.columns([5, 4], gap="large")

    with col_controls:

        # ── 1. URL ──────────────────────────────────────────
        st.subheader("1. URL del artículo")

        col_url, col_reset = st.columns([5, 1])
        with col_url:
            url = st.text_input(
                "URL",
                placeholder="🔗  https://www.elespectador.com/...",
                label_visibility="collapsed",
            )
        with col_reset:
            if st.button("↻ Resetear", help="Limpiar todo y empezar de nuevo"):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()

        if "data" not in st.session_state:
            st.markdown("""
            <div style="background: white; border: 1px solid #E5E7EB;
                 border-left: 4px solid #E31B23; border-radius: 10px;
                 padding: 14px 18px; margin: 10px 0 16px 0;
                 color: #4B5563; font-size: 0.92rem;">
            💡 <strong>Cómo funciona:</strong> Pega una URL de El Espectador,
            extraemos título, sección e imagen automáticamente. Luego eliges
            plantilla y formato, y descargas la tarjeta lista para publicar.
            </div>
            """, unsafe_allow_html=True)

        if st.button("✨ Extraer y generar tarjeta", type="primary"):
            if not url:
                st.error("Pega una URL primero")
            else:
                try:
                    with st.spinner("Extrayendo contenido..."):
                        data = extract_from_url(url)
                    keys_to_remove = [k for k in st.session_state.keys() if k.startswith("img_cache_")]
                    for k in keys_to_remove:
                        del st.session_state[k]
                    st.session_state["data"] = data
                    st.session_state["edited"] = False
                    st.session_state["card_generated"] = False
                except Exception as e:
                    st.error(f"Error al extraer: {e}")

        # ── Solo si hay data ─────────────────────────────────
        if "data" in st.session_state:
            data = st.session_state["data"]

            # ── 2. Datos extraídos ───────────────────────────
            st.subheader("2. Contenido")

            _ai_title_default = st.session_state.get("ai_title_override")
            if _ai_title_default:
                if "title_input" in st.session_state:
                    del st.session_state["title_input"]
                data["title"] = _ai_title_default
                st.session_state["ai_title_override"] = None

            title   = st.text_input("Título", value=data["title"], key="title_input")
            section = st.text_input("Sección", value=data["section"], key="section_input")

            # Formato aquí, junto al contenido (más natural)
            selected_format = st.selectbox(
                "Formato",
                options=list(FORMATS.keys()),
                format_func=lambda k: FORMATS[k]["name"] + " — " + FORMATS[k]["description"],
                label_visibility="collapsed",
            )

            # Imagen: URL primero, subir como opción secundaria colapsada
            image_url = st.text_input("URL de la imagen", value=data["image"], key="image_input")
            with st.expander("📁 Subir imagen desde el computador", expanded=False):
                uploaded_file = st.file_uploader(
                    "Imagen",
                    type=["jpg", "jpeg", "png", "webp"],
                    key="image_uploader",
                    label_visibility="collapsed",
                )
                if uploaded_file is not None:
                    up_key = "img_upload_" + uploaded_file.name + "_" + str(uploaded_file.size)
                    if up_key not in st.session_state:
                        st.session_state[up_key] = Image.open(uploaded_file).convert("RGB")
                    image_url = "upload://" + up_key
                    data["image"] = image_url

            # Columnista: colapsado por defecto
            with st.expander("✍️ Datos del columnista (solo plantilla Columnista)", expanded=False):
                author = st.text_input("Autor", value=data.get("author", ""), key="author_input")
                author_image_url = st.text_input(
                    "URL foto del autor",
                    value=data.get("author_image", ""),
                    key="author_image_input",
                )
                author_uploaded = st.file_uploader(
                    "...o subir foto del autor",
                    type=["jpg", "jpeg", "png", "webp"],
                    key="author_image_uploader",
                )
                summary = st.text_area(
                    "Resumen / lead",
                    value=data.get("summary", ""),
                    key="summary_input",
                    height=200,
                )
                data["author"] = author
                data["summary"] = summary

                if author_image_url != data.get("author_image", ""):
                    keys_to_remove = [k for k in st.session_state.keys() if k.startswith("author_img_cache_")]
                    for k in keys_to_remove:
                        del st.session_state[k]
                data["author_image"] = author_image_url

                if author_uploaded is not None:
                    upload_key = "author_upload_" + author_uploaded.name + "_" + str(author_uploaded.size)
                    if not author_image_url or not author_image_url.startswith("upload://"):
                        author_image_url = "upload://" + upload_key
                        data["author_image"] = author_image_url
                    cache_key = "author_img_cache_" + author_image_url
                    if cache_key not in st.session_state:
                        st.session_state[cache_key] = Image.open(author_uploaded).convert("RGB")

            data["title"]   = title
            data["section"] = section

            if image_url != data.get("image"):
                keys_to_remove = [k for k in st.session_state.keys() if k.startswith("img_cache_")]
                for k in keys_to_remove:
                    del st.session_state[k]
            data["image"] = image_url

            # ── 3. Plantilla — GRID VISUAL ───────────────────
            st.subheader("3. Plantilla")

            # Detectar plantilla por sección/URL
            SECTION_TO_TEMPLATE = {"echemos cuentas": "echemos_cuentas"}
            section_lower = (section or "").lower().strip()
            auto_template = SECTION_TO_TEMPLATE.get(section_lower)
            _url_value = st.session_state.get("data", {}).get("url", "") or url or ""
            if "/politica/elecciones-colombia-2026" in _url_value.lower():
                auto_template = "elecciones_2026_post"

            _ai_template_default = st.session_state.get("ai_template_override")
            ai_suggested_template = None
            if _ai_template_default:
                ai_suggested_template = _ai_template_default
                st.session_state["ai_template_override"] = None

            if ai_suggested_template:
                st.success("✨ Plantilla sugerida por IA: " + ALL_TEMPLATES.get(ai_suggested_template, {}).get("name", ai_suggested_template))
            elif auto_template:
                st.caption("Sugerencia automática para '" + (section or "esta URL") + "': " + ALL_TEMPLATES.get(auto_template, {}).get("name", auto_template))

            # Agrupar por categoría
            TEMPLATE_CATEGORIES = {}
            for tkey, tinfo in ALL_TEMPLATES.items():
                cat = tinfo.get("category", "Otras")
                if cat not in TEMPLATE_CATEGORIES:
                    TEMPLATE_CATEGORIES[cat] = []
                TEMPLATE_CATEGORIES[cat].append(tkey)

            category_options = list(TEMPLATE_CATEGORIES.keys())

            # Determinar default
            if ai_suggested_template and ai_suggested_template in ALL_TEMPLATES:
                default_template_key = ai_suggested_template
            elif auto_template in ALL_TEMPLATES:
                default_template_key = auto_template
            else:
                default_template_key = TEMPLATE_CATEGORIES[category_options[0]][0]

            default_category = ALL_TEMPLATES.get(default_template_key, {}).get("category", category_options[0])
            if default_category not in category_options:
                default_category = category_options[0]

            # Tabs por categoría (pill-style horizontal)
            selected_category = st.radio(
                "Categoría",
                options=category_options,
                index=category_options.index(default_category),
                horizontal=True,
                label_visibility="collapsed",
            )

            templates_in_category = TEMPLATE_CATEGORIES[selected_category]

            # Estado para la plantilla seleccionada en el grid
            grid_state_key = "selected_template_" + selected_category
            if grid_state_key not in st.session_state:
                if default_template_key in templates_in_category:
                    st.session_state[grid_state_key] = default_template_key
                else:
                    st.session_state[grid_state_key] = templates_in_category[0]

            # Renderizar grid visual 3 columnas
            n_tpl = len(templates_in_category)
            cols_per_row = 3
            for row_start in range(0, n_tpl, cols_per_row):
                row_keys = templates_in_category[row_start : row_start + cols_per_row]
                cols = st.columns(cols_per_row)
                for col_idx, tkey in enumerate(row_keys):
                    with cols[col_idx]:
                        is_active = st.session_state[grid_state_key] == tkey
                        emoji, short_name = TEMPLATE_VISUAL.get(tkey, ("📄", ALL_TEMPLATES[tkey]["name"]))
                        border = "2px solid #E31B23" if is_active else "1.5px solid #E5E7EB"
                        bg     = "#FFF5F5" if is_active else "white"
                        st.markdown(
                            f"""<div style="background:{bg}; border:{border}; border-radius:10px;
                                 padding:10px 8px; text-align:center; margin-bottom:2px;">
                                <span style="font-size:1.4rem;">{emoji}</span><br>
                                <span style="font-size:0.78rem; font-weight:600; color:#1A1A1A;">{short_name}</span>
                            </div>""",
                            unsafe_allow_html=True,
                        )
                        if st.button(
                            "✓" if is_active else "Elegir",
                            key=f"tpl_btn_{tkey}",
                            use_container_width=True,
                        ):
                            st.session_state[grid_state_key] = tkey
                            st.rerun()

            selected_template = st.session_state[grid_state_key]
            st.caption("Seleccionada: **" + ALL_TEMPLATES[selected_template]["name"] + "** — " + ALL_TEMPLATES[selected_template]["description"])

            # ── Fondo (solo plantilla generic) ──────────────
            selected_fondo = None
            step_offset = 0

            if selected_template == "generic":
                st.subheader("4. Fondo (degradado)")
                step_offset = 1
                fondos = list_fondos()
                if not fondos:
                    st.warning("No hay fondos disponibles en assets/fondos/")
                else:
                    suggested = suggest_fondo_for_section(section)
                    default_idx = fondos.index(suggested) if suggested in fondos else 0
                    st.caption("Sugerencia automática para '" + (section or "sin sección") + "': " + str(suggested))
                    selected_fondo = st.selectbox(
                        "Fondo:",
                        options=fondos,
                        index=default_idx,
                        help="Archivos PNG de assets/fondos/",
                    )

            # Carga de imagen (sin ajustes aquí, van debajo del preview)
            if not title or not image_url:
                source_img = None
            else:
                if image_url.startswith("upload://"):
                    up_key = image_url[len("upload://"):]
                    source_img = st.session_state.get(up_key)
                else:
                    cache_key = "img_cache_" + image_url
                    if cache_key not in st.session_state:
                        with st.spinner("Descargando imagen..."):
                            try:
                                st.session_state[cache_key] = fetch_image(image_url)
                            except Exception as e:
                                st.error("Error al descargar imagen: " + str(e))
                                st.stop()
                    source_img = st.session_state[cache_key]

            # Valores por defecto de ajustes (se sobreescriben desde col_preview)
            zoom      = st.session_state.get("adj_zoom", 1.0)
            offset_x  = st.session_state.get("adj_offset_x", 0.5)
            offset_y  = st.session_state.get("adj_offset_y", 0.5)
            title_size_multiplier = st.session_state.get("adj_title_size", 1.0)

            # ── OPCIONES AVANZADAS (colapsadas) ──────────────
            seccion_con_icono = False
            logo_override     = None
            logo_variant      = None
            show_cta          = False
            show_social_icons = False
            sticker_position  = "bottom"

            with st.expander("⚙️ Opciones avanzadas", expanded=False):
                col_opt1, col_opt2 = st.columns(2)

                with col_opt1:
                    seccion_con_icono = st.checkbox(
                        "Icono en sticker de sección",
                        value=False,
                        help="Usa el sticker con icono (carpeta secciones-icono/)",
                    )

                if selected_template in ("classic", "with_cta", "story_minimal", "generic", "echemos_cuentas"):
                    available_logos = list_section_logos()
                    if available_logos:
                        auto_logo_path = find_section_logo(section) if section else None
                        auto_logo_name = None
                        if auto_logo_path:
                            import os as _os
                            auto_logo_name = _os.path.basename(_os.path.dirname(auto_logo_path))

                        options = ["(Automático según sección)", "(Sin logo)"] + available_logos
                        if auto_logo_name and auto_logo_name in available_logos:
                            options[0] = "(Automático según sección) — " + auto_logo_name

                        col_logo, col_variant_col = st.columns(2)
                        with col_logo:
                            selected_logo = st.selectbox(
                                "Logo de sección",
                                options=options,
                                index=0,
                                help="Elige qué logo de marca/sección usar",
                            )
                        if selected_logo.startswith("(Automático"):
                            logo_override = None
                            variant_folder = auto_logo_name or ""
                        elif selected_logo == "(Sin logo)":
                            logo_override = "__NONE__"
                            variant_folder = None
                        else:
                            logo_override = selected_logo
                            variant_folder = selected_logo

                        with col_variant_col:
                            if variant_folder:
                                variants = list_logo_variants(variant_folder)
                                if not variants and auto_logo_name:
                                    variant_folder = auto_logo_name
                                    variants = list_logo_variants(variant_folder)
                                if variants:
                                    variant_labels = [v[0] for v in variants]
                                    variant_files  = [v[1] for v in variants]
                                    default_v_idx  = 0
                                    for i, label in enumerate(variant_labels):
                                        if label.lower() == "blanco":
                                            default_v_idx = i
                                            break
                                    selected_variant_label = st.selectbox(
                                        "Variante de color",
                                        options=variant_labels,
                                        index=default_v_idx,
                                    )
                                    idx          = variant_labels.index(selected_variant_label)
                                    logo_variant = variant_files[idx]
                                else:
                                    st.caption("Sin variantes disponibles")
                            else:
                                st.caption("Sin logo seleccionado")

                with col_opt2:
                    if selected_template == "generic":
                        footer_type = st.radio(
                            "Footer:",
                            options=["Iconos sociales", "CTA Lea la noticia", "Sin nada"],
                        )
                        show_cta          = footer_type == "CTA Lea la noticia"
                        show_social_icons = footer_type == "Iconos sociales"
                    else:
                        st.caption("Footer: " + TEMPLATE_FOOTER_INFO.get(selected_template, "—"))

                if selected_template == "generic":
                    sticker_position_label = st.radio(
                        "Posición del sticker de sección",
                        options=["Abajo (junto al título)", "Arriba (estilo clásico)", "Sin sticker"],
                        index=0,
                        horizontal=True,
                    )
                    if sticker_position_label.startswith("Arriba"):
                        sticker_position = "top"
                    elif sticker_position_label.startswith("Sin"):
                        sticker_position = "none"
                    else:
                        sticker_position = "bottom"

    # ── COLUMNA DERECHA: PREVIEW ─────────────────────────────
    with col_preview:
        if "data" not in st.session_state:
            st.markdown("""
            <div class="ee-preview-empty">
                <div class="ee-preview-empty-icon">🖼️</div>
                <div style="font-weight:600;font-size:1.05rem;color:#1A1A1A;margin-bottom:6px;">
                    Aquí aparecerá tu tarjeta
                </div>
                <div style="font-size:0.9rem;">
                    Pega una URL y haz clic en <strong>Extraer y generar</strong> para empezar.
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            data = st.session_state["data"]
            if not data.get("title") or not data.get("image"):
                st.markdown("""
                <div class="ee-preview-empty">
                    <div class="ee-preview-empty-icon">⚠️</div>
                    <div style="font-weight:600;font-size:1rem;color:#1A1A1A;margin-bottom:6px;">
                        Completa título e imagen
                    </div>
                </div>
                """, unsafe_allow_html=True)
            elif source_img is None:
                pass
            else:
                st.subheader("Vista previa")
                try:
                    effective_override = logo_override
                    if logo_override == "__NONE__":
                        effective_override = "___no_logo___"

                    author_img_obj  = None
                    author_img_url  = data.get("author_image", "")
                    if author_img_url:
                        author_cache_key = "author_img_cache_" + author_img_url
                        if author_cache_key not in st.session_state:
                            try:
                                author_img_obj = fetch_image(author_img_url)
                                st.session_state[author_cache_key] = author_img_obj
                            except Exception:
                                author_img_obj = None
                        else:
                            author_img_obj = st.session_state[author_cache_key]

                    img = generate_card_from_image(
                        source_image=source_img,
                        section=section or "NOTICIAS",
                        title=title,
                        template=selected_template,
                        format_key=selected_format,
                        fondo_name=selected_fondo,
                        seccion_con_icono=seccion_con_icono,
                        show_cta=show_cta,
                        show_social_icons=show_social_icons,
                        zoom=st.session_state.get("adj_zoom", 1.0),
                        offset_x=st.session_state.get("adj_offset_x", 0.5),
                        offset_y=st.session_state.get("adj_offset_y", 0.5),
                        title_size_multiplier=st.session_state.get("adj_title_size", 1.0),
                        logo_override=effective_override,
                        logo_variant=logo_variant,
                        sticker_position=sticker_position,
                        author=data.get("author", ""),
                        summary=data.get("summary", ""),
                        author_image=author_img_obj
    
                    )

                    # Marcar que ya hay una tarjeta generada
                    st.session_state["card_generated"] = True
                    st.session_state["last_card_img"]  = img

                    st.markdown('<div class="ee-preview-card">', unsafe_allow_html=True)
                    st.image(img)
                    st.markdown('</div>', unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)

                    # ── Ajustes debajo de la imagen ──────────
                    st.markdown("**Ajustar tarjeta**")
                    c_ts, c_z, c_x, c_y = st.columns(4)
                    with c_ts:
                        new_ts = st.slider("Título", 0.50, 1.50, st.session_state.get("adj_title_size", 1.0), 0.05, key="sl_title_size")
                        st.session_state["adj_title_size"] = new_ts
                    with c_z:
                        new_z = st.slider("Zoom", 1.0, 3.0, st.session_state.get("adj_zoom", 1.0), 0.05, key="sl_zoom")
                        st.session_state["adj_zoom"] = new_z
                    with c_x:
                        new_x = st.slider("Horiz.", 0.0, 1.0, st.session_state.get("adj_offset_x", 0.5), 0.05, key="sl_offset_x")
                        st.session_state["adj_offset_x"] = new_x
                    with c_y:
                        new_y = st.slider("Vert.", 0.0, 1.0, st.session_state.get("adj_offset_y", 0.5), 0.05, key="sl_offset_y")
                        st.session_state["adj_offset_y"] = new_y

                    
                    buf = BytesIO()
                    img.save(buf, format="PNG")
                    buf.seek(0)

                    safe_name = "".join(c if c.isalnum() else "-" for c in title.lower())[:50]

                    st.download_button(
                        label="⬇ Descargar PNG — " + FORMATS[selected_format]["name"] + " / " + ALL_TEMPLATES[selected_template]["name"],
                        data=buf,
                        file_name=selected_format + "-" + selected_template + "-" + safe_name + ".png",
                        mime="image/png",
                        type="primary",
                    )

                    st.markdown(
                        """<div style='padding:10px 14px;background:#F5F6F8;border-radius:8px;
                           color:#6B7280;font-size:0.85rem;text-align:center;margin-top:8px;'>
                           ✓ Lista para subir a SocialFlow
                           </div>""",
                        unsafe_allow_html=True,
                    )

                    # ── IA y Hootsuite: solo cuando hay tarjeta generada ──
                    # ── Mejorar con IA ─────────────────────────────────
                    if AI_ENABLED:
                        with st.expander("✨ Mejorar contenido con IA (Gemini)", expanded=False):
                            st.caption("Genera titulares optimizados, caption para Instagram, hashtags y sugiere la mejor plantilla.")

                            if st.button("🪄 Mejorar con IA", key="btn_ai_enhance"):
                                with st.spinner("Gemini está pensando..."):
                                    try:
                                        result = ai_helper.enhance_content(
                                            title=title,
                                            section=section,
                                            article_text=data.get("summary", ""),
                                            current_template=None,
                                        )
                                        if result:
                                            st.session_state["ai_result"] = result
                                            if result.get("titulo_post"):
                                                st.session_state["ai_title_override"] = result["titulo_post"]
                                            if result.get("plantilla_sugerida"):
                                                st.session_state["ai_template_override"] = result["plantilla_sugerida"]
                                            st.rerun()
                                        else:
                                            st.error("La IA no devolvió un resultado válido. Intentá de nuevo.")
                                    except Exception as e:
                                        st.error("Error al llamar a Gemini: " + str(e))

                            ai_result = st.session_state.get("ai_result")
                            if ai_result:
                                st.markdown("---")
                                sug   = ai_result.get("plantilla_sugerida", "")
                                razon = ai_result.get("razon_plantilla", "")
                                if sug:
                                    st.info("**Plantilla sugerida:** `" + sug + "` — " + razon)

                                col_t1, col_t2 = st.columns(2)
                                with col_t1:
                                    st.markdown("**Título POST:**")
                                    st.code(ai_result.get("titulo_post", ""), language=None)
                                with col_t2:
                                    st.markdown("**Título STORY:**")
                                    st.code(ai_result.get("titulo_story", ""), language=None)

                                st.markdown("**Caption para Instagram:**")
                                caption_full = ai_helper.format_caption_with_hashtags(
                                    ai_result.get("caption_ig", ""),
                                    ai_result.get("hashtags", []),
                                )
                                st.text_area(
                                    "Caption + hashtags",
                                    value=caption_full,
                                    height=250,
                                    key="ai_caption_display",
                                    label_visibility="collapsed",
                                )

                                hashtags = ai_result.get("hashtags", [])
                                if hashtags:
                                    st.markdown("**Hashtags:** " + " ".join(["`#" + h + "`" for h in hashtags]))

                                if st.button("🗑️ Descartar resultados de IA", key="btn_ai_clear"):
                                    st.session_state["ai_result"] = None
                                    st.rerun()

                    # ── Hootsuite: solo cuando hay tarjeta generada ─────
                    if HOOTSUITE_ENABLED:
                        hs_token = st.session_state.get("hs_token")
                        if not hs_token:
                            auth_url = hootsuite_helper.build_authorize_url(
                                client_id=HS_CREDS["client_id"],
                                redirect_uri=HS_CREDS["redirect_uri"],
                                scope="offline",
                            )
                            with st.expander("📤 Publicar en Hootsuite", expanded=False):
                                st.info("Conecta tu cuenta de Hootsuite para publicar directamente.")
                                st.markdown(
                                    f'<a href="{auth_url}" target="_self" '
                                    f'style="display:inline-block;background:#143059;color:white;'
                                    f'padding:8px 16px;border-radius:6px;text-decoration:none;'
                                    f'font-weight:600;">🔗 Conectar Hootsuite</a>',
                                    unsafe_allow_html=True,
                                )
                        else:
                            with st.expander("📤 Publicar en Hootsuite", expanded=False):
                                col_hs_msg, col_hs_disc = st.columns([8, 2])
                                with col_hs_msg:
                                    st.success("✅ Hootsuite conectado")
                                with col_hs_disc:
                                    if st.button("🔌 Desconectar", key="hs_disconnect"):
                                        st.session_state["hs_token"] = None
                                        st.session_state["hs_profiles"] = None
                                        st.rerun()

                                try:
                                    hs_token = hootsuite_helper.ensure_valid_token(
                                        hs_token,
                                        HS_CREDS["client_id"],
                                        HS_CREDS["client_secret"],
                                    )
                                    st.session_state["hs_token"] = hs_token
                                except Exception as e:
                                    st.error("Tu sesión de Hootsuite expiró: " + str(e))
                                    if st.button("🔌 Limpiar sesión"):
                                        st.session_state["hs_token"] = None
                                        st.rerun()
                                    st.stop()

                                access = hs_token["access_token"]

                                if st.session_state.get("hs_profiles") is None:
                                    try:
                                        with st.spinner("Cargando tus redes sociales..."):
                                            profiles = hootsuite_helper.list_social_profiles(access)
                                            st.session_state["hs_profiles"] = profiles
                                    except Exception as e:
                                        st.error("Error cargando perfiles: " + str(e))
                                        st.stop()

                                profiles = st.session_state["hs_profiles"] or []

                                if not profiles:
                                    st.warning("No tienes redes sociales conectadas en Hootsuite.")
                                    if st.button("🔄 Refrescar", key="hs_refresh"):
                                        st.session_state["hs_profiles"] = None
                                        st.rerun()
                                else:
                                    st.caption(f"✅ Listo para publicar en **{len(profiles)}** cuenta(s)")
                                    st.markdown("**📱 Cuentas destino:**")
                                    selected_profile_ids = []
                                    for p in profiles:
                                        label = hootsuite_helper.format_profile_label(p)
                                        if st.checkbox(label, key="hs_chk_" + str(p["id"])):
                                            selected_profile_ids.append(p["id"])

                                    st.markdown("**📝 Caption:**")
                                    ai_res = st.session_state.get("ai_result")
                                    if ai_res:
                                        default_caption = ai_helper.format_caption_with_hashtags(
                                            ai_res.get("caption_ig", ""), ai_res.get("hashtags", [])
                                        )
                                    else:
                                        default_caption = data.get("title", "") + "\n\nLee la noticia completa en elespectador.com"

                                    caption = st.text_area("Caption del post", value=default_caption, height=160, label_visibility="collapsed")

                                    st.markdown("**⏰ Cuándo publicar:**")
                                    publish_mode_label = st.radio(
                                        "Modo",
                                        options=["Publicar ahora", "Programar", "Guardar como borrador"],
                                        horizontal=True,
                                        label_visibility="collapsed",
                                    )
                                    scheduled_dt = None
                                    if publish_mode_label == "Programar":
                                        col_date, col_time = st.columns(2)
                                        with col_date:
                                            sch_date = st.date_input("Fecha", value=datetime.now().date() + timedelta(days=1))
                                        with col_time:
                                            sch_time = st.time_input("Hora", value=datetime.now().time().replace(second=0, microsecond=0))
                                        scheduled_dt = datetime.combine(sch_date, sch_time)
                                        st.caption(f"Se programará para: {scheduled_dt.strftime('%Y-%m-%d %H:%M')}")

                                    mode_map = {"Publicar ahora": "now", "Programar": "schedule", "Guardar como borrador": "draft"}
                                    publish_mode  = mode_map[publish_mode_label]
                                    can_publish   = bool(selected_profile_ids) and bool(caption.strip())

                                    if not selected_profile_ids:
                                        st.warning("Selecciona al menos una red social.")
                                    if not caption.strip():
                                        st.warning("El texto del post no puede estar vacío.")

                                    if st.button("📤 Enviar a Hootsuite", type="primary", disabled=not can_publish):
                                        with st.spinner("Enviando..."):
                                            try:
                                                img_buf = BytesIO()
                                                img_rgb = img.convert("RGB") if img.mode != "RGB" else img
                                                img_rgb.save(img_buf, format="JPEG", quality=92)
                                                result = hootsuite_helper.publish_post(
                                                    access_token=access,
                                                    text=caption,
                                                    social_profile_ids=selected_profile_ids,
                                                    image_bytes=img_buf.getvalue(),
                                                    image_mime="image/jpeg",
                                                    mode=publish_mode,
                                                    scheduled_time=scheduled_dt,
                                                )
                                                st.session_state["hs_last_publish"] = result
                                                if publish_mode == "now":
                                                    st.success("✅ Publicación enviada correctamente.")
                                                elif publish_mode == "schedule":
                                                    st.success(f"✅ Programada para {scheduled_dt.strftime('%Y-%m-%d %H:%M')}.")
                                                else:
                                                    st.success("✅ Borrador guardado en Hootsuite.")
                                                if result:
                                                    with st.expander("Respuesta técnica"):
                                                        st.json(result)
                                            except Exception as e:
                                                st.error(f"❌ Error al publicar: {e}")
                                                import traceback
                                                with st.expander("Detalles técnicos"):
                                                    st.code(traceback.format_exc())

                except Exception as e:
                    st.error("Error al generar: " + str(e))
                    import traceback
                    with st.expander("Detalles del error"):
                        st.code(traceback.format_exc())


# =====================================================
# PESTAÑA 2: RESULTADOS ELECCIONES 2026
# =====================================================
with tab_resultados:

    def update_prev_pct(idx):
        st.session_state[f"prev_pct_{idx}"] = st.session_state.get(f"current_pct_{idx}", 0.0)
        st.session_state[f"current_pct_{idx}"] = st.session_state[f"res_pct_{idx}"]

    col_res_controls, col_res_preview = st.columns([5, 4], gap="large")

    res_format   = st.session_state.get("res_format", "post")
    boletin_text = st.session_state.get("res_boletin_text", "BOLETÍN 1")

    if "datos_candidatos" in st.session_state:
        try:
            res_img = render_resultados_candidatos(
                candidatos=st.session_state["datos_candidatos"],
                format_key=res_format,
                boletin_text=boletin_text,
            )
            st.image(res_img)
        except Exception:
            pass

    with col_res_controls:
        st.subheader("🗳️ Generador de tarjetas de resultados")
        st.caption("Selecciona candidatos del catálogo, ingresa porcentaje y votos.")

        candidatos_disponibles = list_candidatos()
        if not candidatos_disponibles:
            st.error("⚠️ No hay candidatos cargados en assets/candidatos/. Agregá PNGs ahí y reintentá.")
            st.stop()

        cand_by_key  = {c["key"]: c for c in candidatos_disponibles}
        cand_options = [c["key"] for c in candidatos_disponibles]

        def _cand_label(k):
            return cand_by_key.get(k, {}).get("nombre", k)

        n_candidatos = st.slider(
            "¿Cuántos candidatos vas a comparar?",
            min_value=2, max_value=5, value=2, step=1,
            key="res_n_candidatos",
        )

        res_format = st.radio(
            "Formato",
            options=["post", "story"],
            format_func=lambda k: FORMATS[k]["name"] + " (" + FORMATS[k]["description"] + ")",
            horizontal=True,
            key="res_format",
        )

        boletin_text = st.text_input(
            "Texto del boletín (esquina inferior derecha)",
            value="BOLETÍN 1",
            key="res_boletin_text",
            placeholder="Ej: BOLETÍN 1, PRIMER REPORTE, etc.",
            help="Aparecerá como recuadro rojo en la esquina inferior derecha del cuadro gris.",
        )

        st.markdown("---")
        st.markdown("### Datos de los candidatos")
        st.caption("Total disponibles en catálogo: " + str(len(candidatos_disponibles)))

        candidatos_data = []
        color_options   = list(BAR_COLORS.keys())

        for i in range(n_candidatos):
            st.markdown("**Candidato " + str(i + 1) + "**")

            if f"current_pct_{i}" not in st.session_state:
                st.session_state[f"current_pct_{i}"] = 0.0
            if f"prev_pct_{i}" not in st.session_state:
                st.session_state[f"prev_pct_{i}"] = 0.0

            col_sel, col_pct, col_votos, col_color = st.columns([2.5, 3.5, 2, 2])

            with col_sel:
                sel_key = st.selectbox(
                    "Candidato",
                    options=cand_options,
                    index=min(i, len(cand_options) - 1),
                    format_func=_cand_label,
                    key="res_cand_" + str(i),
                )
            with col_pct:
                pct = st.slider(
                    "%",
                    min_value=0.0, max_value=100.0, step=0.1,
                    key="res_pct_" + str(i),
                    on_change=update_prev_pct,
                    args=(i,)
                )
                prev_val = st.session_state[f"prev_pct_{i}"]
                if prev_val > 0.0:
                    st.caption(f"🔙 Anterior: {prev_val:.1f}%")
            with col_votos:
                votos = st.text_input(
                    "Votos",
                    key="res_votos_" + str(i),
                    placeholder="Ej: 250XXX",
                )
            with col_color:
                color = st.selectbox(
                    "Color barra",
                    options=color_options,
                    index=i % len(color_options),
                    key="res_color_" + str(i),
                )

            foto_img = load_candidato_image(sel_key)
            nombre   = cand_by_key.get(sel_key, {}).get("nombre", "")
            candidatos_data.append({
                "foto":        foto_img,
                "nombre":      nombre,
                "porcentaje":  pct,
                "votos":       votos,
                "color_barra": color,
            })
            st.markdown("")

        with st.expander("🔄 Importar resultados desde El Espectador", expanded=False):
            st.caption("Obtiene resultados nacionales y por departamento directamente desde la API de El Espectador.")

            if st.button("🚀 Obtener resultados + datos para mapa", type="primary"):
                try:
                    with st.spinner("Consultando API El Espectador..."):
                        cands_scraped = get_candidatos_resultados()
                        st.session_state["datos_candidatos"] = cands_scraped
                    with st.spinner("Obteniendo resultados por departamento..."):
                        territorial = get_resultados_territoriales()
                        st.session_state["datos_territoriales"] = territorial
                        for k in ["carrusel_tarjetas", "carrusel_boletin", "carrusel_idx"]:
                            st.session_state.pop(k, None)
                    n_deptos    = len(territorial.get("departamentos", []))
                    boletin_api = territorial.get("meta", {}).get("boletin")
                    mesas_api   = territorial.get("meta", {}).get("mesas_reportadas")
                    st.success(f"✅ {len(cands_scraped)} candidatos · {n_deptos} departamentos · Boletín {boletin_api} · {mesas_api:.0f}% escrutado")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
                    import traceback
                    with st.expander("Detalles"): st.code(traceback.format_exc())

            if st.button("🗑️ Limpiar datos"):
                for k in ["datos_candidatos","datos_territoriales","carrusel_tarjetas","carrusel_boletin","carrusel_idx"]:
                    st.session_state.pop(k, None)
                st.rerun()

    with col_res_preview:
        candidatos_validos = [c for c in candidatos_data if c["nombre"].strip()]
        cands_render       = st.session_state.get("datos_candidatos", candidatos_validos)

        subtab_resultados, subtab_mapa = st.tabs(["📊 Tarjeta resultados", "🗺️ Mapa Colombia"])

        with subtab_resultados:
            if not cands_render:
                st.markdown("""<div class="ee-preview-empty"><div class="ee-preview-empty-icon">🗳️</div><div style="font-weight:600;margin-bottom:6px;">Vista previa de resultados</div><div style="font-size:0.9rem;">Configura los candidatos para generar.</div></div>""", unsafe_allow_html=True)
            else:
                try:
                    res_img = render_resultados_candidatos(candidatos=cands_render, format_key=res_format, boletin_text=boletin_text)
                    st.markdown('<div class="ee-preview-card">', unsafe_allow_html=True)
                    st.image(res_img)
                    st.markdown('</div>', unsafe_allow_html=True)
                    res_buf = BytesIO()
                    res_img.save(res_buf, format="PNG")
                    res_buf.seek(0)
                    st.download_button(label="⬇ Descargar tarjeta resultados", data=res_buf, file_name="resultados-" + boletin_text.lower().replace(" ","-") + ".png", mime="image/png", type="primary", key="res_download")
                except Exception as e:
                    st.error("Error al generar tarjeta: " + str(e))
                    import traceback
                    with st.expander("Detalles"): st.code(traceback.format_exc())

        with subtab_mapa:
            datos_territoriales = st.session_state.get("datos_territoriales")

            if not datos_territoriales:
                st.markdown("""<div class="ee-preview-empty"><div class="ee-preview-empty-icon">🗺️</div><div style="font-weight:600;margin-bottom:6px;">Carrusel de mapas electorales</div><div style="font-size:0.9rem;">Usá el botón <strong>🚀 Obtener resultados + datos para mapa</strong> en la columna izquierda.</div></div>""", unsafe_allow_html=True)
            else:
                deptos      = datos_territoriales.get("departamentos", [])
                meta        = datos_territoriales.get("meta", {})
                boletin_num = meta.get("boletin")
                mesas       = meta.get("mesas_reportadas")

                if not deptos:
                    st.warning("No hay datos por departamento. Intentá obtener resultados de nuevo.")
                else:
                    if boletin_num or mesas:
                        col_b1, col_b2 = st.columns(2)
                        with col_b1:
                            if boletin_num: st.metric("Boletín", f"N° {boletin_num}")
                        with col_b2:
                            if mesas: st.metric("Escrutado", f"{mesas:.1f}%")

                    boletin_label = f"Boletín {boletin_num}" if boletin_num else boletin_text

                    if "carrusel_tarjetas" not in st.session_state or st.session_state.get("carrusel_boletin") != boletin_num:
                        with st.spinner("Generando carrusel de mapas..."):
                            try:
                                tarjetas = render_carrusel_electoral(
                                    candidatos_globales=cands_render,
                                    departamentos=deptos,
                                    boletin_text=boletin_label,
                                    meta=meta,
                                )
                                st.session_state["carrusel_tarjetas"] = tarjetas
                                st.session_state["carrusel_boletin"]  = boletin_num
                                st.session_state["carrusel_idx"]      = 0
                            except Exception as e:
                                st.error(f"Error generando carrusel: {e}")
                                import traceback
                                with st.expander("Detalles"): st.code(traceback.format_exc())
                                st.stop()

                    tarjetas = st.session_state.get("carrusel_tarjetas", [])

                    if tarjetas:
                        TITULOS = [
                            "🗺️ Tarjeta 1 — Mapa segunda vuelta",
                            "📊 Tarjeta 2 — Resultados por departamento",
                        ]
                        NOMBRES_ARCHIVO = [
                            f"01-mapa-segunda-vuelta-{boletin_label.lower().replace(' ','-')}.png",
                            f"02-resultados-departamentos-{boletin_label.lower().replace(' ','-')}.png",
                        ]

                        if "carrusel_idx" not in st.session_state: st.session_state["carrusel_idx"] = 0
                        idx = st.session_state["carrusel_idx"]

                        puntos = "".join([f'<span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:{"#E31B23" if i==idx else "#D0D0D0"};margin:0 4px;"></span>' for i in range(len(tarjetas))])
                        st.markdown(puntos, unsafe_allow_html=True)
                        st.caption(TITULOS[idx])

                        st.markdown('<div class="ee-preview-card">', unsafe_allow_html=True)
                        st.image(tarjetas[idx])
                        st.markdown('</div>', unsafe_allow_html=True)

                        col_prev, col_dl, col_next = st.columns([1, 2, 1])
                        with col_prev:
                            if st.button("← Anterior", disabled=(idx==0), key="car_prev", use_container_width=True):
                                st.session_state["carrusel_idx"] -= 1; st.rerun()
                        with col_next:
                            if st.button("Siguiente →", disabled=(idx==len(tarjetas)-1), key="car_next", use_container_width=True):
                                st.session_state["carrusel_idx"] += 1; st.rerun()
                        with col_dl:
                            buf_single = BytesIO()
                            tarjetas[idx].save(buf_single, format="PNG")
                            buf_single.seek(0)
                            st.download_button(label="⬇ Descargar esta", data=buf_single, file_name=NOMBRES_ARCHIVO[idx], mime="image/png", type="primary", key=f"dl_single_{idx}", use_container_width=True)

                        st.markdown("---")

                        zip_bytes = carrusel_a_zip(tarjetas, boletin_label)
                        st.download_button(label="⬇ Descargar las 3 tarjetas en ZIP", data=zip_bytes, file_name=f"carrusel-electoral-{boletin_label.lower().replace(' ','-')}.zip", mime="application/zip", key="dl_zip_carrusel", use_container_width=True)

                        if st.button("🔄 Regenerar carrusel", key="regen_carrusel"):
                            for k in ["carrusel_tarjetas","carrusel_boletin","carrusel_idx"]: st.session_state.pop(k, None)
                            st.rerun()

                        with st.expander(f"📋 Ver {len(deptos)} departamentos", expanded=False):
                            for d in deptos:
                                p1 = d.get("primer_lugar", {})
                                p2 = d.get("segundo_lugar", {})
                                p1_txt = f"{p1.get('candidato','—')} {p1.get('porcentaje',0):.1f}%"
                                p2_txt = f"{p2.get('candidato','—')} {p2.get('porcentaje',0):.1f}%" if p2 else "—"
                                st.markdown(f"**{d.get('nombre','')}** — 1° {p1_txt} · 2° {p2_txt}")