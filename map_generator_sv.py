import io, json, zipfile, logging, requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import geopandas as gpd
from PIL import Image, ImageDraw, ImageFont, ImageOps
from pathlib import Path

log = logging.getLogger("map_generator_sv")

_HERE        = Path(__file__).parent
ASSETS_DIR   = _HERE / "assets"
FONTS_DIR    = ASSETS_DIR / "fonts"
FONDOS_DIR   = ASSETS_DIR / "fondos"
CANDS_DIR    = ASSETS_DIR / "candidatos"
GEOJSON_PATH = _HERE / "colombia_deptos.geojson"
GEOJSON_URL  = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector"
    "/master/geojson/ne_10m_admin_1_states_provinces.geojson"
)

W, H = 1080, 1350

BOX_X1, BOX_Y1 = 108,  59
BOX_X2, BOX_Y2 = 976, 1134
BOX_W = BOX_X2 - BOX_X1
BOX_H = BOX_Y2 - BOX_Y1

LOGO_BOTTOM = 210
TITLE_Y     = LOGO_BOTTOM + 55
TITLE_H     = 65
CONTENT_Y   = TITLE_Y + TITLE_H + 20
CONTENT_BOT = BOX_Y2 - 20

LEY_X = BOX_X1 + 100
LEY_W = 200
MAP_W = 720
MAP_H = int(MAP_W * 1.20)
MAP_X = BOX_X2 - MAP_W - 10
MAP_Y = CONTENT_Y

if MAP_Y + MAP_H > CONTENT_BOT:
    MAP_H = CONTENT_BOT - MAP_Y
    MAP_W = int(MAP_H / 1.20)
    MAP_X = BOX_X2 - MAP_W - 10

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
        "display_l1":"ABELARDO DE LA",
        "display_l2":"ESPRIELLA",
        "color_key": "Rojo",
    },
    "ivan-cepeda": {
        "nombre":    "IVÁN CEPEDA",
        "display_l1":"IVÁN",
        "display_l2":"CEPEDA",
        "color_key": "Morado",
    },
}

WHITE = (255, 255, 255)
DARK  = ( 14,  28,  46)
NAVY  = ( 10,  15,  30)
RED   = (227,  27,  35)
GRAY  = (210, 210, 213)

DEPTO_NAME_MAP = {
    "Nariño":"NARIÑO","Putumayo":"PUTUMAYO","Chocó":"CHOCÓ",
    "Guainía":"GUAINÍA","Vaupés":"VAUPÉS","Amazonas":"AMAZONAS",
    "La Guajira":"LA GUAJIRA","Cesar":"CESAR",
    "Norte de Santander":"NORTE DE SANTANDER","Arauca":"ARAUCA",
    "Boyacá":"BOYACÁ","Vichada":"VICHADA","Cauca":"CAUCA",
    "Valle del Cauca":"VALLE DEL CAUCA","Antioquia":"ANTIOQUIA",
    "Córdoba":"CÓRDOBA","Sucre":"SUCRE","Bolívar":"BOLÍVAR",
    "Atlántico":"ATLÁNTICO","Magdalena":"MAGDALENA",
    "San Andrés y Providencia":"SAN ANDRÉS Y PROVIDENCIA",
    "Caquetá":"CAQUETÁ","Huila":"HUILA","Guaviare":"GUAVIARE",
    "Caldas":"CALDAS","Casanare":"CASANARE","Meta":"META",
    "Bogota":"BOGOTÁ D.C.","Santander":"SANTANDER","Tolima":"TOLIMA",
    "Quindío":"QUINDÍO","Cundinamarca":"CUNDINAMARCA","Risaralda":"RISARALDA",
}


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
    for ext in [".jpg",".jpeg",".png"]:
        p = FONDOS_DIR / f"resultados-elecciones-post{ext}"
        if p.exists():
            return Image.open(p).convert("RGB").resize((W,H), Image.LANCZOS)
    c = Image.new("RGB",(W,H),(219,219,219))
    ImageDraw.Draw(c).rectangle([BOX_X1,BOX_Y1,BOX_X2,BOX_Y2],fill=(202,202,202))
    return c


