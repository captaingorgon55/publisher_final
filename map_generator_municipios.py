"""
map_generator_municipios.py
Genera mapas electorales a nivel de MUNICIPIO para Colombia 2026.

Funciones principales:
  - render_mapa_municipios_depto(depto, municipios, candidatos, boletin, meta)
      → Tarjeta 1080x1350 con el mapa de UN departamento coloreado por municipio

  - render_carrusel_municipios(depto, municipios, candidatos, boletin, meta)
      → Lista de PIL Images [mapa_depto]

Usa: colombia_municipios.geojson (campos: dpt, name)
Fondo: Fondo-mapas.jpg (o resultados-elecciones-post.jpg como fallback)
"""

import io, json, zipfile, logging, unicodedata, re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import geopandas as gpd
from PIL import Image, ImageDraw, ImageFont, ImageOps
from pathlib import Path

log = logging.getLogger("map_generator_municipios")

_HERE         = Path(__file__).parent
ASSETS_DIR    = _HERE / "assets"
FONTS_DIR     = ASSETS_DIR / "fonts"
FONDOS_DIR    = ASSETS_DIR / "fondos"
CANDS_DIR     = ASSETS_DIR / "candidatos"
MUN_GEOJSON   = _HERE / "colombia_municipios.geojson"
DEPTO_GEOJSON = _HERE / "colombia_deptos.geojson"

W, H = 1080, 1350
BOX_X1, BOX_Y1 = 108,  59
BOX_X2, BOX_Y2 = 976, 1134
BOX_W = BOX_X2 - BOX_X1
BOX_H = BOX_Y2 - BOX_Y1

LOGO_BOTTOM = 210
TITLE_Y     = LOGO_BOTTOM + 55

BAR_COLORS = {
    "Amarillo": (255, 215,   0),
    "Azul":     (100, 130, 200),
    "Rojo":     (227,  27,  35),
    "Verde":    ( 50, 180,  90),
    "Naranja":  (255, 140,  40),
    "Morado":   (132,   0, 184),
    "Rosa":     (240, 110, 170),
}

SEGUNDA_VUELTA = {
    "abelardo-de-la-espriella": {
        "nombre":    "ABELARDO DE LA ESPRIELLA",
        "color_key": "Rojo",
    },
    "ivan-cepeda": {
        "nombre":    "IVÁN CEPEDA",
        "color_key": "Morado",
    },
}

WHITE = (255, 255, 255)
DARK  = ( 14,  28,  46)
RED   = (227,  27,  35)
GRAY  = (210, 210, 213)

# Mapeo nombres departamento en GeoJSON → nombres normalizados
DEPTO_GEO_MAP = {
    "AMAZONAS":                             "AMAZONAS",
    "ANTIOQUIA":                            "ANTIOQUIA",
    "ARAUCA":                               "ARAUCA",
    "ARCHIPIELAGO DE SAN ANDRES PROVIDENCIA Y SANTA CATALINA": "SAN ANDRÉS Y PROVIDENCIA",
    "ATLANTICO":                            "ATLÁNTICO",
    "BOLIVAR":                              "BOLÍVAR",
    "BOYACA":                               "BOYACÁ",
    "CALDAS":                               "CALDAS",
    "CAQUETA":                              "CAQUETÁ",
    "CASANARE":                             "CASANARE",
    "CAUCA":                                "CAUCA",
    "CESAR":                                "CESAR",
    "CHOCO":                                "CHOCÓ",
    "CORDOBA":                              "CÓRDOBA",
    "CUNDINAMARCA":                         "CUNDINAMARCA",
    "GUAINIA":                              "GUAINÍA",
    "GUAVIARE":                             "GUAVIARE",
    "HUILA":                                "HUILA",
    "LA GUAJIRA":                           "LA GUAJIRA",
    "MAGDALENA":                            "MAGDALENA",
    "META":                                 "META",
    "NARIÑO":                               "NARIÑO",
    "NORTE DE SANTANDER":                   "NORTE DE SANTANDER",
    "PUTUMAYO":                             "PUTUMAYO",
    "QUINDIO":                              "QUINDÍO",
    "RISARALDA":                            "RISARALDA",
    "SANTAFE DE BOGOTA D.C":               "BOGOTÁ D.C.",
    "SANTANDER":                            "SANTANDER",
    "SUCRE":                                "SUCRE",
    "TOLIMA":                               "TOLIMA",
    "VALLE DEL CAUCA":                      "VALLE DEL CAUCA",
    "VAUPES":                               "VAUPÉS",
    "VICHADA":                              "VICHADA",
}


def _norm(s):
    """Normaliza texto: mayúsculas sin acentos."""
    if not s: return ""
    s = s.upper().strip()
    s = "".join(c for c in unicodedata.normalize("NFD", s)
                if unicodedata.category(c) != "Mn")
    return s


