"""
generator.py - Generador de tarjetas estilo El Espectador.

Soporta:
- Formato Post (1080x1350) y Story (1080x1920)
- 4 plantillas: "classic", "card", "with_cta", "attention" (portadas del v1)
- Múltiples fondos/degradados (de assets/fondos/)
- Stickers de sección con o sin icono (de assets/secciones/ o secciones-icono/)
- Logo EE oficial (blanco o negro)
- CTA "Lea la noticia completa en elespectador.com"
- Iconos de acciones IG (corazón, comentario, etc.)
- Ajuste de zoom y posición XY de la imagen
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from io import BytesIO
from PIL import Image
import requests
import re
import os
import unicodedata
import numpy as np
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# ============================================================
# CONSTANTES Y RUTAS
# ============================================================

FORMATS = {
    "post": {
        "name": "Post vertical clásico",
        "size": (1080, 1350),
        "description": "1080x1350 (4:5)",
    },
    "post_vertical_nuevo": {
        "name": "Post vertical nuevo",
        "size": (1080, 1440),
        "description": "1080x1440 (3:4)",
    },
    "post_cuadrado": {
        "name": "Post cuadrado",
        "size": (1080, 1080),
        "description": "1080x1080 (1:1)",
    },
    "post_horizontal": {
        "name": "Post horizontal",
        "size": (1080, 608),
        "description": "1080x608 (1.91:1)",
    },
    "story": {
        "name": "Stories (foto y video)",
        "size": (1080, 1920),
        "description": "1080x1920 (9:16)",
    },
    "stories_destacadas": {
        "name": "Portada Stories destacadas",
        "size": (640, 640),
        "description": "640x640 (1:1)",
    },
    "reels": {
        "name": "Reels",
        "size": (1080, 1920),
        "description": "1080x1920 (9:16)",

    },
    "portada_reel": {
        "name": "Portada Reel",
        "size": (420, 654),
        "description": "420x654 (1:1.55)",
    },
    "reels_ultra_ancho": {
        "name": "Reels ultra ancho",
        "size": (5120, 1080),
        "description": "5120x1080 (5:1)",
    },
}

# Familia de cada formato: cómo debe tratarse el layout
# "story" = layouts verticales tipo story/reels (alto >> ancho)
# "post"  = layouts tipo post (cuadrado o vertical moderado)
# "wide"  = layouts horizontales (ancho > alto)
FORMAT_FAMILY = {
    "post": "post",
    "post_vertical_nuevo": "post",
    "post_cuadrado": "post",
    "post_horizontal": "wide",
    "story": "story",
    "stories_destacadas": "post",
    "reels": "story",
    "portada_reel": "story",
    "reels_ultra_ancho": "wide",
}
DEFAULT_FORMAT = "post"


def format_family(format_key):
    """Devuelve la familia de layout para un format_key: 'post', 'story' o 'wide'."""
    return FORMAT_FAMILY.get(format_key, "post")

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
FONDOS_DIR = os.path.join(ASSETS_DIR, "fondos")
SECCIONES_DIR = os.path.join(ASSETS_DIR, "secciones")
SECCIONES_ICONO_DIR = os.path.join(ASSETS_DIR, "secciones-icono")
LOGOS_SECCIONES_DIR = os.path.join(ASSETS_DIR, "logos-secciones")
LOGOS_DIR = os.path.join(ASSETS_DIR, "logos")
GRAFICOS_DIR = os.path.join(ASSETS_DIR, "graficos")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")

# Rutas a Open Sans (para plantilla Columnista)
OPENSANS_REG_PATH = os.path.join(FONTS_DIR, "OpenSans-Regular.ttf")
OPENSANS_BOLD_PATH = os.path.join(FONTS_DIR, "OpenSans-Bold.ttf")
# Fuente LFT Etica para plantillas de elecciones
LFT_ETICA_REG_PATH = os.path.join(FONTS_DIR, "LFTEtica-Regular.ttf")
LFT_ETICA_BOLD_PATH = os.path.join(FONTS_DIR, "LFTEtica-Bold.ttf")
# Colores
RED = (227, 27, 35)
WHITE = (255, 255, 255)
BLACK = (15, 15, 15)
GRAY_BG = (235, 235, 235)
PURPLE = (66, 28, 87)


# ============================================================
# REGISTRO DE PLANTILLAS
# ============================================================
TEMPLATES = {
    "classic": {
        "name": "Clásica",
        "description": "Foto a sangre con gradiente oscuro, título blanco e iconos sociales",
        "category": "Clásicas",
    },
    "card": {
        "name": "Card",
        "description": "Foto enmarcada sobre fondo gris claro, título en negro",
        "category": "Clásicas",
    },
    "with_cta": {
        "name": "Con CTA",
        "description": "Como Clásica pero con 'Lea la noticia completa...'",
        "category": "Clásicas",
    },
    "lo_ultimo": {
        "name": "Lo Último",
        "description": "Foto a sangre + overlay lo-ultimo.png + título",
        "category": "Clásicas",
    },
    "atencion": {
        "name": "Atención",
        "description": "Foto a sangre + overlay atencion.png + título",
        "category": "Clásicas",
    },
    "en_vivo_simple": {
        "name": "En Vivo (simple)",
        "description": "Foto a sangre + overlay en-vivo.png + título",
        "category": "Clásicas",
    },

    "ultima_hora": {
        "name": "Última Hora",
        "description": "Foto a sangre + overlay ultima_hora.png + título",
        "category": "Clásicas",
    },


    "story_minimal": {
        "name": "Story Minimal",
        "description": "Foto a sangre + sticker arriba derecha + título sobre degradado negro abajo",
        "category": "Clásicas",
    },
    "echemos_cuentas": {
        "name": "Echemos Cuentas",
        "description": "Foto a sangre + logo grande arriba derecha + título en bloque claro/oscuro abajo",
        "category": "Clásicas",
    },
    "elecciones_2026_post": {
        "name": "Elecciones 2026 (Post)",
        "description": "Foto + overlay eleccionespost.png + título",
        "category": "Elecciones 2026",
    },
    "elecciones_2026_story": {
        "name": "Elecciones 2026 (Story)",
        "description": "Foto + overlay eleccionesstory.png + título",
        "category": "Elecciones 2026",
    },
    "elecciones_2026_ultima_hora_post": {
        "name": "Ultima Hora 2026 (Post)",
        "description": "Foto + overlay ultima-hora.png + título",
        "category": "Elecciones 2026",
    },
    "elecciones_2026_ultima_hora_story": {
        "name": "Ultima Hora 2026 (Story)",
        "description": "Foto + overlay ultima-hora.png + título",
        "category": "Elecciones 2026",
    },
    "envivo_elecciones_post": {
        "name": "En Vivo Elecciones (Post)",
        "description": "Foto + overlay envivoeleccionespost.png + título",
        "category": "Elecciones 2026",
    },
    "envivo_elecciones_story": {
        "name": "En Vivo Elecciones (Story)",
        "description": "Foto + overlay envivoeleccionesstory.png + título",
        "category": "Elecciones 2026",
    },   
    "en_vivo": {
        "name": "En Vivo (Story)",
        "description": "Story con overlay negro, sticker EN VIVO y título centrados en la mitad",
        "category": "Clásicas",
    },
    "columnista": {
        "name": "Columnista de hoy",
        "description": "Card blanca con foto circular del columnista, título, autor y resumen",
        "category": "Clásicas",

    
    },

    "elecciones_2026_card_post": {
        "name": "Elecciones 2026 Card (Post)",
        "description": "Foto enmarcada arriba + texto negro sin línea roja",
        "category": "Elecciones 2026",
    },
}

# ============================================================
# UTILIDADES
# ============================================================

def normalize_key(s):
    """Minúsculas, sin acentos, espacios/símbolos → guiones."""
    if not s:
        return ""
    s = s.lower().strip()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def find_in_dir(dir_path, key):
    """Busca un archivo PNG en un directorio que matchee la key normalizada."""
    if not key or not os.path.exists(dir_path):
        return None
    files = [f for f in os.listdir(dir_path) if f.lower().endswith(".png")]
    for f in files:
        if normalize_key(f[:-4]) == key:
            return os.path.join(dir_path, f)
    for f in files:
        name = normalize_key(f[:-4])
        if name.startswith(key + "-") or name.endswith("-" + key):
            return os.path.join(dir_path, f)
    return None


def list_fondos():
    """Devuelve lista de fondos disponibles."""
    if not os.path.exists(FONDOS_DIR):
        return []
    return sorted([f[:-4] for f in os.listdir(FONDOS_DIR) if f.lower().endswith(".png")])


SECTION_TO_FONDO = {
    "la-red-zoocial": "la-red-zoocial",
    "colombia-20": "colombia-20",
    "vea": "vea",
    "gastronomia": "gastronomia",
    "ultima-hora": "ultima-hora",
    "podcast": "podcast",
    "politica": "claro-oscuro",
    "judicial": "claro-oscuro",
    "investigacion": "claro-oscuro",
    "internacional": "claro-oscuro",
    "mundo": "claro-oscuro",
    "colombia": "claro-oscuro",
    "bogota": "claro-oscuro",
    "atencion": "ultima-hora",
    "lo-ultimo": "ultima-hora",
    "en-vivo": "ultima-hora",
    "en-directo": "ultima-hora",
    "deportes": "claro-oscuro",
    "economia": "echemos-cuentas",
    "el-magazin-cultural": "claro-oscuro",
    "entretenimiento": "claro-oscuro",
    "peliculas": "claro-oscuro",
    "series": "claro-oscuro",
    "vea-y-vea": "vea",
    "opinion": "gris-oscuro",
    "columna": "gris-oscuro",
    "entrevista": "claro-oscuro",
    "enfoque": "en-foco",
    "ambiente": "claro-oscuro",
    "ciencia": "claro-oscuro",
    "salud": "claro-oscuro",
    "tecnologia": "claro-oscuro",
    "educacion": "claro-oscuro",
    "genero": "impacto-mujer",
    "reportajes": "claro-oscuro",
    "turismo": "claro-oscuro",
    "autos": "claro-oscuro",
    "especial-ee": "claro-oscuro",
    "actualidad": "claro-oscuro",
}


def suggest_fondo_for_section(section_text):
    """Sugiere un fondo apropiado para la sección."""
    if not section_text:
        return "claro-oscuro"
    key = normalize_key(section_text)
    fondos_disponibles = set(list_fondos())
    if key in fondos_disponibles:
        return key
    if key in SECTION_TO_FONDO:
        candidate = SECTION_TO_FONDO[key]
        if candidate in fondos_disponibles:
            return candidate
    for fondo in fondos_disponibles:
        if fondo in key or key in fondo:
            return fondo
    if "claro-oscuro" in fondos_disponibles:
        return "claro-oscuro"
    if fondos_disponibles:
        return sorted(fondos_disponibles)[0]
    return None


def find_section_sticker(section_text, with_icon=False):
    """Busca el sticker de la sección (con o sin icono)."""
    key = normalize_key(section_text)
    if not key:
        return None
    folder = SECCIONES_ICONO_DIR if with_icon else SECCIONES_DIR
    return find_in_dir(folder, key)

def find_section_logo(section_text, color="blanco"):
    """Busca el logo de la sección dentro de assets/logos-secciones/.

    Estructura esperada:
        logos-secciones/
            Nombre Seccion/
                Logo Nombre Seccion blanco.png
                Logo Nombre Seccion negro.png

    Hace match difuso: la key normalizada de la sección debe coincidir
    con la subcarpeta, o estar contenida en ella (ej: 'las igualadas'
    matchea con la carpeta 'Las igualadas').

    color: 'blanco' o 'negro' — para elegir variante.
    Retorna None si no existe.
    """
    if not section_text or not os.path.exists(LOGOS_SECCIONES_DIR):
        return None

    key = normalize_key(section_text)
    if not key:
        return None

    # 1) Buscar subcarpeta que matchee con la sección
    matched_folder = None
    try:
        subdirs = [d for d in os.listdir(LOGOS_SECCIONES_DIR)
                   if os.path.isdir(os.path.join(LOGOS_SECCIONES_DIR, d))]
    except OSError:
        return None

    # Match exacto primero
    for d in subdirs:
        if normalize_key(d) == key:
            matched_folder = d
            break

    # Match parcial: la key está contenida en el nombre de la carpeta o viceversa
    if not matched_folder:
        for d in subdirs:
            d_norm = normalize_key(d)
            if key in d_norm or d_norm in key:
                matched_folder = d
                break

    if not matched_folder:
        return None

    folder_path = os.path.join(LOGOS_SECCIONES_DIR, matched_folder)
    files = [f for f in os.listdir(folder_path) if f.lower().endswith(".png")]
    if not files:
        return None

    # 2) Elegir el archivo según color (busca "blanco" o "negro" en el nombre)
    color_lower = color.lower()
    for f in files:
        if color_lower in f.lower():
            return os.path.join(folder_path, f)

    # Fallback: si no hay variante de color, devolver el primero
    return os.path.join(folder_path, files[0])


def list_section_logos():
    """Lista todas las subcarpetas/marcas disponibles en logos-secciones/.
    Retorna una lista de nombres de carpeta (ej: ['Bibo', 'Las igualadas', ...])."""
    if not os.path.exists(LOGOS_SECCIONES_DIR):
        return []
    subdirs = [
        d for d in os.listdir(LOGOS_SECCIONES_DIR)
        if os.path.isdir(os.path.join(LOGOS_SECCIONES_DIR, d))
        and not d.startswith(".")
    ]
    return sorted(subdirs)


def find_section_logo_by_name(folder_name, color="blanco"):
    """Busca el logo dentro de una subcarpeta específica de logos-secciones/.

    folder_name: nombre exacto de la subcarpeta (ej: 'Las igualadas')
    color: 'blanco' o 'negro'
    """
    if not folder_name:
        return None
    folder_path = os.path.join(LOGOS_SECCIONES_DIR, folder_name)
    if not os.path.isdir(folder_path):
        return None

    files = [f for f in os.listdir(folder_path) if f.lower().endswith(".png")]
    if not files:
        return None

    color_lower = color.lower()
    for f in files:
        if color_lower in f.lower():
            return os.path.join(folder_path, f)

    return os.path.join(folder_path, files[0])


def list_logo_variants(folder_name):
    """Lista las variantes de color disponibles para un logo específico.

    Retorna una lista de tuplas (variant_label, filename) ordenadas:
    [('blanco', 'Logo Bibo blanco.png'), ('negro', 'Logo Bibo negro.png'), ...]

    El label es la palabra que diferencia las variantes (blanco, negro, azul, etc.).
    Si no se puede detectar, usa el nombre del archivo sin extension.
    """
    if not folder_name:
        return []
    folder_path = os.path.join(LOGOS_SECCIONES_DIR, folder_name)
    if not os.path.isdir(folder_path):
        return []

    files = sorted([f for f in os.listdir(folder_path) if f.lower().endswith(".png")])
    if not files:
        return []

    # Palabras clave conocidas que identifican variantes
    color_keywords = [
        "blanco", "negro", "gris", "azul", "fucsia", "morado",
        "amarillo", "rojo", "verde", "naranja", "rosado", "rosa",
        "turismo", "moda", "amor", "autos", "gastronomia", "gastronomía",
        "tecnologia", "tecnología", "huerta", "zoocial",
    ]

    variants = []
    for f in files:
        name_no_ext = f[:-4]
        name_lower = name_no_ext.lower()

        # Buscar keyword conocida
        label = None
        for kw in color_keywords:
            if kw in name_lower:
                label = kw
                break

        # Si no hay keyword, usar el nombre completo del archivo sin la palabra "Logo"
        if not label:
            cleaned = name_no_ext
            for prefix in ["Logo ", "logo "]:
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix):]
            # Quitar el nombre de la marca para que quede solo la variante
            folder_norm = normalize_key(folder_name)
            cleaned_norm = normalize_key(cleaned)
            if cleaned_norm.startswith(folder_norm):
                cleaned = cleaned[len(folder_name):].strip()
            label = cleaned or name_no_ext

        variants.append((label, f))

    return variants


def find_section_logo_by_file(folder_name, filename):
    """Devuelve la ruta absoluta a un archivo específico dentro de una subcarpeta."""
    if not folder_name or not filename:
        return None
    full_path = os.path.join(LOGOS_SECCIONES_DIR, folder_name, filename)
    if os.path.isfile(full_path):
        return full_path
    return None
    
def find_fondo(fondo_name):
    """Busca el fondo por nombre."""
    if not fondo_name:
        return None
    return find_in_dir(FONDOS_DIR, normalize_key(fondo_name))


def load_font(size, bold=True, font_path=None, font_family="abril"):
    """Carga fuente especificada o del proyecto con fallbacks.

    Args:
        size: tamaño en pixels
        bold: si es True usa variante bold (solo aplica a opensans)
        font_path: ruta personalizada (override total)
        font_family: 'abril' (default, para titulares de tarjetas) o
                     'opensans' (para columnistas y textos secundarios)
    """
    # 1) Override explicito por ruta
    if font_path and os.path.exists(font_path):
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass

    # 2) Mapa de familias -> archivo dentro de assets/fonts/
    family_files = {
        "abril": ["abriltitling.ttf"],
        "opensans": (
            ["OpenSans-Bold.ttf", "OpenSans-Regular.ttf"]
            if bold else
            ["OpenSans-Regular.ttf", "OpenSans-Bold.ttf"]
        ),
    }

    target_files = family_files.get(font_family, family_files["abril"])

    # 3) Intentar cargar en orden de preferencia
    if os.path.exists(FONTS_DIR):
        for filename in target_files:
            fpath = os.path.join(FONTS_DIR, filename)
            if os.path.exists(fpath):
                try:
                    return ImageFont.truetype(fpath, size)
                except Exception:
                    pass

    # 4) Fallback a fuentes del sistema
    candidates_bold = [
        "C:/Windows/Fonts/georgiab.ttf", "C:/Windows/Fonts/arialbd.ttf",
        "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    ]
    candidates_reg = [
        "C:/Windows/Fonts/georgia.ttf", "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    ]
    for path in (candidates_bold if bold else candidates_reg):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def trim_transparent(img):
    bbox = img.getbbox()
    return img.crop(bbox) if bbox else img


def upscale_image_url(url):
    """Genera URLs candidatas de mayor calidad."""
    candidates = []
    if "/resizer/" in url:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        hd = {**{k: v[0] for k, v in params.items()}, "width": "2400", "quality": "95", "smart": "true"}
        hd.pop("height", None)
        candidates.append(urlunparse(parsed._replace(query=urlencode(hd))))
        md = {**hd, "width": "1600"}
        candidates.append(urlunparse(parsed._replace(query=urlencode(md))))
    elif "/image/upload/" in url and "cloudinary" in url:
        candidates.append(re.sub(r"/image/upload/[^/]*?/", "/image/upload/w_2400,q_95,c_fill/", url, count=1))
    elif "wp-content/uploads" in url:
        orig = re.sub(r"-\d+x\d+(\.[a-z]+)$", r"\1", url)
        if orig != url:
            candidates.append(orig)
    parsed = urlparse(url)
    if parsed.query:
        params = parse_qs(parsed.query)
        new_params = {k: v[0] for k, v in params.items()}
        modified = False
        for key in ("width", "w", "size"):
            if key in new_params:
                try:
                    if int(new_params[key]) < 2000:
                        new_params[key] = "2400"
                        modified = True
                except ValueError:
                    pass
        for key in ("quality", "q"):
            if key in new_params:
                try:
                    if int(new_params[key]) < 90:
                        new_params[key] = "95"
                        modified = True
                except ValueError:
                    pass
        for key in ("height", "h"):
            if key in new_params:
                new_params.pop(key)
                modified = True
        if modified:
            new_url = urlunparse(parsed._replace(query=urlencode(new_params)))
            if new_url not in candidates:
                candidates.append(new_url)
    candidates.append(url)
    return candidates


def fetch_image(url):
    """Descarga imagen con mejor calidad disponible."""
    candidates = upscale_image_url(url)
    last_err = None
    for u in candidates:
        try:
            r = requests.get(u, timeout=30, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0)"})
            if r.status_code == 200 and len(r.content) > 1000:
                img = Image.open(BytesIO(r.content)).convert("RGB")
                if img.width >= 400 and img.height >= 400:
                    return img
        except Exception as e:
            last_err = e
    if last_err:
        raise last_err
    raise Exception("No se pudo descargar la imagen")


def cover_resize(img, target_size, zoom=1.0, offset_x=0.5, offset_y=0.5):
    """Cover resize con zoom y offsets."""
    tw, th = target_size
    iw, ih = img.size
    cover_scale = max(tw / iw, th / ih)
    final_scale = cover_scale * max(zoom, 1.0)
    nw, nh = int(iw * final_scale), int(ih * final_scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    max_left, max_top = nw - tw, nh - th
    left = max(0, min(int(max_left * offset_x), max_left))
    top = max(0, min(int(max_top * offset_y), max_top))
    return img.crop((left, top, left + tw, top + th))


def paste_asset(canvas, asset_path, target_height=None, target_width=None,
                position=(0, 0), anchor="top-left"):
    """Pega un PNG con transparencia."""
    if not asset_path or not os.path.exists(asset_path):
        return canvas
    asset = Image.open(asset_path).convert("RGBA")
    asset = trim_transparent(asset)
    if target_height:
        ratio = target_height / asset.height
        new_w = int(asset.width * ratio)
        asset = asset.resize((new_w, target_height), Image.LANCZOS)
    elif target_width:
        ratio = target_width / asset.width
        new_h = int(asset.height * ratio)
        asset = asset.resize((target_width, new_h), Image.LANCZOS)
    aw, ah = asset.size
    x, y = position
    if anchor == "top-left":
        px, py = x, y
    elif anchor == "top-right":
        px, py = x - aw, y
    elif anchor == "bottom-left":
        px, py = x, y - ah
    elif anchor == "bottom-right":
        px, py = x - aw, y - ah
    elif anchor == "center":
        px, py = x - aw // 2, y - ah // 2
    else:
        px, py = x, y
    rgba = canvas.convert("RGBA")
    rgba.paste(asset, (int(px), int(py)), asset)
    return rgba.convert("RGB")


def wrap_text(text, font, max_width, draw):
    words = text.split()
    lines, current = [], []
    for w in words:
        test = " ".join(current + [w])
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current.append(w)
        else:
            if current:
                lines.append(" ".join(current))
            current = [w]
    if current:
        lines.append(" ".join(current))
    return lines


def fit_title_font(draw, title, max_width, max_lines,
                   size_start=58, size_min=36, size_step=2, bold=True, font_path=None,
                   size_multiplier=1.0):
    """Ajusta fuente para que el título quepa en max_lines.

    size_multiplier: factor para escalar size_start y size_min.
                     1.0 = normal, 0.8 = chico, 1.2 = grande, etc.
    """
    size_start = int(size_start * size_multiplier)
    size_min   = int(size_min   * size_multiplier)

    # Asegurar que size_min no sea mayor que size_start
    if size_min > size_start:
        size_min = size_start

    for size in range(size_start, size_min - 1, -size_step):
        font = load_font(size, bold=bold, font_path=font_path)
        lines = wrap_text(title, font, max_width, draw)
        if len(lines) <= max_lines:
            return font, lines
    font = load_font(size_min, bold=bold, font_path=font_path)
    lines = wrap_text(title, font, max_width, draw)[:max_lines]
    if lines and not lines[-1].endswith("..."):
        lines[-1] = lines[-1].rsplit(" ", 1)[0] + "..."
    return font, lines


def draw_text_lines(draw, lines, font, x, y, color, line_spacing=1.25):
    lh_bbox = draw.textbbox((0, 0), "Ag", font=font)
    lh = (lh_bbox[3] - lh_bbox[1]) * line_spacing
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        ly = int(y + i * lh - bbox[1])
        draw.text((x, ly), line, font=font, fill=color)
    return int(lh * len(lines))


def add_dark_gradient(img, top_frac=0.55, bottom_frac=0.82, max_alpha=200):
    """Gradiente oscuro concentrado en área del título."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = img.size
    top = int(h * top_frac)
    bottom = int(h * bottom_frac)
    for y in range(top, bottom):
        alpha = int(max_alpha * ((y - top) / (bottom - top)) ** 1.2)
        draw.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
    for y in range(bottom, h):
        draw.line([(0, y), (w, y)], fill=(0, 0, 0, max_alpha))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def draw_section_badge(canvas, section_text, position, font, with_icon=False):
    """
    Dibuja el sticker/badge de sección.

    Busca primero en assets/secciones-icono/ o assets/secciones/ según with_icon.
    Si no encuentra el PNG, dibuja un badge básico con fondo rojo.

    Returns: (canvas, badge_width, badge_height)
    """
    x, y = position
    sticker_path = find_section_sticker(section_text, with_icon=with_icon)

    if sticker_path:
        sticker = Image.open(sticker_path).convert("RGBA")
        sticker = trim_transparent(sticker)
        target_h = int(font.size * 1.3)
        ratio = target_h / sticker.height
        new_w = int(sticker.width * ratio)
        sticker = sticker.resize((new_w, target_h), Image.LANCZOS)
        canvas_rgba = canvas.convert("RGBA")
        canvas_rgba.paste(sticker, (int(x), int(y)), sticker)
        return canvas_rgba.convert("RGB"), new_w, target_h

    # Fallback: badge básico con fondo rojo. Usar LFT Etica Regular si está disponible.
    fallback_font = font
    if os.path.exists(LFT_ETICA_REG_PATH):
        try:
            fallback_font = ImageFont.truetype(LFT_ETICA_REG_PATH, font.size)
        except Exception:
            fallback_font = font
    elif os.path.exists(LFT_ETICA_BOLD_PATH):
        try:
            fallback_font = ImageFont.truetype(LFT_ETICA_BOLD_PATH, font.size)
        except Exception:
            fallback_font = font

    draw = ImageDraw.Draw(canvas)
    text = (section_text or "").upper()
    bbox = draw.textbbox((0, 0), text, font=fallback_font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    pad_x, pad_y = 22, 14
    badge_w = text_w + pad_x * 2
    badge_h = text_h + pad_y * 2
    draw.rounded_rectangle([x, y, x + badge_w, y + badge_h], radius=int(badge_h * 0.35), fill=RED)
    draw.text((x + pad_x, y + pad_y - bbox[1]), text, font=fallback_font, fill=WHITE)
    return canvas, badge_w, badge_h


def _logo_path(color="blanco"):
    """Resuelve la ruta del logo EE según color ('blanco' o 'negro')."""
    return os.path.join(LOGOS_DIR, f"ee-{color}.png")


def _social_icons_path(color="blanco"):
    """Resuelve la ruta de los iconos de acciones IG según color."""
    return os.path.join(GRAFICOS_DIR, f"acciones-ig-{color}.png")


def _cta_path(color="blanco"):
    """Resuelve la ruta del CTA PNG según color."""
    return os.path.join(GRAFICOS_DIR, f"cta-{color}.png")


def draw_cta_inline(draw, position, font, canvas_size):
    """
    Dibuja el CTA '→ Lea la noticia completa en elespectador.com' usando texto
    cuando no existe el PNG de CTA. Retorna (width, height).
    """
    x, y = position
    text_normal = "Lea la noticia completa en "
    text_bold = "elespectador.com"

    bbox_n = draw.textbbox((0, 0), text_normal, font=font)
    text_w_n = bbox_n[2] - bbox_n[0]
    text_h = bbox_n[3] - bbox_n[1]

    bold_font = load_font(font.size, bold=True)
    bbox_b = draw.textbbox((0, 0), text_bold, font=bold_font)
    text_w_b = bbox_b[2] - bbox_b[0]

    arrow_w = 30
    arrow_gap = 14
    pad_x, pad_y = 18, 12

    total_text_w = arrow_w + arrow_gap + text_w_n + text_w_b
    box_w = total_text_w + pad_x * 2
    box_h = text_h + pad_y * 2

    try:
        draw.rounded_rectangle(
            [x, y, x + box_w, y + box_h],
            radius=6,
            outline=RED, width=3, fill=WHITE,
        )
    except AttributeError:
        draw.rectangle([x, y, x + box_w, y + box_h], outline=RED, width=3, fill=WHITE)

    # Flecha roja
    arrow_x = x + pad_x
    arrow_y = y + box_h // 2
    draw.line([(arrow_x, arrow_y), (arrow_x + arrow_w - 6, arrow_y)], fill=RED, width=3)
    arrow_tip = [
        (arrow_x + arrow_w - 6, arrow_y),
        (arrow_x + arrow_w - 14, arrow_y - 7),
        (arrow_x + arrow_w - 14, arrow_y + 7),
    ]
    draw.polygon(arrow_tip, fill=RED)

    # Texto
    text_x = arrow_x + arrow_w + arrow_gap
    text_y = y + pad_y - bbox_n[1]
    draw.text((text_x, text_y), text_normal, font=font, fill=BLACK)
    draw.text((text_x + text_w_n, text_y), text_bold, font=bold_font, fill=BLACK)

    return box_w, box_h


def _paste_cta(canvas, margin_x, footer_y, canvas_w, text_color, draw_fallback=None):
    """
    Intenta pegar el CTA PNG. Si no existe, usa draw_fallback (draw objeto) para
    dibujar el CTA inline. Si draw_fallback es None, omite el CTA sin imagen.
    """
    color = "blanco" if text_color == WHITE else "negro"
    cta_file = _cta_path(color)
    if os.path.exists(cta_file):
        cta_w = int(canvas_w * 0.65)
        canvas = paste_asset(
            canvas, cta_file,
            target_width=cta_w,
            position=(margin_x, footer_y),
            anchor="bottom-left",
        )
    elif draw_fallback is not None:
        cta_font = load_font(22, bold=False)
        draw_cta_inline(draw_fallback, (margin_x, footer_y - 60), cta_font, (canvas_w, footer_y))
    return canvas


def _paste_logo(canvas, canvas_w, footer_y, canvas_h, text_color):
    """Pega el logo EE en la esquina inferior derecha."""
    color = "blanco" if text_color == WHITE else "negro"
    logo_file = _logo_path(color)
    logo_h = int(canvas_h * 0.06)
    margin_x = int(canvas_w * 0.06)
    return paste_asset(
        canvas, logo_file,
        target_height=logo_h,
        position=(canvas_w - margin_x, footer_y),
        anchor="bottom-right",
    )


def _paste_social_icons(canvas, margin_x, footer_y, canvas_h, text_color):
    """Pega los iconos de acciones IG en la esquina inferior izquierda."""
    color = "blanco" if text_color == WHITE else "negro"
    icons_file = _social_icons_path(color)
    icons_h = int(canvas_h * 0.04)
    return paste_asset(
        canvas, icons_file,
        target_height=icons_h,
        position=(margin_x, footer_y),
        anchor="bottom-left",
    )

def _paste_section_logo(canvas, section, canvas_w, canvas_h,
                        position="top-right", logo_override=None,
                        logo_variant=None):
    """Pega el logo de sección si existe.

    position: 'top-right' para POSTs, 'top-left' para STORIES.
    logo_override: si se pasa, fuerza usar esa subcarpeta de logos-secciones/.
    logo_variant: nombre del archivo PNG dentro de la subcarpeta a usar
                  (ej: 'Logo Bibo negro.png'). Si no se pasa, usa la variante
                  blanca por defecto.
    """
    if logo_override and logo_variant:
        # Archivo específico elegido por el usuario
        logo_path = find_section_logo_by_file(logo_override, logo_variant)
    elif logo_override:
        # Solo carpeta, sin variante → blanco por defecto
        logo_path = find_section_logo_by_name(logo_override)
    elif logo_variant:
        # Automático pero con variante específica elegida
        # Detectar la carpeta automáticamente y aplicar la variante elegida
        auto_path = find_section_logo(section)
        if auto_path:
            import os as _os_logo
            auto_folder = _os_logo.path.basename(_os_logo.path.dirname(auto_path))
            logo_path = find_section_logo_by_file(auto_folder, logo_variant)
        else:
            logo_path = None
    else:
        # Modo automático sin variante: detección por sección, variante blanco
        logo_path = find_section_logo(section)

    if not logo_path:
        return canvas

    margin_x = int(canvas_w * 0.06)
    margin_y = int(canvas_h * 0.045)
    # Altura del logo: ~6% del canvas (similar al sticker, pero un poco mayor)
    logo_h = int(canvas_h * 0.06)

    if position == "top-right":
        x, y = canvas_w - margin_x, margin_y
        anchor = "top-right"
    else:  # top-left
        x, y = margin_x, margin_y
        anchor = "top-left"

    return paste_asset(
        canvas, logo_path,
        target_height=logo_h,
        position=(x, y),
        anchor=anchor,
    )


# ============================================================
# HELPERS PARA PLANTILLA COLUMNISTA
# ============================================================

def make_circle_avatar(img, size, bg_color=RED):
    """Devuelve un Image RGBA cuadrado con la foto recortada en círculo,
    sobre un fondo de color sólido (típicamente rojo)."""
    if img is None:
        # Solo círculo rojo sin foto
        result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(result)
        draw.ellipse([0, 0, size, size], fill=bg_color + (255,))
        return result

    # Cuadrado de fondo rojo
    bg = Image.new("RGBA", (size, size), bg_color + (255,))

    # La foto se ajusta a un círculo ligeramente menor para que se vea borde rojo
    photo_size = int(size * 0.92)
    photo = cover_resize(img, (photo_size, photo_size), zoom=1.0, offset_x=0.5, offset_y=0.4)
    photo = photo.convert("RGBA")

    # Máscara circular para la foto
    mask = Image.new("L", (photo_size, photo_size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse([0, 0, photo_size, photo_size], fill=255)

    # Pegar la foto en el centro del círculo rojo
    offset = (size - photo_size) // 2
    bg.paste(photo, (offset, offset), mask)

    # Máscara circular para el fondo (recortar todo el cuadrado)
    final_mask = Image.new("L", (size, size), 0)
    fm_draw = ImageDraw.Draw(final_mask)
    fm_draw.ellipse([0, 0, size, size], fill=255)
    bg.putalpha(final_mask)

    return bg


def draw_card_with_shadow(canvas, box, radius=30, shadow_offset=(0, 8),
                          shadow_blur=20, shadow_alpha=60):
    """Dibuja una card blanca con esquinas redondeadas y sombra suave.
    box: (x0, y0, x1, y1). Devuelve el canvas modificado."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0

    # Capa de sombra
    pad = shadow_blur * 2
    shadow_layer = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow_layer)
    sd.rounded_rectangle(
        [pad, pad, pad + w, pad + h],
        radius=radius, fill=(0, 0, 0, shadow_alpha),
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(shadow_blur))

    canvas_rgba = canvas.convert("RGBA")
    canvas_rgba.alpha_composite(
        shadow_layer,
        (x0 - pad + shadow_offset[0], y0 - pad + shadow_offset[1]),
    )

    # Card blanca encima
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    cd.rounded_rectangle([0, 0, w, h], radius=radius, fill=(255, 255, 255, 255))
    canvas_rgba.alpha_composite(card, (x0, y0))

    return canvas_rgba.convert("RGB")


def wrap_text_lines(text, font, max_width, draw, max_lines=None):
    """Envuelve texto en líneas que quepan en max_width. Si supera max_lines, agrega '...'."""
    if not text:
        return []
    words = text.split()
    lines = []
    current = ""
    for w in words:
        candidate = (current + " " + w).strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        # Agregar elipsis a la última línea
        last = lines[-1]
        while last:
            bbox = draw.textbbox((0, 0), last + "...", font=font)
            if bbox[2] - bbox[0] <= max_width:
                lines[-1] = last + "..."
                break
            last = last.rsplit(" ", 1)[0] if " " in last else ""
    return lines


# ============================================================
# PLANTILLA 1: CLASSIC
# Foto sangrada + gradiente oscuro + título blanco + iconos sociales + logo EE
# ============================================================


def render_classic(source_image, section, title,
                   format_key="post", seccion_con_icono=False,
                   zoom=1.0, offset_x=0.5, offset_y=0.5, font_path=None,
                   logo_override=None, logo_variant=None,title_size_multiplier=1.0):
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    margin_x = int(canvas_w * 0.06)

    img = cover_resize(source_image, (canvas_w, canvas_h), zoom, offset_x, offset_y)
    img = add_dark_gradient(img, top_frac=0.55, bottom_frac=0.82)

    draw = ImageDraw.Draw(img)
    badge_font = load_font(30, bold=True, font_path=font_path)
    img, _, _ = draw_section_badge(img, section.upper(), (margin_x, int(canvas_h * 0.045)), badge_font, seccion_con_icono)
    draw = ImageDraw.Draw(img)

    max_w = canvas_w - margin_x * 2 - 6 - 20 - 60
    title_font, lines = fit_title_font(draw, title, max_w, max_lines=4, font_path=font_path,
                                       size_multiplier=title_size_multiplier)

    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))
    y_start = canvas_h - int(canvas_h * 0.163) - total_h

    draw.rectangle([margin_x, y_start, margin_x + 6, y_start + total_h], fill=RED)
    draw_text_lines(draw, lines, title_font, margin_x + 26, y_start, WHITE)

    footer_y = canvas_h - int(canvas_h * 0.044)
    img = _paste_social_icons(img, margin_x, footer_y, canvas_h, WHITE)
    img = _paste_logo(img, canvas_w, footer_y, canvas_h, WHITE)

    
    # Logo de sección: top-right para POST y STORY
    logo_pos = "top-right"
    img = _paste_section_logo(img, section, canvas_w, canvas_h,
                              position=logo_pos, logo_override=logo_override,
                              logo_variant=logo_variant)  

    return img


# ============================================================
# PLANTILLA 2: CARD
# Fondo gris + foto enmarcada + título en negro + logo EE oscuro
# ============================================================

def render_card(source_image, section, title,
                format_key="post", seccion_con_icono=False,
                zoom=1.0, offset_x=0.5, offset_y=0.5, font_path=None,title_size_multiplier=1.0):
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    margin_x = int(canvas_w * 0.06)

    canvas = Image.new("RGB", (canvas_w, canvas_h), GRAY_BG)

    draw = ImageDraw.Draw(canvas)
    badge_font = load_font(28, bold=True, font_path=font_path)
    canvas, _, _ = draw_section_badge(canvas, section.upper(), (margin_x, int(canvas_h * 0.045)), badge_font, seccion_con_icono)
    draw = ImageDraw.Draw(canvas)

    # Foto enmarcada
    photo_top = int(canvas_h * 0.104)
    photo_left = margin_x
    photo_right = canvas_w - margin_x
    photo_bottom = int(canvas_h * 0.607)
    photo_w = photo_right - photo_left
    photo_h = photo_bottom - photo_top

    photo = cover_resize(source_image, (photo_w, photo_h), zoom, offset_x, offset_y)
    canvas.paste(photo, (photo_left, photo_top))

    # Título en negro debajo de la foto
    title_max_w = canvas_w - margin_x * 2 - 6 - 20 - 60
    title_font, lines = fit_title_font(
        draw, title, max_width=title_max_w,
        max_lines=3 if format_key == "post" else 4,
        size_start=56, size_min=42, font_path=font_path,
        size_multiplier=title_size_multiplier,
    )

    line_y_start = photo_bottom + int(canvas_h * 0.037)
    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))

    draw.rectangle([margin_x, line_y_start, margin_x + 6, line_y_start + total_h], fill=RED)
    draw_text_lines(draw, lines, title_font, margin_x + 26, line_y_start, BLACK)

    # Iconos sociales y logo en negro (fondo claro)
    footer_y = canvas_h - int(canvas_h * 0.044)
    canvas = _paste_social_icons(canvas, margin_x, footer_y, canvas_h, BLACK)
    canvas = _paste_logo(canvas, canvas_w, footer_y, canvas_h, BLACK)

    return canvas


# ============================================================
# PLANTILLA 3: WITH_CTA
# Como classic + CTA "Lea la noticia completa..." en footer
# ============================================================

def render_with_cta(source_image, section, title,
                    format_key="post", seccion_con_icono=False,
                    zoom=1.0, offset_x=0.5, offset_y=0.5, font_path=None,title_size_multiplier=1.0):
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    margin_x = int(canvas_w * 0.06)

    img = cover_resize(source_image, (canvas_w, canvas_h), zoom, offset_x, offset_y)
    img = add_dark_gradient(img, top_frac=0.50, bottom_frac=0.80, max_alpha=210)

    draw = ImageDraw.Draw(img)
    badge_font = load_font(30, bold=True, font_path=font_path)
    img, _, _ = draw_section_badge(img, section.upper(), (margin_x, int(canvas_h * 0.045)), badge_font, seccion_con_icono)
    draw = ImageDraw.Draw(img)

    max_w = canvas_w - margin_x * 2 - 6 - 20 - 60
    title_font, lines = fit_title_font(draw, title, max_w, max_lines=3, size_start=54, font_path=font_path)

    # Reservar espacio para CTA + logo debajo del título
    cta_reserved = int(canvas_h * 0.148)
    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))
    y_start = canvas_h - cta_reserved - total_h - int(canvas_h * 0.022)

    draw.rectangle([margin_x, y_start, margin_x + 6, y_start + total_h], fill=RED)
    draw_text_lines(draw, lines, title_font, margin_x + 26, y_start, WHITE)

    # Footer: CTA izquierda + logo derecha
    footer_y = canvas_h - int(canvas_h * 0.044)
    draw = ImageDraw.Draw(img)  # re-crear draw si paste_asset convirtió a RGB
    img = _paste_cta(img, margin_x, footer_y, canvas_w, WHITE, draw_fallback=draw)
    img = _paste_logo(img, canvas_w, footer_y, canvas_h, WHITE)
    logo_pos = "top-right"
    img = _paste_section_logo(img, section, canvas_w, canvas_h, position=logo_pos)

    return img


# ============================================================
# PLANTILLA 4: ATTENTION
# Foto arriba + bloque morado sólido abajo + título blanco + CTA
# ============================================================

def render_attention(source_image, section, title,
                     format_key="post", seccion_con_icono=False,
                     zoom=1.0, offset_x=0.5, offset_y=0.5, font_path=None, title_size_multiplier=1.0):
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    margin_x = int(canvas_w * 0.06)

    # Foto cubre todo el canvas al fondo
    photo_full = cover_resize(source_image, (canvas_w, canvas_h), zoom, offset_x, offset_y)
    canvas = photo_full.convert("RGBA")

    # Bloque morado con degradado (transición foto → morado)
    photo_h = int(canvas_h * 0.62)
    block_height = canvas_h - photo_h
    transition_height = int(block_height * 0.40)

    overlay = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)

    for i in range(transition_height):
        progress = i / transition_height
        alpha = int(255 * (progress ** 0.85))
        y = photo_h + i
        draw_overlay.line([(0, y), (canvas_w, y)],
                          fill=(PURPLE[0], PURPLE[1], PURPLE[2], alpha))

    draw_overlay.rectangle(
        [0, photo_h + transition_height, canvas_w, canvas_h],
        fill=(PURPLE[0], PURPLE[1], PURPLE[2], 255)
    )

    canvas = Image.alpha_composite(canvas, overlay).convert("RGB")

    # Badge de sección sobre el bloque morado
    badge_y = photo_h + int(block_height * 0.06)
    badge_font = load_font(30, bold=True, font_path=font_path)
    canvas, _, _ = draw_section_badge(canvas, section.upper(), (margin_x, badge_y), badge_font, seccion_con_icono)
    draw = ImageDraw.Draw(canvas)

    # Título blanco
    max_w = canvas_w - margin_x * 2 - 6 - 20 - 60
    title_font, lines = fit_title_font(draw, title, max_w, max_lines=3, size_start=50, font_path=font_path)

    title_y = badge_y + int(block_height * 0.18)
    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))

    draw.rectangle([margin_x, title_y, margin_x + 6, title_y + total_h], fill=WHITE)
    draw_text_lines(draw, lines, title_font, margin_x + 26, title_y, WHITE)

    # Footer: CTA izquierda + logo derecha
    footer_y = canvas_h - int(canvas_h * 0.044)
    draw = ImageDraw.Draw(canvas)
    canvas = _paste_cta(canvas, margin_x, footer_y, canvas_w, WHITE, draw_fallback=draw)
    canvas = _paste_logo(canvas, canvas_w, footer_y, canvas_h, WHITE)

    return canvas

# ============================================================
# PLANTILLA 5: STORY MINIMAL
# Foto a sangre + sticker arriba derecha + degradado negro abajo con título
# ============================================================

def render_story_minimal(source_image, section, title,
                         format_key="story", seccion_con_icono=True,
                         zoom=1.0, offset_x=0.5, offset_y=0.5, font_path=None, title_size_multiplier=1.0,
                         logo_override=None, logo_variant=None):
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    # Márgenes laterales más amplios para Story (8% en lugar de 6%)
    margin_x = int(canvas_w * 0.08)

    # Zonas seguras de Instagram Story (top ~13%, bottom ~22%)
    # El título debe quedar por encima de la zona inferior de interacción
    safe_bottom_frac = 0.28      # el título termina arriba del 72% de altura
    safe_top_frac = 0.08         # el sticker baja un poco del borde superior

    # Foto a sangre
    img = cover_resize(source_image, (canvas_w, canvas_h), zoom, offset_x, offset_y)

    # Degradado negro centrado en la zona del título (mitad inferior)
    img = add_dark_gradient(img, top_frac=0.45, bottom_frac=0.78, max_alpha=220)

    # Sticker de sección arriba a la DERECHA, dentro de zona segura
    draw = ImageDraw.Draw(img)
    badge_font = load_font(30, bold=True, font_path=font_path)
    sticker_path = find_section_sticker(section.upper(), with_icon=seccion_con_icono)
    if sticker_path:
        sticker = Image.open(sticker_path).convert("RGBA")
        sticker = trim_transparent(sticker)
        target_h = int(badge_font.size * 1.4)
        ratio = target_h / sticker.height
        new_w = int(sticker.width * ratio)
        sticker = sticker.resize((new_w, target_h), Image.LANCZOS)
        sticker_x = canvas_w - margin_x - new_w
        sticker_y = int(canvas_h * safe_top_frac)
        canvas_rgba = img.convert("RGBA")
        canvas_rgba.paste(sticker, (sticker_x, sticker_y), sticker)
        img = canvas_rgba.convert("RGB")
    else:
        # Texto fallback usando LFT Etica Regular si existe
        fallback_font = badge_font
        if os.path.exists(LFT_ETICA_REG_PATH):
            try:
                fallback_font = ImageFont.truetype(LFT_ETICA_REG_PATH, badge_font.size)
            except Exception:
                pass
        elif os.path.exists(LFT_ETICA_BOLD_PATH):
            try:
                fallback_font = ImageFont.truetype(LFT_ETICA_BOLD_PATH, badge_font.size)
            except Exception:
                pass

        text = (section or "").upper()
        bbox = draw.textbbox((0, 0), text, font=fallback_font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        pad_x, pad_y = 22, 14
        badge_w = text_w + pad_x * 2
        badge_h = text_h + pad_y * 2
        sticker_x = canvas_w - margin_x - badge_w
        sticker_y = int(canvas_h * safe_top_frac)
        draw.rounded_rectangle([sticker_x, sticker_y, sticker_x + badge_w, sticker_y + badge_h], radius=int(badge_h * 0.35), fill=RED)
        draw.text((sticker_x + pad_x, sticker_y + pad_y - bbox[1]), text, font=fallback_font, fill=WHITE)

    # Título con línea roja a la izquierda, ubicado arriba del centro inferior
    draw = ImageDraw.Draw(img)
    # Ancho disponible considerando la línea roja (6px) + separación (20px)
    max_w = canvas_w - margin_x * 2 - 6 - 20
    title_font, lines = fit_title_font(draw, title, max_w, max_lines=5, font_path=font_path)

    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))
    # El título termina ANTES de la zona segura inferior de Instagram
    y_start = canvas_h - int(canvas_h * safe_bottom_frac) - total_h

    # Línea roja vertical a la izquierda del título
    # Línea roja vertical a la izquierda del título
    draw.rectangle([margin_x, y_start, margin_x + 6, y_start + total_h], fill=RED)
    # Texto del título a la derecha de la línea roja
    draw_text_lines(draw, lines, title_font, margin_x + 26, y_start, WHITE)

    # Logo de sección en la parte SUPERIOR DERECHA (story)

    img = _paste_section_logo(img, section, canvas_w, canvas_h,
                              position="top-left", logo_override=logo_override,
                              logo_variant=logo_variant)

    return img


# ============================================================
# PLANTILLA 6: EN VIVO (Story)
# Foto a sangre + overlay negro.png + sticker EN VIVO y título centrados
# ============================================================

def render_en_vivo(source_image, section, title,
                   format_key="story", seccion_con_icono=True,
                   zoom=1.0, offset_x=0.5, offset_y=0.5, font_path=None,
                   logo_override=None, logo_variant=None,title_size_multiplier=1.0):
    """Plantilla EN VIVO para Story: degradado negro abajo, sticker + título
    pequeños posicionados en la zona segura inferior de Instagram (~70-78% alto)."""
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    margin_x = int(canvas_w * 0.08)

    # Foto a sangre
    canvas = cover_resize(source_image, (canvas_w, canvas_h), zoom, offset_x, offset_y)
    canvas = canvas.convert("RGBA")

    # Overlay degradado negro (gradacion-negro.png)
    canvas = canvas.convert("RGB")

    # Degradado negro INFERIOR (cubre la zona donde van el sticker y el título)
    # Empieza al 55% y se intensifica hacia abajo
    canvas = add_dark_gradient(canvas, top_frac=0.55, bottom_frac=0.95, max_alpha=230)

    draw = ImageDraw.Draw(canvas)

    # === Calcular tamaño del título (más pequeño, como en la referencia) ===
    max_w = canvas_w - margin_x * 2
    title_font, lines = fit_title_font(
        draw, title, max_w, max_lines=4,
        size_start=44, size_min=44, font_path=font_path,
    )
    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    title_total_h = int(line_h * len(lines))

    # === Sticker EN VIVO pequeño ===
    sticker_path = find_section_sticker("en vivo", with_icon=seccion_con_icono)
    sticker_img = None
    sticker_h = 0
    if sticker_path:
        sticker_img = Image.open(sticker_path).convert("RGBA")
        sticker_img = trim_transparent(sticker_img)
        # Sticker pequeño (~3.2% del alto), tamaño similar al de la referencia
        target_h = int(canvas_h * 0.032)
        ratio = target_h / sticker_img.height
        new_w = int(sticker_img.width * ratio)
        sticker_img = sticker_img.resize((new_w, target_h), Image.LANCZOS)
        sticker_h = target_h

    # Separación entre sticker y título
    gap = int(canvas_h * 0.018)

    # === Posicionar el bloque en la zona inferior segura de Instagram ===
    # El título termina al ~88% del alto (zona segura inferior de IG ~22%)
    # El bloque (sticker + título) queda en ~70-88% del alto
    block_bottom_y = int(canvas_h * 0.88)
    title_y_start = block_bottom_y - title_total_h
    sticker_y = title_y_start - gap - sticker_h

    # === Pegar sticker centrado horizontalmente ===
    if sticker_img is not None:
        sticker_x = (canvas_w - sticker_img.width) // 2
        canvas_rgba = canvas.convert("RGBA")
        canvas_rgba.paste(sticker_img, (sticker_x, sticker_y), sticker_img)
        canvas = canvas_rgba.convert("RGB")
        draw = ImageDraw.Draw(canvas)

    # === Dibujar título centrado horizontalmente ===
    for i, ln in enumerate(lines):
        bbox = draw.textbbox((0, 0), ln, font=title_font)
        tw = bbox[2] - bbox[0]
        tx = (canvas_w - tw) // 2
        ty = title_y_start + int(i * line_h)
        draw.text((tx, ty), ln, font=title_font, fill=WHITE)

    # === Logo de sección EN VIVO arriba a la derecha ===
    canvas = _paste_section_logo(
        canvas, "en-vivo", canvas_w, canvas_h,
        position="top-right",
        logo_override=logo_override,
        logo_variant=logo_variant,
    )

    return canvas


# ============================================================
# PLANTILLA 7: COLUMNISTA
# Fondo gris + título "Columnista de hoy" + card blanca con foto circular,
# breadcrumb, título, autor y resumen
# ============================================================


def render_columnista(source_image, section, title,
                      format_key="post", author="", summary="",
                      author_image=None,
                      zoom=1.0, offset_x=0.5, offset_y=0.5, font_path=None, title_size_multiplier=1.0,
                      logo_override=None, logo_variant=None,
                      seccion_con_icono=False):
    """Plantilla 'Columnista de hoy' con texto auto-escalable, color gris y justificado perfecto.
    Base: 1080x1350. En otros formatos se escala proporcionalmente.
    """
    canvas_w, canvas_h = FORMATS[format_key]["size"]

    # === Factor de escala (las medidas guía son para 1080x1350) ===
    base_w, base_h = 1080, 1350
    scale = min(canvas_w / base_w, canvas_h / base_h)

    def s(v):
        return int(v * scale)

    # Offset Y global: baja todo el bloque (header + card + footer) en px del diseño base
    Y_OFFSET = s(90)

    # === Fuentes ===
    header_font_path = font_path  # serif (abriltitling) por defecto
    sans_reg = OPENSANS_REG_PATH if os.path.exists(OPENSANS_REG_PATH) else font_path
    sans_bold = OPENSANS_BOLD_PATH if os.path.exists(OPENSANS_BOLD_PATH) else font_path

    # === Colores ===
    GRAY_BG_CARD = (235, 235, 235)
    BLACK = (0, 0, 0)
    RED = (219, 29, 34)
    GRAY_TEXT = (110, 110, 110) # Nuevo color gris para el resumen
    
    canvas = Image.new("RGB", (canvas_w, canvas_h), GRAY_BG_CARD)
    draw = ImageDraw.Draw(canvas)

    # === Imagen del avatar ===
    avatar_src = author_image if author_image is not None else source_image

    # =========================================================
    # COORDENADAS Y TAMAÑOS EXACTOS (base 1080x1350)
    # Todas las Y llevan Y_OFFSET para bajar el bloque completo
    # =========================================================
    header_x, header_y = s(215), s(110) + Y_OFFSET
    header_w, header_h = s(650), s(80)

    card_x, card_y = s(80), s(250) + Y_OFFSET
    card_w, card_h = s(920), s(720)
    card_right = card_x + card_w
    card_bottom = card_y + card_h

    avatar_x, avatar_y = s(100), s(310) + Y_OFFSET
    avatar_size = s(220)

    text_x = s(350)
    text_y_top = s(310) + Y_OFFSET
    text_w = s(600)

    icons_x, icons_y = s(80), s(1230)
    icons_w, icons_h = s(180), s(45)

    logo_x, logo_y = s(925), s(1220)
    logo_size = s(75)

    cta_x, cta_y = s(355), s(1280)
    cta_w_target, cta_h_target = s(550), s(45)

    # =========================================================
    # HEADER "Columnista de hoy"
    # =========================================================
    header_size = int(header_h * 0.85)
    header_font = load_font(header_size, bold=False, font_path=header_font_path)
    htxt = "Columnista de hoy"
    hbbox = draw.textbbox((0, 0), htxt, font=header_font)
    hw = hbbox[2] - hbbox[0]
    hh = hbbox[3] - hbbox[1]
    
    draw.text(
        (header_x + (header_w - hw) // 2, header_y + (header_h - hh) // 2 - hbbox[1]),
        htxt, font=header_font, fill=BLACK,
    )

    # =========================================================
    # CARD BLANCA
    # =========================================================
    draw.rounded_rectangle(
        [card_x, card_y, card_right, card_bottom],
        radius=s(15), fill=(255, 255, 255)
    )

    # =========================================================
    # AVATAR 220x220 (circular)
    # =========================================================
    avatar = make_circle_avatar(avatar_src, avatar_size, bg_color=RED)
    canvas_rgba = canvas.convert("RGBA")
    canvas_rgba.alpha_composite(avatar, (avatar_x, avatar_y))
    canvas = canvas_rgba.convert("RGB")
    draw = ImageDraw.Draw(canvas)

    # =========================================================
    # CAJA DE TEXTO: breadcrumb + título + autor
    # =========================================================
    cursor_y = text_y_top

    # ----- Breadcrumb -----
    crumb_size = s(26)
    crumb_font = load_font(crumb_size, bold=False, font_path=sans_reg)
    crumb_bold = load_font(crumb_size, bold=True, font_path=sans_bold)
    section_text = (section or "").strip().capitalize() or "Opinión"

    home_text = "Home"
    sep_text = "  ›  "
    home_bbox = draw.textbbox((0, 0), home_text, font=crumb_bold)
    home_w = home_bbox[2] - home_bbox[0]
    sep_bbox = draw.textbbox((0, 0), sep_text, font=crumb_font)
    sep_w = sep_bbox[2] - sep_bbox[0]

    draw.text((text_x, cursor_y), home_text, font=crumb_bold, fill=BLACK)
    draw.text((text_x + home_w, cursor_y), sep_text, font=crumb_font, fill=(140, 140, 140))
    draw.text((text_x + home_w + sep_w, cursor_y), section_text, font=crumb_bold, fill=BLACK)
    
    crumb_h_real = home_bbox[3] - home_bbox[1]
    cursor_y += crumb_h_real + s(18)

    # ----- Título del artículo -----
    title_size_start = s(56)
    title_size_min = s(38)
    title_font, title_lines = fit_title_font(
        draw, title, text_w, max_lines=3,
        size_start=title_size_start, size_min=title_size_min,
        font_path=sans_bold,
    )
    tbbox = draw.textbbox((0, 0), "Ag", font=title_font)
    title_line_h = (tbbox[3] - tbbox[1]) * 1.2
    
    for i, ln in enumerate(title_lines):
        draw.text((text_x, cursor_y + int(i * title_line_h)), ln, font=title_font, fill=BLACK)
    
    cursor_y += int(title_line_h * len(title_lines)) + s(12)

    # ----- "Por [Autor]" -----
    if author:
        author_size = s(28)
        author_font = load_font(author_size, bold=False, font_path=sans_reg)
        draw.text((text_x, cursor_y), f"Por {author}", font=author_font, fill=(120, 120, 120))
        
        abb = draw.textbbox((0, 0), "Ag", font=author_font)
        cursor_y += (abb[3] - abb[1]) + s(28)

    # =========================================================
    # RESUMEN (Auto-escalado y Justificado perfecto)
    # =========================================================
    if summary:
        summary_max_y = card_bottom - s(40) 
        space_for_summary = summary_max_y - cursor_y
        
        best_size = s(23) 
        max_size = s(41)
        
        best_lines = []
        best_font = None
        best_line_h = 0
        
        # Multiplicador de interlineado (1.45 default, bajamos 3 puntos → 1.15)
        LINE_HEIGHT_MULT = 1.15

        # 1. Encontrar el tamaño ideal
        for f_size in range(max_size, best_size - 1, -1):
            temp_font = load_font(f_size, bold=False, font_path=sans_reg)
            temp_lines = wrap_text_lines(summary, temp_font, text_w, draw)
            
            tbb = draw.textbbox((0, 0), "Ag", font=temp_font)
            temp_line_h = (tbb[3] - tbb[1]) * LINE_HEIGHT_MULT
            
            if len(temp_lines) * temp_line_h <= space_for_summary:
                best_size = f_size
                best_lines = temp_lines
                best_font = temp_font
                best_line_h = temp_line_h
                break
        
        if best_font is None:
            best_font = load_font(best_size, bold=False, font_path=sans_reg)
            tbb = draw.textbbox((0, 0), "Ag", font=best_font)
            best_line_h = (tbb[3] - tbb[1]) * LINE_HEIGHT_MULT
            max_lines = max(1, int(space_for_summary / best_line_h))
            best_lines = wrap_text_lines(summary, best_font, text_w, draw, max_lines=max_lines)
            
        # 2. Dibujar alineado a la izquierda
        for i, ln in enumerate(best_lines):
            y_pos = cursor_y + int(i * best_line_h)
            draw.text((text_x, y_pos), ln, font=best_font, fill=GRAY_TEXT)

    # =========================================================
    # BARRA INFERIOR
    # =========================================================
    icons_file = _social_icons_path("negro")
    if os.path.exists(icons_file):
        canvas = paste_asset(
            canvas, icons_file,
            target_height=icons_h,
            position=(icons_x, icons_y + icons_h),
            anchor="bottom-left",
        )

    cta_file = _cta_path("negro")
    if os.path.exists(cta_file):
        canvas = paste_asset(
            canvas, cta_file,
            target_width=cta_w_target,
            position=(cta_x, cta_y + cta_h_target),
            anchor="bottom-left",
        )

    logo_file = _logo_path("negro")
    if os.path.exists(logo_file):
        canvas = paste_asset(
            canvas, logo_file,
            target_height=logo_size,
            position=(logo_x, logo_y + logo_size),
            anchor="bottom-left",
        )

    return canvas
# ============================================================
# PLANTILLAS: ELECCIONES 2026 POST y STORY
# Foto a sangre + overlay PNG dedicado + titulo
# ============================================================

def render_elecciones_2026_post(source_image, section, title,
                                format_key=None,
                                zoom=1.0, offset_x=0.5, offset_y=0.5,
                                font_path=None, title_size_multiplier=1.0, **kwargs):
    """
    Plantilla Elecciones 2026 POST (1080x1350):
    - Foto cubre todo el canvas
    - Encima va el overlay assets/fondos/eleccionespost.png
    - Titulo blanco con linea roja, anclado abajo
    Nota: ignora el format_key recibido, siempre usa 'post' (1080x1350).
    """
    # FORZAR formato POST
    format_key = "post"
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    margin_x = int(canvas_w * 0.06)

    # 1. Foto base a sangre
    img = cover_resize(source_image, (canvas_w, canvas_h), zoom, offset_x, offset_y)

    # 2. Overlay con el PNG del fondo
    overlay_path = os.path.join(FONDOS_DIR, "eleccionespost.png")
    if os.path.exists(overlay_path):
        overlay = Image.open(overlay_path).convert("RGBA")
        overlay = overlay.resize((canvas_w, canvas_h), Image.LANCZOS)
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    # 3. Titulo abajo con linea roja
    draw = ImageDraw.Draw(img)
    max_w = canvas_w - margin_x * 2 - 6 - 20 - 60
    title_font, lines = fit_title_font(draw, title, max_w, max_lines=4, font_path=font_path,
                                       size_multiplier=title_size_multiplier)

    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))
    y_start = canvas_h - int(canvas_h * 0.163) - total_h

    draw.rectangle([margin_x, y_start, margin_x + 6, y_start + total_h], fill=RED)
    draw_text_lines(draw, lines, title_font, margin_x + 26, y_start, WHITE)

    return img


def render_elecciones_2026_card_post(source_image, section, title,
                                     format_key=None,
                                     zoom=1.0, offset_x=0.5, offset_y=0.5,
                                     font_path=None, title_size_multiplier=1.0,
                                     **kwargs):
    """
    Plantilla Elecciones 2026 Card POST (1080x1350):
    - Fondo: PNG base elecciones-card.png
    - Foto del candidato enmarcada en la parte superior
    - Texto del titulo en NEGRO debajo de la foto, sin linea roja
    """
    format_key = "post"
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    margin_x = int(canvas_w * 0.08)

    # 1. Cargar el PNG base
    overlay_path = os.path.join(FONDOS_DIR, "elecciones-card.jpg")
    if os.path.exists(overlay_path):
        canvas = Image.open(overlay_path).convert("RGB")
        canvas = canvas.resize((canvas_w, canvas_h), Image.LANCZOS)
    else:
        canvas = Image.new("RGB", (canvas_w, canvas_h), (220, 220, 220))

    # 2. Pegar la foto del candidato (enmarcada arriba)
    photo_top    = int(canvas_h * 0.16)
    photo_left   = margin_x
    photo_right  = canvas_w - margin_x
    photo_bottom = int(canvas_h * 0.55)
    photo_w      = photo_right - photo_left
    photo_h      = photo_bottom - photo_top

    photo = cover_resize(source_image, (photo_w, photo_h), zoom, offset_x, offset_y)

    # Aplicar esquinas redondeadas a la foto
    radius = 30  # ajustar segun cuan redondeadas se quieran las esquinas

    # Crear mascara con esquinas redondeadas
    mask = Image.new("L", (photo_w, photo_h), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(
        [0, 0, photo_w, photo_h],
        radius=radius,
        fill=255,
    )

    # Convertir la foto a RGBA y aplicar la mascara
    photo_rgba = photo.convert("RGBA")
    photo_rgba.putalpha(mask)

    # Pegar respetando transparencia
    canvas_rgba = canvas.convert("RGBA")
    canvas_rgba.paste(photo_rgba, (photo_left, photo_top), photo_rgba)
    canvas = canvas_rgba.convert("RGB")

    # 3. Titulo en NEGRO debajo de la foto (sin linea roja)
    draw = ImageDraw.Draw(canvas)

    # Margen interno extra para el texto (mas pegado al centro del cuadro)
    text_margin_x = int(canvas_w * 0.12)  # 12% en lugar del 8% de la foto
    title_max_w = canvas_w - text_margin_x * 2

    title_font, lines = fit_title_font(
        draw, title, title_max_w,
        max_lines=4,
        size_start=54, size_min=36,
        font_path=font_path,
        size_multiplier=title_size_multiplier,
    )

    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))

    # Texto BAJADO: empieza mas abajo de la foto
    text_y_start = photo_bottom + int(canvas_h * 0.055)

    # Dibujar lineas alineadas a la izquierda en negro, con margen mayor
    for i, ln in enumerate(lines):
        ly = text_y_start + int(i * line_h)
        draw.text((text_margin_x, ly), ln, font=title_font, fill=BLACK)

    return canvas

def render_elecciones_2026_story(source_image, section, title,
                                 format_key=None,
                                 zoom=1.0, offset_x=0.5, offset_y=0.5,
                                 font_path=None, title_size_multiplier=1.0, **kwargs):
    """
    Plantilla Elecciones 2026 STORY (1080x1920):
    - Foto cubre todo el canvas vertical
    - Encima va el overlay assets/fondos/eleccionesstory.png
    - Titulo blanco con linea roja, anclado en zona segura inferior
    Nota: ignora el format_key recibido, siempre usa 'story' (1080x1920).
    """
    # FORZAR formato STORY
    format_key = "story"
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    margin_x = int(canvas_w * 0.08)

    # 1. Foto base a sangre
    img = cover_resize(source_image, (canvas_w, canvas_h), zoom, offset_x, offset_y)

    # 2. Overlay con el PNG del fondo
    overlay_path = os.path.join(FONDOS_DIR, "eleccionesstory.png")
    if os.path.exists(overlay_path):
        overlay = Image.open(overlay_path).convert("RGBA")
        overlay = overlay.resize((canvas_w, canvas_h), Image.LANCZOS)
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    # 3. Titulo en zona segura inferior de Stories (~22% de abajo es zona de IG UI)
    draw = ImageDraw.Draw(img)
    max_w = canvas_w - margin_x * 2 - 6 - 20
    title_font, lines = fit_title_font(draw, title, max_w, max_lines=5, font_path=font_path,
                                       size_multiplier=title_size_multiplier)   

    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))
    y_start = canvas_h - int(canvas_h * 0.18) - total_h

    draw.rectangle([margin_x, y_start, margin_x + 6, y_start + total_h], fill=RED)
    draw_text_lines(draw, lines, title_font, margin_x + 26, y_start, WHITE)

    return img

def render_elecciones_2026_ultima_hora_post(source_image, section, title,
                                        format_key=None,
                                        zoom=1.0, offset_x=0.5, offset_y=0.5,
                                        font_path=None, title_size_multiplier=1.0, **kwargs):
    """
    Plantilla Ultima Hora Elecciones 2026 POST (1080x1350):
    - Foto cubre todo el canvas
    - Encima va el overlay assets/fondos/ultimahoraeleccionespost.png
    - Titulo blanco centrado, sin linea roja
    Nota: ignora el format_key recibido, siempre usa 'post' (1080x1350).
    """
    format_key = "post"
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    margin_x = int(canvas_w * 0.06)

    img = cover_resize(source_image, (canvas_w, canvas_h), zoom, offset_x, offset_y)

    overlay_path = os.path.join(FONDOS_DIR, "ultimahoraeleccionespost.png")
    if not os.path.exists(overlay_path):
        overlay_path = os.path.join(FONDOS_DIR, "ultima-hora.png")
    if os.path.exists(overlay_path):
        overlay = Image.open(overlay_path).convert("RGBA")
        overlay = overlay.resize((canvas_w, canvas_h), Image.LANCZOS)
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)
    max_w = canvas_w - margin_x * 2 - 6 - 20 - 60
    title_font, lines = fit_title_font(draw, title, max_w, max_lines=4, font_path=font_path,
                                       size_multiplier=title_size_multiplier)

    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))
    y_start = canvas_h - int(canvas_h * 0.163) - total_h

    for i, ln in enumerate(lines):
        bbox = draw.textbbox((0, 0), ln, font=title_font)
        tw = bbox[2] - bbox[0]
        tx = (canvas_w - tw) // 2
        ty = y_start + int(i * line_h)
        draw.text((tx, ty), ln, font=title_font, fill=WHITE)

    return img

def render_elecciones_2026_ultima_hora_story(source_image, section, title,
                                         format_key=None,
                                         zoom=1.0, offset_x=0.5, offset_y=0.5,
                                         font_path=None, title_size_multiplier=1.0, **kwargs):
    """
    Plantilla Ultima Hora Elecciones 2026 STORY (1080x1920):
    - Foto cubre todo el canvas vertical
    - Encima va el overlay assets/fondos/ultimahoraeleccionesstory.png
    - Titulo blanco con linea roja, anclado en zona segura inferior
    Nota: ignora el format_key recibido, siempre usa 'story' (1080x1920).
    """
    format_key = "story"
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    margin_x = int(canvas_w * 0.08)

    img = cover_resize(source_image, (canvas_w, canvas_h), zoom, offset_x, offset_y)

    overlay_path = os.path.join(FONDOS_DIR, "ultimahoraeleccionesstory.png")
    if not os.path.exists(overlay_path):
        overlay_path = os.path.join(FONDOS_DIR, "ultima-hora.png")
    if os.path.exists(overlay_path):
        overlay = Image.open(overlay_path).convert("RGBA")
        overlay = overlay.resize((canvas_w, canvas_h), Image.LANCZOS)
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)
    max_w = canvas_w - margin_x * 2 - 6 - 20
    title_font, lines = fit_title_font(draw, title, max_w, max_lines=5, font_path=font_path,
                                       size_multiplier=title_size_multiplier)

    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))
    y_start = canvas_h - int(canvas_h * 0.18) - total_h

    draw.rectangle([margin_x, y_start, margin_x + 6, y_start + total_h], fill=RED)
    draw_text_lines(draw, lines, title_font, margin_x + 26, y_start, WHITE)

    return img

def render_envivo_elecciones_post(source_image, section, title,
                                  format_key=None,
                                  zoom=1.0, offset_x=0.5, offset_y=0.5,
                                  font_path=None, title_size_multiplier=1.0, **kwargs):
    """
    Plantilla En Vivo Elecciones POST (1080x1350):
    - Foto cubre todo el canvas
    - Overlay assets/fondos/envivoeleccionespost.png
    - Titulo blanco CENTRADO, sin linea roja
    """
    format_key = "post"
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    margin_x = int(canvas_w * 0.06)

    # 1. Foto base a sangre
    img = cover_resize(source_image, (canvas_w, canvas_h), zoom, offset_x, offset_y)

    # 2. Overlay con el PNG dedicado
    overlay_path = os.path.join(FONDOS_DIR, "envivoeleccionespost.png")
    if os.path.exists(overlay_path):
        overlay = Image.open(overlay_path).convert("RGBA")
        overlay = overlay.resize((canvas_w, canvas_h), Image.LANCZOS)
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    # 3. Titulo CENTRADO (sin linea roja)
    draw = ImageDraw.Draw(img)
    max_w = canvas_w - margin_x * 2
    title_font, lines = fit_title_font(draw, title, max_w, max_lines=4, font_path=font_path)

    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))
    y_start = canvas_h - int(canvas_h * 0.163) - total_h

    # Dibujar cada linea centrada horizontalmente
    for i, ln in enumerate(lines):
        bbox = draw.textbbox((0, 0), ln, font=title_font)
        tw = bbox[2] - bbox[0]
        tx = (canvas_w - tw) // 2
        ty = y_start + int(i * line_h)
        draw.text((tx, ty), ln, font=title_font, fill=WHITE)

    return img


def render_envivo_elecciones_story(source_image, section, title,
                                   format_key=None,
                                   zoom=1.0, offset_x=0.5, offset_y=0.5,
                                   font_path=None, title_size_multiplier=1.0, **kwargs):
    """
    Plantilla En Vivo Elecciones STORY (1080x1920):
    - Foto cubre todo el canvas vertical
    - Overlay assets/fondos/envivoeleccionesstory.png
    - Titulo blanco CENTRADO, sin linea roja
    """
    format_key = "story"
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    margin_x = int(canvas_w * 0.08)

    # 1. Foto base a sangre
    img = cover_resize(source_image, (canvas_w, canvas_h), zoom, offset_x, offset_y)

    # 2. Overlay con el PNG dedicado
    overlay_path = os.path.join(FONDOS_DIR, "envivoeleccionesstory.png")
    if os.path.exists(overlay_path):
        overlay = Image.open(overlay_path).convert("RGBA")
        overlay = overlay.resize((canvas_w, canvas_h), Image.LANCZOS)
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    # 3. Titulo CENTRADO (sin linea roja), anclado abajo
    draw = ImageDraw.Draw(img)
    max_w = canvas_w - margin_x * 2
    title_font, lines = fit_title_font(draw, title, max_w, max_lines=5, font_path=font_path)

    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))
    y_start = canvas_h - int(canvas_h * 0.21) - total_h

    # Dibujar cada linea centrada horizontalmente
    for i, ln in enumerate(lines):
        bbox = draw.textbbox((0, 0), ln, font=title_font)
        tw = bbox[2] - bbox[0]
        tx = (canvas_w - tw) // 2
        ty = y_start + int(i * line_h)
        draw.text((tx, ty), ln, font=title_font, fill=WHITE)

    return img


def render_classic_overlay(source_image, section, title,
                           overlay_name,
                           format_key="post",
                           zoom=1.0, offset_x=0.5, offset_y=0.5,
                           font_path=None, title_size_multiplier=1.0, **kwargs):
    """
    Renderiza una plantilla clásica simple:
    - Foto a sangre + overlay PNG de assets/fondos/
    - Título blanco centrado en la parte inferior
    """
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    margin_x = int(canvas_w * 0.06) if format_key == "post" else int(canvas_w * 0.08)

    img = cover_resize(source_image, (canvas_w, canvas_h), zoom, offset_x, offset_y)
    overlay_path = os.path.join(FONDOS_DIR, overlay_name)
    if os.path.exists(overlay_path):
        overlay = Image.open(overlay_path).convert("RGBA")
        overlay = overlay.resize((canvas_w, canvas_h), Image.LANCZOS)
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)
    max_w = canvas_w - margin_x * 2 - 20
    max_lines = 4 if format_key == "post" else 5
    title_font, lines = fit_title_font(
        draw, title, max_w, max_lines=max_lines,
        size_start=48 if format_key == "post" else 54,
        size_min=32, font_path=font_path,
        size_multiplier=title_size_multiplier,
    )

    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    total_h = int(line_h * len(lines))
    y_start = canvas_h - int(canvas_h * 0.163) - total_h if format_key == "post" else canvas_h - int(canvas_h * 0.18) - total_h

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=title_font)
        tw = bbox[2] - bbox[0]
        tx = (canvas_w - tw) // 2
        ty = int(y_start + i * line_h - bbox[1])
        draw.text((tx, ty), line, font=title_font, fill=WHITE)

    return img

# ============================================================
# RENDER GENÉRICO (del script v2, adaptado a las nuevas plantillas)
# ============================================================
def render_generic(source_image, section, title,
                   format_key="post", fondo_name="ultima-hora",
                   seccion_con_icono=False, show_cta=False,
                   show_social_icons=True,
                   zoom=1.0, offset_x=0.5, offset_y=0.5, font_path=None,
                   logo_override=None, logo_variant=None,
                   sticker_position="bottom", title_size_multiplier=1.0):
    """
    Render con fondo/degradado PNG de assets/fondos/.

    sticker_position: 'top' (como classic), 'bottom' (junto al título) o 'none'.
    logo_override / logo_variant: control manual del logo de sección.
    """
    canvas_w, canvas_h = FORMATS[format_key]["size"]
    margin_x = int(canvas_w * 0.06)

    canvas = cover_resize(source_image, (canvas_w, canvas_h), zoom, offset_x, offset_y)
    canvas = canvas.convert("RGBA")

    bg_path = find_fondo(fondo_name)
    if bg_path:
        overlay = Image.open(bg_path).convert("RGBA")
        overlay = overlay.resize((canvas_w, canvas_h), Image.LANCZOS)
        canvas = Image.alpha_composite(canvas, overlay)

    canvas = canvas.convert("RGB")

    text_area_top = int(canvas_h * 0.62)
    text_area_h = canvas_h - text_area_top

    badge_font = load_font(28, bold=True, font_path=font_path)
    sticker_h = int(canvas_h * 0.05) if format_family(format_key) == "post" else int(canvas_h * 0.04)

    # === Sticker de sección ===
    if sticker_position == "top":
        # Arriba a la izquierda (como classic)
        top_sticker_y = int(canvas_h * 0.045)
        canvas, _, _ = draw_section_badge(
            canvas, section.upper(), (margin_x, top_sticker_y),
            badge_font, seccion_con_icono,
        )
        # El título empieza donde estaba antes (no se mueve)
        title_top = text_area_top + int(text_area_h * 0.10)
    elif sticker_position == "bottom":
        # Junto al título (comportamiento original)
        sticker_y = text_area_top + int(text_area_h * 0.10)
        canvas, _, _ = draw_section_badge(
            canvas, section.upper(), (margin_x, sticker_y),
            badge_font, seccion_con_icono,
        )
        title_top = sticker_y + sticker_h + int(canvas_h * 0.025)
    else:  # 'none'
        # Sin sticker, el título sube un poco
        title_top = text_area_top + int(text_area_h * 0.10)

    # === Título ===
    title_max_w = canvas_w - margin_x * 2 - 30
    reserved_bottom = int(canvas_h * 0.14) if (show_cta or show_social_icons) else int(canvas_h * 0.10)
    max_title_h = canvas_h - title_top - reserved_bottom
    line_h_approx = 60 if format_family(format_key) == "post" else 65
    max_lines = max(3, max_title_h // line_h_approx)

    draw = ImageDraw.Draw(canvas)
    title_font, lines = fit_title_font(
        draw, title, title_max_w, max_lines=max_lines,
        size_start=48 if format_family(format_key) == "post" else 54,
        size_min=32, font_path=font_path,
    )

    # Detectar color de texto según luminosidad del área
    sample_area = canvas.crop((0, title_top, canvas_w, min(canvas_h, title_top + 200)))
    bg_sample = np.array(sample_area.resize((50, 50))).mean()
    title_color = WHITE if bg_sample < 128 else BLACK

    lh_bbox = draw.textbbox((0, 0), "Ag", font=title_font)
    line_h = (lh_bbox[3] - lh_bbox[1]) * 1.25
    title_total_h = int(line_h * len(lines))

    draw.rectangle([margin_x, title_top, margin_x + 6, title_top + title_total_h], fill=RED)
    draw_text_lines(draw, lines, title_font, margin_x + 26 + 6, title_top, title_color)

    # === Footer ===
    footer_y = canvas_h - int(canvas_h * 0.04)
    canvas = _paste_logo(canvas, canvas_w, footer_y, canvas_h, title_color)

    if show_cta:
        canvas = _paste_cta(canvas, margin_x, footer_y, canvas_w, title_color, draw_fallback=draw)
    elif show_social_icons:
        canvas = _paste_social_icons(canvas, margin_x, footer_y, canvas_h, title_color)


    # === Logo de sección ===
    # Logo siempre top-right, independiente de donde esté el sticker
    canvas = _paste_section_logo(
        canvas, section, canvas_w, canvas_h,
        position="top-right", logo_override=logo_override,
        logo_variant=logo_variant,
    )
    return canvas

# ============================================================
# PLANTILLA: RESULTADOS ELECCIONES (ranking de candidatos)
# Foto candidato + barra vertical de color + % + votos + nombre
# Sobre overlay resultados-elecciones-post.png o resultados-elecciones-story.png
# ============================================================

# Colores disponibles para barras de candidatos
BAR_COLORS = {
    "Amarillo": (255, 215, 0),
    "Azul": (100, 130, 200),
    "Rojo": (227, 27, 35),
    "Verde": (50, 180, 90),
    "Naranja": (255, 140, 40),
    "Morado": (120, 80, 180),
    "Rosa": (240, 110, 170),
}


# Carpeta de candidatos preconfigurados
CANDIDATOS_DIR = os.path.join(ASSETS_DIR, "candidatos")


# Mapeo manual de nombre-archivo → nombre formal con acentos
# Si el archivo no esta aqui, se autogenera desde el nombre del archivo
CANDIDATOS_NOMBRES = {
    "clara-lopez": "CLARA LÓPEZ",
    "oscar-lizcano": "OSCAR LIZCANO",
    "santiago-botero": "SANTIAGO BOTERO",
    "miguel-uribe": "MIGUEL URIBE",
    "sondra-macollins": "SONDRA MACOLLINS",
    "ivan-cepeda": "IVÁN CEPEDA",
    "abelardo-de-la-espriella": "ABELARDO DE LA ESPRIELLA",
    "claudia-lopez": "CLAUDIA LÓPEZ",
    "paloma-valencia": "PALOMA VALENCIA",
    "sergio-fajardo": "SERGIO FAJARDO",
    "roy-barreras": "ROY BARRERAS",
    "gustavo-matamoros": "GUSTAVO MATAMOROS",
    "luis-gilberto-murillo": "LUIS GILBERTO MURILLO",
    "carlos-caicedo": "CARLOS CAICEDO",
}

# Partidos politicos (opcional, por si despues querés mostrarlos)
CANDIDATOS_PARTIDOS = {
    "clara-lopez": "Partido Esperanza Democrática",
    "oscar-lizcano": "Coalición F.A.M.I.L.I.A",
    "santiago-botero": "Romper el Sistema",
    "miguel-uribe": "Partido Demócrata Colombiano",
    "sondra-macollins": "Sondra Macollins",
    "ivan-cepeda": "Pacto Histórico",
    "abelardo-de-la-espriella": "Defensores de la Patria",
    "claudia-lopez": "Con Claudia Imparables",
    "paloma-valencia": "Centro Democrático",
    "sergio-fajardo": "Dignidad & Compromiso",
    "roy-barreras": "La Fuerza",
    "gustavo-matamoros": "Partido Ecologista Colombiano",
    "luis-gilberto-murillo": "La Oportunidad es Colombia",
    "carlos-caicedo": "Caicedo",
}


def list_candidatos():
    """
    Escanea assets/candidatos/ y devuelve lista de candidatos disponibles.

    Si el archivo no esta en CANDIDATOS_NOMBRES, autogenera nombre desde
    el filename (replazando guiones por espacios y mayusculizando).

    Returns:
        Lista de dicts con:
            {
                "key": "ivan-cepeda",
                "nombre": "IVÁN CEPEDA",
                "partido": "Pacto Histórico",
                "path": "/ruta/absoluta.png",
            }
    """
    if not os.path.exists(CANDIDATOS_DIR):
        return []

    candidatos = []
    for f in sorted(os.listdir(CANDIDATOS_DIR)):
        if not f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            continue
        if f.startswith("_") or f.startswith("."):
            continue

        name_no_ext = os.path.splitext(f)[0]

        # 1) Nombre formal desde el mapeo si existe
        if name_no_ext in CANDIDATOS_NOMBRES:
            clean_name = CANDIDATOS_NOMBRES[name_no_ext]
        else:
            # 2) Autogenerar desde filename
            clean_name = name_no_ext.replace("_", " ").replace("-", " ")
            clean_name = " ".join(w.capitalize() for w in clean_name.split()).upper()

        partido = CANDIDATOS_PARTIDOS.get(name_no_ext, "")

        candidatos.append({
            "key": name_no_ext,
            "nombre": clean_name,
            "partido": partido,
            "path": os.path.join(CANDIDATOS_DIR, f),
        })

    return candidatos


def load_candidato_image(candidato_key):
    """Carga la imagen PIL de un candidato preservando transparencia (RGBA)."""
    if not candidato_key:
        return None
    folder = CANDIDATOS_DIR
    if not os.path.exists(folder):
        return None
    for f in os.listdir(folder):
        if os.path.splitext(f)[0] == candidato_key:
            try:
                # Cargar como RGBA para preservar transparencia
                return Image.open(os.path.join(folder, f)).convert("RGBA")
            except Exception:
                return None
    return None

def _format_percentage(pct):
    """Formatea un porcentaje: 28.0 -> '28%', 26.5 -> '26,5%'"""
    if pct == int(pct):
        return str(int(pct)) + "%"
    return ("%.1f" % pct).replace(".", ",") + "%"

def render_resultados_candidatos(candidatos, format_key="post", font_path=None, boletin_text="",title_size_multiplier=1.0):
    """
    Render de tarjeta de resultados de elecciones.

    Cambios incorporados:
    - N>3: Barra ancha detrás de la foto, texto grande azul oscuro, porcentaje horizontal, nombre rotado, y degradado inferior en la foto.
    - N<=3: Barra más gruesa, alineada a la base y dibujada detrás de la foto. Textos desplazados hacia abajo.
      * NUEVO: Ajuste dinámico de y_offset_factor para el formato "story" para que el texto baje y no tape la cara.
    """
    def _fmt_pct(pct):
        if pct == int(pct):
            return str(int(pct)) + "%"
        return ("%.1f" % pct).replace(".", ",") + "%"
    
    def _fmt_votos(votos_raw):
        """Formatea votos: 2223422 -> '2.223.422 VOTOS'. Si no es numerico, deja el texto."""
        if not votos_raw:
            return ""
        s = str(votos_raw).strip().upper()

        # Si ya tiene 'VOTOS' al final, lo quitamos primero
        if s.endswith("VOTOS"):
            s = s[:-5].strip()

        # Quitar puntos, comas y espacios para ver si es solo digitos
        digits_only = s.replace(".", "").replace(",", "").replace(" ", "")

        if digits_only.isdigit():
            # Formatear con puntos cada 3 digitos
            n_int = int(digits_only)
            formatted = "{:,}".format(n_int).replace(",", ".")
            return formatted + " VOTOS"
        else:
            # Si tiene letras (ej 250XXX), dejarlo tal cual + ' VOTOS'
            return s + " VOTOS"
    
    if not candidatos:
        raise ValueError("Debe haber al menos 1 candidato")
    if len(candidatos) > 5:
        candidatos = candidatos[:5]

    canvas_w, canvas_h = FORMATS[format_key]["size"]

    lft_bold = os.path.join(FONTS_DIR, "LFTEtica-Bold.ttf")
    font_bold_path = lft_bold if os.path.exists(lft_bold) else font_path

    overlay_basename = (
        "resultados-elecciones-post" if format_key == "post"
        else "resultados-elecciones-story"
    )
    overlay_path = None
    for ext in [".png", ".jpg", ".jpeg", ".webp"]:
        cand_path = os.path.join(FONDOS_DIR, overlay_basename + ext)
        if os.path.exists(cand_path):
            overlay_path = cand_path
            break

    if overlay_path:
        canvas = Image.open(overlay_path).convert("RGB")
        canvas = canvas.resize((canvas_w, canvas_h), Image.LANCZOS)
    else:
        canvas = Image.new("RGB", (canvas_w, canvas_h), (220, 220, 220))

    if format_key == "post":
        bloque_top    = int(canvas_h * 0.22)
        bloque_bottom = int(canvas_h * 0.84)
        bloque_left   = int(canvas_w * 0.10)
        bloque_right  = canvas_w - int(canvas_w * 0.10)
    else:
        bloque_top    = int(canvas_h * 0.18)
        bloque_bottom = int(canvas_h * 0.84)
        bloque_left   = int(canvas_w * 0.10)
        bloque_right  = canvas_w - int(canvas_w * 0.10)

    bloque_w = bloque_right - bloque_left
    bloque_h = bloque_bottom - bloque_top

    n     = len(candidatos)
    col_w = bloque_w / n

    candidatos_ord = sorted(candidatos, key=lambda c: c.get("porcentaje", 0), reverse=True)
    max_pct = max((c.get("porcentaje", 0) for c in candidatos_ord), default=100) or 100

    TEXT_COLOR = (255, 255, 255)

    # Escala adaptativa
    foto_scale_map  = {1: 1.00, 2: 1.00, 3: 1.05, 4: 1.20, 5: 1.40}
    text_scale_map  = {1: 1.00, 2: 1.00, 3: 0.85, 4: 0.72, 5: 0.60}
    foto_multiplier = foto_scale_map.get(n, 1.00)
    text_multiplier = text_scale_map.get(n, 1.00)

    draw_bg = ImageDraw.Draw(canvas)

    # Separadores verticales sutiles entre columnas
    if n > 1:
        for i in range(1, n):
            sep_x      = int(bloque_left + i * col_w)
            sep_top    = bloque_top    + int(bloque_h * 0.05)
            sep_bottom = bloque_bottom - int(bloque_h * 0.05)
            draw_bg.rectangle(
                [sep_x - 1, sep_top, sep_x + 1, sep_bottom],
                fill=(180, 180, 180),
            )

    for i, cand in enumerate(candidatos_ord):
        col_left     = int(bloque_left + i * col_w)
        col_right    = int(bloque_left + (i + 1) * col_w)
        col_w_int    = col_right - col_left
        col_center_x = (col_left + col_right) // 2

        pct        = cand.get("porcentaje", 0)
        color_name = cand.get("color_barra", "Amarillo")
        bar_color  = BAR_COLORS.get(color_name, BAR_COLORS["Amarillo"])

        if n <= 3:
            # ── MODO NORMAL: texto abajo sobre la foto ───────────────────────

            # 1. DIBUJAR LA BARRA PRIMERO (Detrás de la foto, más gruesa, base igual que degradado)
            bar_zone_h   = int(bloque_h * 0.65) # Zona máxima para la barra
            bar_h        = int(bar_zone_h * (pct / max_pct)) if max_pct > 0 else 0
            bar_w        = max(15, int(col_w * 0.08)) # Barra más gruesa
            bar_x        = col_left + int(col_w * 0.06) 
            bar_bottom_y = bloque_bottom # Punto de partida = base del bloque (igual al degradado)
            bar_top_y    = bar_bottom_y - bar_h

            if bar_h > 5:
                try:
                    draw_bg.rounded_rectangle(
                        [bar_x, bar_top_y, bar_x + bar_w, bar_bottom_y],
                        radius=bar_w // 2, fill=bar_color,
                    )
                    # Quitar el borde redondeado inferior para que asiente en la base
                    draw_bg.rectangle([bar_x, bar_bottom_y - bar_w, bar_x + bar_w, bar_bottom_y], fill=bar_color)
                except AttributeError:
                    draw_bg.rectangle([bar_x, bar_top_y, bar_x + bar_w, bar_bottom_y], fill=bar_color)

            # 2. PEGAR LA FOTO Y EL DEGRADADO (Quedan encima de la barra)
            foto = cand.get("foto")
            if foto is not None:
                iw, ih = foto.size
                scale        = col_w_int / iw
                nw           = col_w_int
                target_h_eff = int(ih * scale * foto_multiplier)

                if target_h_eff < bloque_h:
                    scale_h  = bloque_h / ih
                    nw_alt   = int(iw * scale_h)
                    if nw_alt > col_w_int:
                        nw           = col_w_int
                        target_h_eff = int(ih * (col_w_int / iw))
                    else:
                        nw           = nw_alt
                        target_h_eff = bloque_h

                foto_scaled = foto.resize((nw, target_h_eff), Image.LANCZOS)
                if nw > col_w_int:
                    crop_x      = (nw - col_w_int) // 2
                    foto_scaled = foto_scaled.crop((crop_x, 0, crop_x + col_w_int, target_h_eff))
                    nw          = col_w_int

                foto_x = col_left
                foto_y = bloque_bottom - target_h_eff

                if foto_scaled.mode == "RGBA":
                    canvas_rgba = canvas.convert("RGBA")
                    canvas_rgba.paste(foto_scaled, (foto_x, foto_y), foto_scaled)
                    canvas = canvas_rgba.convert("RGB")
                else:
                    canvas.paste(foto_scaled, (foto_x, foto_y))

                # Degradado negro
                grad_h   = int(target_h_eff * 0.70) 
                grad_top = bloque_bottom - grad_h
                grad_w   = nw
                try:
                    import numpy as np
                    arr          = np.zeros((grad_h, grad_w, 4), dtype=np.uint8)
                    alphas       = (210 * (np.arange(grad_h) / grad_h) ** 1.3).astype(np.uint8)
                    arr[:, :, 3] = alphas[:, np.newaxis]
                    gradient     = Image.fromarray(arr, "RGBA")
                except ImportError:
                    gradient = Image.new("RGBA", (grad_w, grad_h), (0, 0, 0, 0))
                    gd = ImageDraw.Draw(gradient)
                    for row in range(grad_h):
                        alpha = int(210 * (row / grad_h) ** 1.3)
                        gd.line([(0, row), (grad_w, row)], fill=(0, 0, 0, alpha))

                canvas_rgba = canvas.convert("RGBA")
                canvas_rgba.paste(gradient, (foto_x, grad_top), gradient)
                canvas = canvas_rgba.convert("RGB")

            draw = ImageDraw.Draw(canvas)

            # 3. TEXTOS Y POSICIONES
            col_inner_w = int(col_w * 0.85)

            if n <= 2:
                pct_size_base    = 95  
                pill_size_base   = 20
                nombre_size_base = 30
                # Ajuste drástico para formato story para no tapar la cara
                y_offset_factor  = 0.22 if format_key == "story" else 0.32
                gap_pill         = 0.04
            else:
                pct_size_base    = 70
                pill_size_base   = 16
                nombre_size_base = 24
                # Ajuste drástico para formato story para no tapar la cara
                y_offset_factor  = 0.18 if format_key == "story" else 0.26
                gap_pill         = 0.02

            pct_size    = max(20, int(pct_size_base    * text_multiplier))
            pill_size   = max(10, int(pill_size_base   * text_multiplier))
            nombre_size = max(12, int(nombre_size_base * text_multiplier))

            # Ajuste dinámico de %
            pct_str  = _fmt_pct(pct)
            pct_font = load_font(pct_size, bold=True, font_path=font_bold_path)
            pct_bbox = draw.textbbox((0, 0), pct_str, font=pct_font)
            pct_w    = pct_bbox[2] - pct_bbox[0]
            pct_h    = pct_bbox[3] - pct_bbox[1]

            while pct_w > col_inner_w and pct_size > 30:
                pct_size  -= 4
                pct_font   = load_font(pct_size, bold=True, font_path=font_bold_path)
                pct_bbox   = draw.textbbox((0, 0), pct_str, font=pct_font)
                pct_w      = pct_bbox[2] - pct_bbox[0]
                pct_h      = pct_bbox[3] - pct_bbox[1]

            text_start_y = bloque_bottom - int(bloque_h * y_offset_factor)
            pct_x = col_center_x - pct_w // 2
            draw.text((pct_x, text_start_y), pct_str, font=pct_font, fill=TEXT_COLOR)

            # Calculamos la posición de los votos con el gap definido
            votos_str = _fmt_votos(cand.get("votos"))
            pill_y = text_start_y + pct_h + int(bloque_h * gap_pill) 

            if votos_str:
                if not votos_str.endswith("VOTOS"):
                    votos_str += " VOTOS"

                pill_font      = load_font(pill_size, bold=True, font_path=font_bold_path)
                pill_text_bbox = draw.textbbox((0, 0), votos_str, font=pill_font)
                pill_text_w    = pill_text_bbox[2] - pill_text_bbox[0]
                pill_text_h    = pill_text_bbox[3] - pill_text_bbox[1]

                while pill_text_w + 28 > col_inner_w and pill_size > 10:
                    pill_size      -= 2
                    pill_font       = load_font(pill_size, bold=True, font_path=font_bold_path)
                    pill_text_bbox  = draw.textbbox((0, 0), votos_str, font=pill_font)
                    pill_text_w     = pill_text_bbox[2] - pill_text_bbox[0]
                    pill_text_h     = pill_text_bbox[3] - pill_text_bbox[1]

                pill_pad_x = 14
                pill_pad_y = 8
                pill_w     = pill_text_w + pill_pad_x * 2
                pill_h     = pill_text_h + pill_pad_y * 2
                pill_x     = col_center_x - pill_w // 2

                draw.rectangle([pill_x, pill_y, pill_x + pill_w, pill_y + pill_h], fill=RED)
                draw.text(
                    (pill_x + pill_pad_x, pill_y + pill_pad_y - pill_text_bbox[1]),
                    votos_str, font=pill_font, fill=WHITE,
                )
                nombre_y = pill_y + pill_h + int(bloque_h * 0.02)
            else:
                nombre_y = pill_y

            nombre = (cand.get("nombre") or "").strip().upper()
            if nombre:
                nombre_font = load_font(nombre_size, bold=True, font_path=font_bold_path)
                lines       = wrap_text(nombre, nombre_font, col_inner_w, draw)

                while len(lines) > 2 and nombre_size > 10:
                    nombre_size -= 2
                    nombre_font  = load_font(nombre_size, bold=True, font_path=font_bold_path)
                    lines        = wrap_text(nombre, nombre_font, col_inner_w, draw)
                lines = lines[:2]

                lh_bbox = draw.textbbox((0, 0), "Ag", font=nombre_font)
                line_h  = (lh_bbox[3] - lh_bbox[1]) * 1.2

                for j, ln in enumerate(lines):
                    bb = draw.textbbox((0, 0), ln, font=nombre_font)
                    lw = bb[2] - bb[0]
                    lx = col_center_x - lw // 2
                    ly = nombre_y + int(j * line_h)
                    draw.text((lx, ly), ln, font=nombre_font, fill=TEXT_COLOR)

        else:
            # ── MODO VERTICAL (N>3): Barra gruesa fondo, texto azul oscuro superpuesto ─
            draw = ImageDraw.Draw(canvas)
            TEXT_DARK = (10, 28, 54) # Azul oscuro/navy de la imagen de referencia
            
            # 1. Barra de color detrás de la foto y el texto
            bar_max_h = int(bloque_h * 0.85) # La barra más alta ocupa hasta un 85% de la columna
            bar_h = int(bar_max_h * (pct / max_pct)) if max_pct > 0 else 0
            bar_w = int(col_w_int * 0.85)
            bar_x = col_left + (col_w_int - bar_w) // 2
            bar_bot_y = bloque_bottom
            bar_top_y = bloque_bottom - bar_h

            if bar_h > 5:
                try:
                    draw.rounded_rectangle(
                        [bar_x, bar_top_y, bar_x + bar_w, bar_bot_y],
                        radius=15, fill=bar_color
                    )
                    # Quitar el borde redondeado de abajo
                    draw.rectangle([bar_x, bar_bot_y - 20, bar_x + bar_w, bar_bot_y], fill=bar_color)
                except AttributeError:
                    draw.rectangle([bar_x, bar_top_y, bar_x + bar_w, bar_bot_y], fill=bar_color)

            # 2. Porcentaje (Horizontal, debajo del nombre)
            pct_str = _fmt_pct(pct)
            pct_size_v = max(24, int(65 * text_multiplier)) # Letra mucho más grande
            pct_font_v = load_font(pct_size_v, bold=True, font_path=font_bold_path)
            
            pct_bbox = draw.textbbox((0, 0), pct_str, font=pct_font_v)
            pct_w = pct_bbox[2] - pct_bbox[0]
            pct_h = pct_bbox[3] - pct_bbox[1]
            
            # Altura fija horizontal general para los porcentajes (alineados como en referencia)
            fixed_pct_y = bloque_top + int(bloque_h * 0.46) 
            pct_x = col_center_x - pct_w // 2
            
            draw.text((pct_x, fixed_pct_y), pct_str, font=pct_font_v, fill=TEXT_DARK)

            # 3. Nombre (Rotado 90° hacia arriba) - Nombre Regular + Apellido Bold
            nombre = (cand.get("nombre") or "").strip().upper()

            # Cargar fuentes separadas para nombre (regular) y apellido (bold)
            lft_regular = os.path.join(FONTS_DIR, "LFTEtica-Regular.ttf")
            font_regular_path = lft_regular if os.path.exists(lft_regular) else font_path

            nombre_size_v = max(18, int(45 * text_multiplier))
            nombre_font_regular = load_font(nombre_size_v, bold=False, font_path=font_regular_path)
            nombre_font_bold = load_font(nombre_size_v, bold=True, font_path=font_bold_path)

            if nombre:
                # Dividir en NOMBRE (primera palabra) y APELLIDO (resto)
                words = nombre.split(" ")
                if len(words) >= 2:
                    primer_nombre = words[0]
                    apellidos = " ".join(words[1:])
                else:
                    primer_nombre = nombre
                    apellidos = ""

                # Lienzo temporal para girar (mas ancho para acomodar 2 lineas)
                tmp_w = int(bloque_h * 0.42)
                tmp_h = int(col_w_int * 0.8)
                tmp = Image.new("RGBA", (tmp_w, tmp_h), (0, 0, 0, 0))
                tmp_draw = ImageDraw.Draw(tmp)

                lh_bbox = tmp_draw.textbbox((0, 0), "Ag", font=nombre_font_bold)
                line_h = (lh_bbox[3] - lh_bbox[1]) * 1.1

                # Cuantas lineas
                num_lines = 2 if apellidos else 1
                total_h = line_h * num_lines
                y_start = (tmp_h - total_h) // 2

                # Linea 1: nombre en REGULAR
                bb1 = tmp_draw.textbbox((0, 0), primer_nombre, font=nombre_font_regular)
                lw1 = bb1[2] - bb1[0]
                lx1 = tmp_w - lw1 - 5
                ly1 = y_start
                tmp_draw.text((lx1, ly1), primer_nombre, font=nombre_font_regular, fill=TEXT_DARK)

                # Linea 2: apellido en BOLD
                if apellidos:
                    bb2 = tmp_draw.textbbox((0, 0), apellidos, font=nombre_font_bold)
                    lw2 = bb2[2] - bb2[0]
                    lx2 = tmp_w - lw2 - 5
                    ly2 = y_start + line_h
                    tmp_draw.text((lx2, ly2), apellidos, font=nombre_font_bold, fill=TEXT_DARK)

                # Rotar 90° antihorario
                tmp_rot = tmp.rotate(90, expand=True)
                rot_w, rot_h = tmp_rot.size

                paste_x = col_center_x - rot_w // 2
                paste_y = fixed_pct_y - rot_h - int(bloque_h * 0.02)

                canvas_rgba = canvas.convert("RGBA")
                canvas_rgba.paste(tmp_rot, (paste_x, int(paste_y)), tmp_rot)
                canvas = canvas_rgba.convert("RGB")
                draw = ImageDraw.Draw(canvas)

            # 4. Foto del Candidato y Degradado Inferior
            foto = cand.get("foto")
            if foto is not None:
                # Limitamos la foto para que no tape el porcentaje
                foto_max_h = bloque_bottom - (fixed_pct_y + pct_h + int(bloque_h * 0.02))
                foto_max_h = max(int(bloque_h * 0.40), foto_max_h) 
                
                iw, ih = foto.size
                nw = col_w_int
                target_h = int(ih * (nw / iw))
                
                foto_scaled = foto.resize((nw, target_h), Image.LANCZOS)
                
                if target_h > foto_max_h:
                    foto_scaled = foto_scaled.crop((0, 0, nw, foto_max_h))
                    target_h = foto_max_h
                    
                foto_x = col_left
                foto_y = bloque_bottom - target_h
                
                if foto_scaled.mode == "RGBA":
                    canvas_rgba = canvas.convert("RGBA")
                    canvas_rgba.paste(foto_scaled, (foto_x, foto_y), foto_scaled)
                    canvas = canvas_rgba.convert("RGB")
                else:
                    canvas.paste(foto_scaled, (foto_x, foto_y))

                # --- AGREGAR DEGRADADO NEGRO INFERIOR ---
                grad_h   = int(target_h * 0.60) # Altura del degradado
                grad_top = bloque_bottom - grad_h
                grad_w   = nw
                try:
                    import numpy as np
                    arr          = np.zeros((grad_h, grad_w, 4), dtype=np.uint8)
                    # Opacidad un poco más suave (180) para el diseño de >3 candidatos
                    alphas       = (180 * (np.arange(grad_h) / grad_h) ** 1.3).astype(np.uint8) 
                    arr[:, :, 3] = alphas[:, np.newaxis]
                    gradient     = Image.fromarray(arr, "RGBA")
                except ImportError:
                    gradient = Image.new("RGBA", (grad_w, grad_h), (0, 0, 0, 0))
                    gd = ImageDraw.Draw(gradient)
                    for row in range(grad_h):
                        alpha = int(180 * (row / grad_h) ** 1.3)
                        gd.line([(0, row), (grad_w, row)], fill=(0, 0, 0, alpha))

                canvas_rgba = canvas.convert("RGBA")
                canvas_rgba.paste(gradient, (foto_x, grad_top), gradient)
                canvas = canvas_rgba.convert("RGB")
                # ----------------------------------------

                draw = ImageDraw.Draw(canvas)

                # === CUADRO ROJO DE VOTOS (parte inferior de cada candidato) ===

                # === CUADRO ROJO DE VOTOS (parte inferior de cada candidato) ===
            votos_str_v = _fmt_votos(cand.get("votos"))
            if votos_str_v:
                pill_size_v = max(18, int(18 * text_multiplier))
                pill_font_v = load_font(pill_size_v, bold=True, font_path=font_bold_path)

                pill_text_bbox = draw.textbbox((0, 0), votos_str_v, font=pill_font_v)
                pill_text_w = pill_text_bbox[2] - pill_text_bbox[0]
                pill_text_h = pill_text_bbox[3] - pill_text_bbox[1]

                # Achicar si excede ancho de columna
                while pill_text_w + 20 > col_w_int and pill_size_v > 8:
                    pill_size_v -= 1
                    pill_font_v = load_font(pill_size_v, bold=True, font_path=font_bold_path)
                    pill_text_bbox = draw.textbbox((0, 0), votos_str_v, font=pill_font_v)
                    pill_text_w = pill_text_bbox[2] - pill_text_bbox[0]
                    pill_text_h = pill_text_bbox[3] - pill_text_bbox[1]

                pill_pad_x = 10
                pill_pad_y = 6
                pill_w_v = pill_text_w + pill_pad_x * 2
                pill_h_v = pill_text_h + pill_pad_y * 2

                # Posicion: parte inferior del bloque, centrado en cada columna
                pill_x_v = col_center_x - pill_w_v // 2
                pill_y_v = bloque_bottom - pill_h_v - int(bloque_h * 0.015)

                draw.rectangle(
                    [pill_x_v, pill_y_v, pill_x_v + pill_w_v, pill_y_v + pill_h_v],
                    fill=RED,
                )
                draw.text(
                    (pill_x_v + pill_pad_x, pill_y_v + pill_pad_y - pill_text_bbox[1]),
                    votos_str_v, font=pill_font_v, fill=WHITE,
                )



    # =========================================================
    # RECUADRO BOLETIN (esquina inferior derecha del cuadro gris)
    # =========================================================
    if boletin_text and boletin_text.strip():
        draw = ImageDraw.Draw(canvas)
        boletin_str = boletin_text.strip().upper()

        # Tamano de fuente segun formato
        if format_key == "post":
            boletin_size = 28
        else:
            boletin_size = 30

        boletin_font = load_font(boletin_size, bold=True, font_path=font_bold_path)

        # Medir texto
        bbox = draw.textbbox((0, 0), boletin_str, font=boletin_font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        pad_x = 18
        pad_y = 10

        box_w = text_w + pad_x * 2
        box_h = text_h + pad_y * 2

        # Posicion: DEBAJO del cuadro gris, alineado a la derecha
        margin_x = int(canvas_w * 0.015)
        margin_y = int(canvas_h * 0.02)  # separacion entre cuadro gris y boletin
        box_x = bloque_right - box_w - margin_x
        box_y = bloque_bottom + margin_y

        # Rectangulo rojo
        draw.rectangle(
            [box_x, box_y, box_x + box_w, box_y + box_h],
            fill=RED,
        )

        # Texto blanco
        draw.text(
            (box_x + pad_x, box_y + pad_y - bbox[1]),
            boletin_str,
            font=boletin_font,
            fill=WHITE,
        )
    return canvas
# ============================================================
# API PÚBLICA
# ============================================================

def generate_card_from_image(
    source_image,
    section,
    title,
    template="classic",
    format_key="post",
    fondo_name=None,
    seccion_con_icono=False,
    show_cta=False,
    show_social_icons=True,
    zoom=1.0,
    offset_x=0.5,
    offset_y=0.5,
    font_path=None,
    output_path=None,
    logo_override=None,
    logo_variant=None,
    sticker_position="bottom",
    author="",
    summary="",
    author_image=None,
    title_size_multiplier=1.0

):
    """
    Genera la tarjeta usando la plantilla seleccionada.

    Args:
        template:   "classic" | "card" | "with_cta" | "attention" | "generic"
        format_key: "post" (1080x1350) | "story" (1080x1920)
        fondo_name: solo para template "generic". Si es None se autodetecta por sección.
        seccion_con_icono: True para usar sticker con icono de la sección.
        show_cta:   solo para template "generic".
        show_social_icons: solo para template "generic".
        zoom, offset_x, offset_y: control de encuadre de la foto.
        font_path: ruta a archivo .ttf personalizado. Si no se proporciona, busca en assets/fonts/
        output_path: si se especifica, guarda el PNG en esa ruta y devuelve None.

    Returns:
        PIL.Image si output_path es None, o None si se guardó en archivo.
    """
    if format_key not in FORMATS:
        format_key = DEFAULT_FORMAT

    common_kwargs = dict(
        format_key=format_key,
        seccion_con_icono=seccion_con_icono,
        zoom=zoom,
        offset_x=offset_x,
        offset_y=offset_y,
        font_path=font_path,
        title_size_multiplier=title_size_multiplier
    )
    # logo_override solo aplica a plantillas que muestran logo de sección
    # logo_override y logo_variant solo aplican a plantillas que muestran logo de sección
    logo_kwargs = dict(logo_override=logo_override, logo_variant=logo_variant)

    if template == "classic":
        img = render_classic(source_image, section, title, **common_kwargs, **logo_kwargs)

    elif template == "card":
        img = render_card(source_image, section, title, **common_kwargs)

    elif template == "with_cta":
        img = render_with_cta(source_image, section, title, **common_kwargs)


    elif template == "lo_ultimo":
        img = render_classic_overlay(source_image, section, title,
                                     overlay_name="lo-ultimo.png", **common_kwargs)

    elif template == "atencion":
        img = render_classic_overlay(source_image, section, title,
                                     overlay_name="atencion.png", **common_kwargs)

    elif template == "en_vivo_simple":
        img = render_classic_overlay(source_image, section, title,
                                     overlay_name="en-vivo.png", **common_kwargs)
    
    elif template == "ultima_hora":
        img = render_classic_overlay(source_image, section, title,
                                     overlay_name="ultima_hora.png", **common_kwargs)
        
    elif template == "story_minimal":
        img = render_story_minimal(source_image, section, title, **common_kwargs)

    elif template == "en_vivo":
        img = render_en_vivo(source_image, section, title, **common_kwargs, **logo_kwargs)

    elif template == "columnista":
        img = render_columnista(
            source_image, section, title,
            author=author,
            summary=summary,
            author_image=author_image,
            **common_kwargs,
            **logo_kwargs,
        )

    elif template == "generic":
        resolved_fondo = fondo_name or suggest_fondo_for_section(section)
        img = render_generic(
            source_image, section, title,
            fondo_name=resolved_fondo,
            show_cta=show_cta,
            show_social_icons=show_social_icons,
            logo_override=logo_override,
            logo_variant=logo_variant,
            sticker_position=sticker_position,
            **common_kwargs,
        )

    elif template == "elecciones_2026_post":
        img = render_elecciones_2026_post(source_image, section, title, **common_kwargs)

    elif template == "elecciones_2026_story":
        img = render_elecciones_2026_story(source_image, section, title, **common_kwargs)

    elif template == "elecciones_2026_ultima_hora_post":
        img = render_elecciones_2026_ultima_hora_post(source_image, section, title, **common_kwargs)

    elif template == "elecciones_2026_ultima_hora_story":
        img = render_elecciones_2026_ultima_hora_story(source_image, section, title, **common_kwargs)

    elif template == "envivo_elecciones_post":
        img = render_envivo_elecciones_post(source_image, section, title, **common_kwargs)

    elif template == "envivo_elecciones_story":
        img = render_envivo_elecciones_story(source_image, section, title, **common_kwargs)

    elif template == "elecciones_2026_card_post":
        img = render_elecciones_2026_card_post(source_image, section, title, **common_kwargs)

    else:
        valid = list(TEMPLATES.keys()) + ["generic"]
        raise ValueError(f"Plantilla desconocida: '{template}'. Opciones: {valid}")

    if output_path:
        img.save(output_path, "PNG", quality=95)
        return None
    return img


def generate_card(image_url, section, title, **kwargs):
    """Versión que descarga la imagen desde URL primero."""
    source_image = fetch_image(image_url)
    return generate_card_from_image(source_image, section, title, **kwargs)