def _rgb_mpl(rgb): return (rgb[0]/255, rgb[1]/255, rgb[2]/255)


def _gdf():
    if GEOJSON_PATH.exists():
        return gpd.read_file(str(GEOJSON_PATH))
    r = requests.get(GEOJSON_URL, timeout=60)
    r.raise_for_status()
    data = r.json()
    col  = [f for f in data["features"]
            if f["properties"].get("admin")=="Colombia"
            or f["properties"].get("iso_a2")=="CO"]
    with open(GEOJSON_PATH,"w",encoding="utf-8") as fh:
        json.dump({"type":"FeatureCollection","features":col},fh)
    return gpd.read_file(str(GEOJSON_PATH))

def _foto_circ(slug, size, color_rgb):
    for ext in [".png", ".jpg"]:
        p = CANDS_DIR / f"{slug}{ext}"

        if p.exists():
            img = Image.open(p).convert("RGBA")

            # Espacio alrededor de la imagen
            pad_size = int(min(img.width, img.height) * 0.12)
            img = ImageOps.expand(
                img,
                border=pad_size,
                fill=(0, 0, 0, 0)
            )

            # Espacio inferior para no cortar hombros
            extra_bottom = int(img.height * 0.15)
            tmp = Image.new(
                "RGBA",
                (img.width, img.height + extra_bottom),
                (0, 0, 0, 0)
            )
            tmp.paste(img, (0, 0), img)
            img = tmp

            # Escalar manteniendo proporción y ocupando casi todo el círculo
            img = ImageOps.contain(
                img,
                (size +100 , size + 100),
                Image.LANCZOS
            )

            # Escala de grises conservando transparencia
            alpha = img.getchannel("A")
            gray = ImageOps.grayscale(img.convert("RGB"))
            bw_img = Image.merge(
                "RGBA",
                (gray, gray, gray, alpha)
            )

            # Fondo del color del candidato
            bg = Image.new(
                "RGBA",
                (size, size),
                color_rgb + (255,)
            )

            # Posicionamiento
            Y_OFFSET = 10  # positivo baja, negativo sube

            x = (size - bw_img.width) // 2
            y = (size - bw_img.height) // 2 + Y_OFFSET

            bg.paste(bw_img, (x, y), bw_img)

            # Máscara circular suavizada
            mask_4x = Image.new(
                "L",
                (size * 4, size * 4),
                0
            )

            ImageDraw.Draw(mask_4x).ellipse(
                [0, 0, (size * 4) - 1, (size * 4) - 1],
                fill=255
            )

            mask = mask_4x.resize(
                (size, size),
                Image.LANCZOS
            )

            out = Image.new(
                "RGBA",
                (size, size),
                (0, 0, 0, 0)
            )

            out.paste(bg, (0, 0), mask)

            return out

    # Si no existe la imagen
    mask_4x = Image.new(
        "L",
        (size * 4, size * 4),
        0
    )

    ImageDraw.Draw(mask_4x).ellipse(
        [0, 0, (size * 4) - 1, (size * 4) - 1],
        fill=255
    )

    mask = mask_4x.resize(
        (size, size),
        Image.LANCZOS
    )

    bg = Image.new(
        "RGBA",
        (size, size),
        color_rgb + (255,)
    )

    out = Image.new(
        "RGBA",
        (size, size),
        (0, 0, 0, 0)
    )

    out.paste(bg, (0, 0), mask)

    return out