def _f(size, bold=False):
    for p in [
        FONTS_DIR / ("LFTEtica-Bold.ttf"  if bold else "LFTEtica-Regular.ttf"),
        FONTS_DIR / ("OpenSans-Bold.ttf"   if bold else "OpenSans-Regular.ttf"),
        FONTS_DIR / "abriltitling.ttf",
    ]:
        if p.exists():
            try: return ImageFont.truetype(str(p), size)
            except: pass
    return ImageFont.load_default()


def _base():
    for nombre in ["Fondo-mapas", "fondo-mapas", "resultados-elecciones-post"]:
        for ext in [".jpg",".jpeg",".png"]:
            p = FONDOS_DIR / f"{nombre}{ext}"
            if p.exists():
                return Image.open(p).convert("RGB").resize((W,H), Image.LANCZOS)
    c = Image.new("RGB",(W,H),(219,219,219))
    ImageDraw.Draw(c).rectangle([BOX_X1,BOX_Y1,BOX_X2,BOX_Y2], fill=(202,202,202))
    return c


def _rgb_mpl(rgb): return (rgb[0]/255, rgb[1]/255, rgb[2]/255)


def _get_gdf_municipios():
    """Carga el GeoJSON de municipios."""
    if MUN_GEOJSON.exists():
        return gpd.read_file(str(MUN_GEOJSON))
    raise FileNotFoundError(f"No se encontró {MUN_GEOJSON}. Copiá colombia_municipios.geojson al proyecto.")


def _get_slug(nombre_up):
    for slug, info in SEGUNDA_VUELTA.items():
        partes = info["nombre"].upper().split()
        if any(len(p)>3 and p in nombre_up for p in partes):
            return slug
    return None


def _get_color(nombre_up):
    slug = _get_slug(nombre_up)
    if slug:
        return BAR_COLORS.get(SEGUNDA_VUELTA[slug]["color_key"], GRAY)
    return GRAY


def _normalizar_depto_geo(dpt_raw):
    """Convierte el nombre de departamento del GeoJSON al nombre normalizado."""
    dpt_up = dpt_raw.upper().strip()
    if dpt_up in DEPTO_GEO_MAP:
        return DEPTO_GEO_MAP[dpt_up]
    # Fallback: quitar acentos y comparar
    dpt_norm = _norm(dpt_up)
    for k, v in DEPTO_GEO_MAP.items():
        if _norm(k) == dpt_norm:
            return v
    return dpt_up


# ── Render mapa de UN departamento por municipios ─────────────