def _pegar_foto(canvas, slug, size, x, y, color_rgb):
    rgba_canvas = canvas.convert("RGBA")
    gap_pixels  = int(size * 0.06) + 1
    border_width = int(size * 0.04) + 1
    offset       = gap_pixels + border_width
    layer_sz     = size + offset*2
    layer_sz_4x  = layer_sz * 4
    ring_4x      = Image.new("RGBA", (layer_sz_4x,layer_sz_4x), (0,0,0,0))
    ImageDraw.Draw(ring_4x).ellipse(
        [0,0,layer_sz_4x-1,layer_sz_4x-1],
        outline=color_rgb+(255,), width=border_width*4
    )
    ring = ring_4x.resize((layer_sz,layer_sz), Image.LANCZOS)
    rgba_canvas.paste(ring, (x-offset, y-offset), ring)
    foto = _foto_circ(slug, size, color_rgb)
    rgba_canvas.paste(foto, (x,y), foto.split()[3])
    return rgba_canvas.convert("RGB")


def _badge(canvas, txt):
    if not txt: return canvas
    draw = ImageDraw.Draw(canvas)
    font = _f(20, True)
    t    = txt.strip().upper()
    bb   = draw.textbbox((0,0), t, font=font)
    bw, bh = bb[2]-bb[0]+24, bb[3]-bb[1]+14
    bx = BOX_X2 - bw - 12
    by = BOX_Y2 + 20
    draw.rectangle([bx, by, bx+bw, by+bh], fill=RED)
    draw.text((bx+12, by+7-bb[1]), t, font=font, fill=WHITE)
    return canvas


def _get_slug(nombre_up):
    """
    Busca el slug del candidato en SEGUNDA_VUELTA a partir de su nombre en mayúsculas.
    Acepta nombres parciales, con apellido compuesto, o con palabras extra (ej. 'CASTRO').
    """
    nombre_up = nombre_up.strip()
    for slug, info in SEGUNDA_VUELTA.items():
        partes_sv = info["nombre"].upper().split()
        partes_input = nombre_up.split()
        # Coincidencia exacta primero
        if info["nombre"].upper() == nombre_up:
            return slug
        # Todas las palabras del candidato registrado (de más de 3 letras) deben estar en el input
        palabras_clave = [p for p in partes_sv if len(p) > 3]
        if palabras_clave and all(p in partes_input for p in palabras_clave):
            return slug
        # Fallback: al menos una palabra clave de más de 4 letras está contenida como substring
        if any(len(p) > 4 and p in nombre_up for p in partes_sv):
            return slug
    return None


def _get_color(nombre_up):
    slug = _get_slug(nombre_up)
    if slug:
        return BAR_COLORS.get(SEGUNDA_VUELTA[slug]["color_key"], GRAY)
    return GRAY


def _recalcular_globales_desde_deptos(candidatos_globales, departamentos):
    """
    Si candidatos_globales no tiene porcentajes válidos para algún candidato de
    SEGUNDA_VUELTA, los recalcula sumando votos de los departamentos.
    Siempre devuelve una lista con una entrada por cada slug de SEGUNDA_VUELTA.
    """
    # Sumar votos por slug desde los departamentos
    votos_por_slug = {slug: 0 for slug in SEGUNDA_VUELTA}
    for d in departamentos:
        p1   = d.get("primer_lugar", {})
        cand = p1.get("candidato", "").upper()
        voto = int(p1.get("votos", 0))
        slug = _get_slug(cand)
        if slug:
            votos_por_slug[slug] += voto

    total = sum(votos_por_slug.values()) or 1

    # Construir mapa nombre_upper -> datos desde candidatos_globales existentes
    global_map = {}
    for c in (candidatos_globales or []):
        n = c.get("nombre", "").upper().strip()
        if n:
            global_map[n] = c
        # También indexar por slug si matchea
        slug = _get_slug(n)
        if slug:
            global_map[f"__slug__{slug}"] = c

    resultado = []
    for slug, info in SEGUNDA_VUELTA.items():
        nombre_sv = info["nombre"].upper()
        # Intentar encontrar en candidatos_globales
        match = (
            global_map.get(nombre_sv)
            or global_map.get(f"__slug__{slug}")
        )
        pct_existente   = float(match.get("porcentaje", 0)) if match else 0
        votos_existente = match.get("votos", "0")           if match else "0"

        # Si el porcentaje existente es 0, recalcular desde deptos
        if pct_existente == 0 and votos_por_slug[slug] > 0:
            votos_calc = votos_por_slug[slug]
            pct_calc   = round(votos_calc / total * 100, 2)
            resultado.append({
                "nombre":     nombre_sv,
                "porcentaje": pct_calc,
                "votos":      str(votos_calc),
            })
        else:
            resultado.append({
                "nombre":     nombre_sv,
                "porcentaje": pct_existente,
                "votos":      votos_existente,
            })

    return resultado