def render_mapa_municipios_depto(
    depto_nombre: str,
    municipios: list,
    candidatos_globales: list,
    boletin_text: str = "",
    meta: dict = None,
    modo_valor: str = "porcentaje",
) -> Image.Image:
    """
    Genera tarjeta 1080x1350 con el mapa de un departamento
    coloreado por candidato ganador en cada municipio.

    Args:
        depto_nombre: Nombre del departamento (ej: "CUNDINAMARCA")
        municipios: Lista de dicts con formato del parser:
            [{ nombre, primer_lugar: { candidato, porcentaje, votos } }, ...]
        candidatos_globales: Lista de candidatos con porcentajes nacionales
        boletin_text: Texto del boletín
        meta: Dict con mesas_reportadas, boletin, etc.
        modo_valor: "porcentaje" o "votos" para etiquetas
    """
    canvas = _base()
    draw   = ImageDraw.Draw(canvas)
    cx     = (BOX_X1 + BOX_X2) // 2

    # Normalizar nombre del departamento
    depto_up   = depto_nombre.upper().strip()
    depto_disp = depto_up  # para mostrar

    # Título
    sub = f"{meta['mesas_reportadas']:.0f}% escrutado" if meta and meta.get("mesas_reportadas") else ""
    draw.text((cx, TITLE_Y - 14), depto_disp,
              font=_f(46, True), fill=DARK, anchor="mm")
    draw.text((cx, TITLE_Y + 30), "Resultados por municipio",
              font=_f(24, False), fill=(100,100,100), anchor="mm")
    if sub:
        draw.text((cx, TITLE_Y + 58), sub,
                  font=_f(20, False), fill=(130,130,130), anchor="mm")

    # Cargar GDF y filtrar departamento
    gdf_all = _get_gdf_municipios()

    # Mapear nombre del departamento al formato del GeoJSON
    depto_geo = None
    depto_norm = _norm(depto_up)
    for dpt_raw in gdf_all['dpt'].unique():
        dpt_norm = _norm(dpt_raw)
        if dpt_norm == depto_norm:
            depto_geo = dpt_raw
            break
        # Alias Bogotá
        if depto_norm in ("BOGOTA DC", "BOGOTA D C", "SANTAFE DE BOGOTA") and \
           _norm(dpt_raw) in ("SANTAFE DE BOGOTA DC", "BOGOTA"):
            depto_geo = dpt_raw
            break

    if not depto_geo:
        # Fallback: buscar por contenido
        for dpt_raw in gdf_all['dpt'].unique():
            if depto_norm[:6] in _norm(dpt_raw):
                depto_geo = dpt_raw
                break

    if not depto_geo:
        draw.text((cx, 700), f"No se encontró geometría\npara {depto_up}",
                  font=_f(28,True), fill=RED, anchor="mm")
        return canvas

    gdf = gdf_all[gdf_all['dpt'] == depto_geo].copy()

    # Índice municipio → datos
    mun_idx = {}
    for m in municipios:
        nombre_mun = _norm(m.get("nombre",""))
        mun_idx[nombre_mun] = m

    # Asignar colores
    colors = []
    for _, row in gdf.iterrows():
        nombre_geo = _norm(str(row.get("name","") or ""))
        dat = mun_idx.get(nombre_geo)
        if dat and dat.get("primer_lugar"):
            cand = dat["primer_lugar"]["candidato"].upper()
            rgb  = _get_color(cand)
        else:
            rgb = GRAY
        colors.append(_rgb_mpl(rgb))

    # Dimensiones del mapa dentro del cuadro
    HEADER_H = 95 if sub else 75
    CONTENT_Y = TITLE_Y + HEADER_H
    CONTENT_BOT = BOX_Y2 - 10

    MAP_W = BOX_W - 8
    MAP_H = CONTENT_BOT - CONTENT_Y
    MAP_X = BOX_X1 + 4

    # Render matplotlib
    dpi = 150
    fig, ax = plt.subplots(1,1, figsize=(MAP_W/dpi, MAP_H/dpi), facecolor='none')
    ax.set_facecolor('none')
    gdf.plot(ax=ax, color=colors, edgecolor='white', linewidth=0.6)

    # Labels
    try:
        from matplotlib import patheffects as pe
        for _, row in gdf.iterrows():
            nombre_geo = _norm(str(row.get("name","") or ""))
            dat = mun_idx.get(nombre_geo)
            if dat and dat.get("primer_lugar"):
                p1  = dat["primer_lugar"]
                pct = p1.get("porcentaje",0)
                if pct >= 1:
                    try:
                        c = row.geometry.centroid
                        if modo_valor == "votos":
                            v = int(p1.get("votos",0))
                            lbl = f"{v:,}".replace(",",".") if v else f"{pct:.0f}%"
                        else:
                            lbl = f"{pct:.0f}%"
                        ax.annotate(lbl, xy=(c.x,c.y),
                            ha='center', va='center',
                            fontsize=4.5, fontweight='bold', color='white',
                            path_effects=[pe.withStroke(linewidth=1.5, foreground='black')])
                    except: pass
    except: pass

    ax.axis('off')
    fig.tight_layout(pad=0)
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight',
                pad_inches=0.01, transparent=True)
    plt.close(fig)
    buf.seek(0)
    mapa = Image.open(buf).convert("RGBA")
    mapa = mapa.resize((MAP_W, MAP_H), Image.LANCZOS)

    rgba = canvas.convert("RGBA")
    rgba.paste(mapa, (MAP_X, CONTENT_Y), mapa)
    canvas = rgba.convert("RGB")

    # Badge boletín
    if boletin_text:
        draw = ImageDraw.Draw(canvas)
        font = _f(20, True)
        t    = boletin_text.strip().upper()
        bb   = draw.textbbox((0,0), t, font=font)
        bw, bh = bb[2]-bb[0]+24, bb[3]-bb[1]+14
        bx = BOX_X2 - bw - 12
        by = BOX_Y2 + 20
        draw.rectangle([bx, by, bx+bw, by+bh], fill=RED)
        draw.text((bx+12, by+7-bb[1]), t, font=font, fill=WHITE)

    return canvas


# ── Carrusel de departamento ──────────────────────────────────

def render_carrusel_municipios(depto_nombre, municipios, candidatos_globales,
                                boletin_text="", meta=None, modo_valor="porcentaje"):
    """Genera [tarjeta_mapa_depto]."""
    t = render_mapa_municipios_depto(
        depto_nombre, municipios, candidatos_globales,
        boletin_text, meta, modo_valor
    )
    return [t]


# ── Listar departamentos disponibles ─────────────────────────

def listar_deptos_disponibles():
    """Retorna lista de departamentos disponibles en el GeoJSON."""
    try:
        gdf = _get_gdf_municipios()
        return sorted([_normalizar_depto_geo(d) for d in gdf['dpt'].unique()])
    except Exception:
        return []