def render_mapa_sv(departamentos, candidatos_globales, boletin_text="", meta=None):
    # Siempre normalizar candidatos_globales usando deptos como fuente de verdad
    candidatos_globales = _recalcular_globales_desde_deptos(candidatos_globales, departamentos)

    canvas = _base()
    draw   = ImageDraw.Draw(canvas)
    cx     = (BOX_X1 + BOX_X2) // 2

    draw.text((cx, TITLE_Y), "VOTO POR REGIONES",
              font=_f(54,True), fill=DARK, anchor="mm")

    depto_idx = {d["nombre"].upper(): d for d in departamentos}
    gdf_data  = _gdf()

    colors = []
    for _, row in gdf_data.iterrows():
        ne   = row.get("name","") or ""
        if not isinstance(ne, str): ne = ""
        norm = DEPTO_NAME_MAP.get(ne, ne.upper())
        dat  = depto_idx.get(norm)
        if dat and dat.get("primer_lugar"):
            rgb = _get_color(dat["primer_lugar"]["candidato"].upper())
        else:
            rgb = GRAY
        colors.append(_rgb_mpl(rgb))

    dpi = 150
    fig, ax = plt.subplots(1,1, figsize=(MAP_W/dpi, MAP_H/dpi), facecolor='none')
    ax.set_facecolor('none')
    gdf_data.plot(ax=ax, color=colors, edgecolor='white', linewidth=1.2)
    ax.axis('off')
    fig.tight_layout(pad=0)
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight',
                pad_inches=0.01, transparent=True)
    plt.close(fig)
    buf.seek(0)
    mapa = Image.open(buf).convert("RGBA").resize((MAP_W,MAP_H), Image.LANCZOS)

    mapa_cy    = MAP_Y + (CONTENT_BOT - MAP_Y) // 2
    mapa_paste = max(MAP_Y, min(mapa_cy - MAP_H//2, CONTENT_BOT - MAP_H))
    rgba = canvas.convert("RGBA")
    rgba.paste(mapa, (MAP_X, mapa_paste), mapa)
    canvas = rgba.convert("RGB")
    draw   = ImageDraw.Draw(canvas)

    FOTO_SZ     = 106
    BLOCK_H     = 318
    avail_h     = CONTENT_BOT - CONTENT_Y
    GAP_BETWEEN = max(10, (avail_h - 2 * BLOCK_H) // 2)

    for i, (slug, info) in enumerate(SEGUNDA_VUELTA.items()):
        slot_y    = CONTENT_Y + i * (BLOCK_H + GAP_BETWEEN) + 5
        color_rgb = BAR_COLORS.get(info["color_key"], (150,150,150))

        if slot_y + BLOCK_H > CONTENT_BOT:
            break

        canvas = _pegar_foto(canvas, slug, FOTO_SZ, LEY_X, slot_y, color_rgb)
        draw   = ImageDraw.Draw(canvas)

        nome_y = slot_y + FOTO_SZ + 24
        draw.text((LEY_X, nome_y),    info["display_l1"], font=_f(28,True), fill=DARK)
        draw.text((LEY_X, nome_y+30), info["display_l2"], font=_f(28,True), fill=DARK)

        # Buscar en candidatos_globales (ya normalizados, indexados por nombre de SEGUNDA_VUELTA)
        nombre_sv = info["nombre"].upper()
        match = next(
            (c for c in candidatos_globales if c.get("nombre","").upper().strip() == nombre_sv),
            None
        )
        pct   = float(match.get("porcentaje", 0)) if match else 0
        votos = match.get("votos","0") if match else "0"
        try: vf = f"{int(str(votos).replace('.','').replace(',','')):,}".replace(",",".")
        except: vf = str(votos)

        font_v = _f(22,True)
        bb     = draw.textbbox((0,0), vf, font=font_v)
        pad_x, pad_y = 12, 10
        box_w  = bb[2]-bb[0] + pad_x*2
        box_h  = bb[3]-bb[1] + pad_y*2
        box_y  = nome_y + 68
        draw.rectangle([LEY_X, box_y, LEY_X+box_w, box_y+box_h], fill=color_rgb)
        draw.text((LEY_X+box_w//2, box_y+box_h//2-1), vf,
                  font=font_v, fill=WHITE, anchor="mm")

        bar_w_total = 180
        bar_h = 16
        bar_y = box_y + box_h + 6
        pct_w = max(4, int(bar_w_total * pct / 100))
        draw.rectangle([LEY_X, bar_y, LEY_X+pct_w, bar_y+bar_h], fill=color_rgb)
        draw.rectangle([LEY_X+pct_w, bar_y, LEY_X+bar_w_total, bar_y+bar_h], fill=NAVY)

        pct_y = bar_y + bar_h + 4
        if pct_y + 52 <= CONTENT_BOT:
            draw.text((LEY_X, pct_y), f"{pct:.2f} %".replace(".",","),
                      font=_f(52,True), fill=DARK)

    return _badge(canvas, boletin_text)


def render_todos_deptos(departamentos, candidatos_globales, boletin_text="", meta=None):
    # Siempre normalizar candidatos_globales usando deptos como fuente de verdad
    candidatos_globales = _recalcular_globales_desde_deptos(candidatos_globales, departamentos)

    canvas = _base()
    draw   = ImageDraw.Draw(canvas)
    cx     = (BOX_X1 + BOX_X2) // 2

    draw.text((cx, TITLE_Y), "RESULTADOS POR DEPARTAMENTO",
              font=_f(38,True), fill=DARK, anchor="mm")

    cands_sv = []
    for slug, info in SEGUNDA_VUELTA.items():
        nombre_sv = info["nombre"].upper()
        match = next(
            (c for c in candidatos_globales if c.get("nombre","").upper().strip() == nombre_sv),
            None
        )
        cands_sv.append({
            "slug":      slug,
            "info":      info,
            "color_rgb": BAR_COLORS.get(info["color_key"],(150,150,150)),
            "pct_nac":   float(match.get("porcentaje",0)) if match else 0,
            "votos_nac": match.get("votos","0") if match else "0",
        })

    cand_deptos = {slug:[] for slug in SEGUNDA_VUELTA}
    for d in departamentos:
        p1     = d.get("primer_lugar",{})
        slug_m = _get_slug(p1.get("candidato","").upper())
        if slug_m:
            cand_deptos[slug_m].append({
                "nombre":     d["nombre"],
                "porcentaje": p1.get("porcentaje",0),
                "votos":      p1.get("votos",0),
            })
    for s in cand_deptos:
        cand_deptos[s].sort(key=lambda x: x["porcentaje"], reverse=True)

    FOTO_SZ = 52
    COL_W   = (BOX_W - 28) // 2
    PAD_X   = BOX_X1 + 8
    MID_X   = PAD_X + COL_W + 12
    COL2_X  = MID_X + 8
    START_Y = CONTENT_Y

    draw.line([(MID_X, START_Y),(MID_X, BOX_Y2-30)], fill=(200,200,203), width=1)

    for col_idx, cdata in enumerate(cands_sv):
        slug      = cdata["slug"]
        info      = cdata["info"]
        color_rgb = cdata["color_rgb"]
        pct_nac   = cdata["pct_nac"]
        votos_nac = cdata["votos_nac"]
        col_x     = PAD_X if col_idx==0 else COL2_X
        deptos    = cand_deptos.get(slug,[])
        n_ganados = len(deptos)

        try: vf = f"{int(str(votos_nac).replace('.','').replace(',','')):,}".replace(",",".")
        except: vf = str(votos_nac)

        canvas = _pegar_foto(canvas, slug, FOTO_SZ, col_x, START_Y, color_rgb)
        draw   = ImageDraw.Draw(canvas)

        tx   = col_x + FOTO_SZ + 16
        nome = (info["display_l1"]+" "+info["display_l2"])[:22]
        draw.text((tx, START_Y+4),  nome,               font=_f(19,True), fill=DARK)
        draw.text((tx, START_Y+26), f"{pct_nac:.1f}%",  font=_f(18,True), fill=color_rgb)
        draw.text((tx, START_Y+46), vf+" votos",         font=_f(13),      fill=(110,110,110))

        H_LINE = START_Y + FOTO_SZ + 12
        draw.line([(col_x, H_LINE),(col_x+COL_W-4, H_LINE)], fill=color_rgb, width=2)

        LIST_Y = H_LINE + 10
        avail  = BOX_Y2 - 32 - LIST_Y
        n_show = min(n_ganados, 17)
        ROW_H  = max(26, min(38, avail // max(n_show,1)))

        for j, dep in enumerate(deptos):
            ry = LIST_Y + j * ROW_H
            if ry + ROW_H > BOX_Y2 - 32: break
            nd     = dep["nombre"]
            nd     = (nd[:19]+"…") if len(nd)>20 else nd
            pctd   = dep.get("porcentaje",0)
            fsize  = max(11, min(15, ROW_H-14))
            BAR_H  = max(11, ROW_H-18)
            BAR_Y  = ry + ROW_H - BAR_H - 2
            BAR_MAX= COL_W - 4
            BAR_W  = max(4, int(BAR_MAX * pctd / 100))
            draw.text((col_x, ry+1), nd, font=_f(fsize), fill=DARK)
            draw.rectangle([col_x, BAR_Y, col_x+BAR_MAX, BAR_Y+BAR_H], fill=(215,215,218))
            draw.rectangle([col_x, BAR_Y, col_x+BAR_W,   BAR_Y+BAR_H], fill=color_rgb)
            draw.text((col_x+BAR_W+3, BAR_Y+1),
                      f"{pctd:.0f}%", font=_f(max(10,fsize-2),True), fill=color_rgb)

        draw.text((col_x+COL_W//2, BOX_Y2-18),
                  f"Ganó en {n_ganados} departamentos",
                  font=_f(13), fill=(100,100,100), anchor="mm")

    return _badge(canvas, boletin_text)


def render_carrusel_segunda_vuelta(candidatos_globales, departamentos,
                                    boletin_text="", meta=None):
    t1 = render_mapa_sv(     departamentos, candidatos_globales, boletin_text, meta)
    t2 = render_todos_deptos(departamentos, candidatos_globales, boletin_text, meta)
    return [t1, t2]


def carrusel_a_zip(tarjetas, boletin_text=""):
    slug    = boletin_text.lower().replace(" ","-").replace("ó","o") or "sv"
    nombres = [f"01-mapa-sv-{slug}.png", f"02-deptos-sv-{slug}.png"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as zf:
        for img, n in zip(tarjetas, nombres):
            b = io.BytesIO(); img.save(b, format="PNG"); zf.writestr(n, b.getvalue())
    buf.seek(0)
    return buf.read()