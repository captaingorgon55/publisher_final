    """
    map_generator_sv.py  v12 (Pixel Perfect Final - Encuadre y Escala)
    Ajustes realizados:
    - Eliminado el shift_y manual que cortaba la cabeza de los candidatos.
    - Encuadre solucionado usando "centering" de ImageOps.fit para subir la imagen de forma nativa.
    - Matemática de Layout: El mapa creció a 620px asegurando que encaje milimétricamente en 
        el espacio restante a la derecha sin solapar la leyenda ni salir del borde.
    """

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

    # ── Cuadro gris contenedor ────────────────────────────────────
    BOX_X1, BOX_Y1 = 108,  59
    BOX_X2, BOX_Y2 = 976, 1134
    BOX_W = BOX_X2 - BOX_X1   # Total: 868px
    BOX_H = BOX_Y2 - BOX_Y1   

    LOGO_BOTTOM = 210
    TITLE_Y     = LOGO_BOTTOM + 25   
    TITLE_H     = 65                 
    CONTENT_Y   = TITLE_Y + TITLE_H + 20  
    CONTENT_BOT = BOX_Y2 - 20        

    # ── Layout Exacto: Columna Izquierda y Mapa Gigante ───────────
    LEY_X    = BOX_X1 + 100         # Margen izquierdo seguro
    LEY_W    = 200                   # Espacio que consume la columna izquierda
    MAP_W    = 720                  # MAPA GIGANTE (Ajustado al máximo espacio libre)
    MAP_H    = int(MAP_W * 1.20)     # Alto proporcional (aprox 744px)
    MAP_X    = BOX_X2 - MAP_W - 10   # Alineado a la derecha con margen de 10px
    MAP_Y    = CONTENT_Y             

    # Verificación de seguridad vertical
    if MAP_Y + MAP_H > CONTENT_BOT:
        MAP_H = CONTENT_BOT - MAP_Y
        MAP_W = int(MAP_H / 1.20)
        MAP_X = BOX_X2 - MAP_W - 10  

    # ── Colores Editoriales ───────────────────────────────────────
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


    # ── Helpers ───────────────────────────────────────────────────

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
            p = FONDOS_DIR / f"voto-regiones{ext}"
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
        for ext in [".png",".jpg"]:
            p = CANDS_DIR / f"{slug}{ext}"
            if p.exists():
                img = Image.open(p).convert("RGBA")
                
                # Zoom Out seguro con padding transparente
                pad_size = int(min(img.width, img.height) * 0.20)
                img = ImageOps.expand(img, border=pad_size, fill=(0,0,0,0))

                # Más aire abajo que arriba
                extra_bottom = int(img.height * 0.20)

                tmp = Image.new(
                    "RGBA",
                    (img.width, img.height + extra_bottom),
                    (0, 0, 0, 0)
                )

                tmp.paste(img, (0, 0), img)
                img = tmp

                # Subir nuevamente el encuadre
                img = ImageOps.fit(
                    img,
                    (size, size),
                    method=Image.LANCZOS,
                    centering=(0.5, 0.0)
                )

                # Filtro Blanco y Negro
                alpha = img.getchannel('A')
                gray = ImageOps.grayscale(img.convert("RGB"))
                bw_img = Image.merge("RGBA", (gray, gray, gray, alpha))

                # Fondo sólido partido, SE PEGA EXACTO EN (0,0) para no recortar la cabeza
                bg = Image.new("RGBA", (size, size), color_rgb + (255,))
                bg.paste(bw_img, (0, 20), bw_img)

                # Máscara circular con ANTIALIASING (supersampling 4x)
                mask_4x = Image.new("L", (size * 4, size * 4), 0)
                ImageDraw.Draw(mask_4x).ellipse([0, 0, (size * 4) - 1, (size * 4) - 1], fill=255)
                mask = mask_4x.resize((size, size), Image.LANCZOS)
                
                out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
                out.paste(bg, (0, 0), mask)
                return out

        # Fallback si no hay foto
        out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        mask_4x = Image.new("L", (size * 4, size * 4), 0)
        ImageDraw.Draw(mask_4x).ellipse([0, 0, (size * 4) - 1, (size * 4) - 1], fill=255)
        mask = mask_4x.resize((size, size), Image.LANCZOS)
        bg = Image.new("RGBA", (size, size), color_rgb+(255,))
        out.paste(bg, (0, 0), mask)
        return out


    def _pegar_foto(canvas, slug, size, x, y, color_rgb):
        rgba_canvas = canvas.convert("RGBA")
        
        # Tamaños de gap y borde exterior
        gap_pixels = int(size * 0.06) + 1
        border_width = int(size * 0.04) + 1
        offset = gap_pixels + border_width
        
        layer_sz = size + offset*2
        
        # Supersampling 4x para un borde completamente nítido
        layer_sz_4x = layer_sz * 4
        ring_layer_4x = Image.new("RGBA", (layer_sz_4x, layer_sz_4x), (0,0,0,0))
        draw_4x = ImageDraw.Draw(ring_layer_4x)
        
        b_box = [0, 0, layer_sz_4x - 1, layer_sz_4x - 1]
        draw_4x.ellipse(b_box, outline=color_rgb + (255,), width=border_width * 4)
        
        # Escalar hacia abajo para aplicar el antialiasing
        ring_layer = ring_layer_4x.resize((layer_sz, layer_sz), Image.LANCZOS)
        
        bx1 = x - offset
        by1 = y - offset
        rgba_canvas.paste(ring_layer, (bx1, by1), ring_layer)

        # Pegamos la foto procesada en el centro exacto
        foto = _foto_circ(slug, size, color_rgb)
        rgba_canvas.paste(foto, (x, y), foto)

        return rgba_canvas.convert("RGB")


    def _badge(canvas, txt):
        # Sin Boletín
        return canvas

    def _get_slug(nombre_up):
        for slug,info in SEGUNDA_VUELTA.items():
            parts = info["nombre"].split()
            if any(len(p)>3 and p in nombre_up for p in parts):
                return slug
        return None

    def _get_color(nombre_up):
        slug = _get_slug(nombre_up)
        if slug:
            ck = SEGUNDA_VUELTA[slug]["color_key"]
            return BAR_COLORS.get(ck, GRAY)
        return GRAY


    # ── TARJETA 1: Layout leyenda izq + mapa der ─────────────────

    def render_mapa_sv(departamentos, candidatos_globales, boletin_text="", meta=None):
        canvas = _base()
        draw   = ImageDraw.Draw(canvas)
        cx     = (BOX_X1 + BOX_X2) // 2

        # Título centrado
        draw.text((cx, TITLE_Y), "VOTO POR REGIONES", font=_f(54, True), fill=DARK, anchor="mm")

        # ── Mapa ─────────────────────────────────────────────────
        depto_idx = {d["nombre"].upper(): d for d in departamentos}
        gdf_data  = _gdf()

        colors = []
        for _, row in gdf_data.iterrows():
            ne   = row.get("name","") or ""
            if not isinstance(ne, str): ne = ""
            norm = DEPTO_NAME_MAP.get(ne, ne.upper())
            dat  = depto_idx.get(norm)
            if dat and dat.get("primer_lugar"):
                cand = dat["primer_lugar"]["candidato"].upper()
                rgb  = _get_color(cand)
            else:
                rgb = GRAY
            colors.append(_rgb_mpl(rgb))

        dpi   = 150
        fig, ax = plt.subplots(1,1,figsize=(MAP_W/dpi, MAP_H/dpi),facecolor='none')
        ax.set_facecolor('none')
        
        gdf_data.plot(ax=ax, color=colors, edgecolor='white', linewidth=1.2)
        ax.axis('off')
        
        fig.tight_layout(pad=0)
        buf = io.BytesIO()
        fig.savefig(buf,format='png',dpi=dpi,bbox_inches='tight', pad_inches=0.01,transparent=True)
        plt.close(fig)
        buf.seek(0)
        mapa = Image.open(buf).convert("RGBA")
        mapa = mapa.resize((MAP_W, MAP_H), Image.LANCZOS)

        # Centrado vertical del mapa
        mapa_center_y = MAP_Y + (CONTENT_BOT - MAP_Y) // 2
        mapa_y_paste  = mapa_center_y - MAP_H // 2
        mapa_y_paste  = max(MAP_Y, min(mapa_y_paste, CONTENT_BOT - MAP_H))

        rgba = canvas.convert("RGBA")
        rgba.paste(mapa,(MAP_X, mapa_y_paste), mapa)
        canvas = rgba.convert("RGB")
        draw   = ImageDraw.Draw(canvas)

        # ── LEYENDA IZQUIERDA ─────────────────────────────────────
        ley_slot_h = (CONTENT_BOT - CONTENT_Y) // 2
        FOTO_SZ    = 106 

        for i, (slug, info) in enumerate(SEGUNDA_VUELTA.items()):
            slot_y    = CONTENT_Y + i * ley_slot_h + 15
            color_rgb = BAR_COLORS.get(info["color_key"],(150,150,150))

            # 1. Foto B/N perfecta
            foto_x = LEY_X
            foto_y = slot_y
            canvas = _pegar_foto(canvas, slug, FOTO_SZ, foto_x, foto_y, color_rgb)
            draw   = ImageDraw.Draw(canvas)

            # 2. Nombre
            nome_y = foto_y + FOTO_SZ + 24
            font_name = _f(28, True)
            draw.text((LEY_X, nome_y),    info["display_l1"], font=font_name, fill=DARK)
            draw.text((LEY_X, nome_y+30), info["display_l2"], font=font_name, fill=DARK)

            match = next((c for c in candidatos_globales
                        if any(len(p)>3 and p in c.get("nombre","").upper()
                                for p in info["nombre"].split())), None)
            pct   = match.get("porcentaje",0) if match else 0
            votos = match.get("votos","0")    if match else "0"
            try: vf = f"{int(str(votos).replace('.','').replace(',','')):,}".replace(",",".")
            except: vf = str(votos)

            # 3. Caja de votos centrada milimétricamente
            font_v = _f(22, True)
            bbox = draw.textbbox((0,0), vf, font=font_v)
            vw = bbox[2] - bbox[0]
            vh = bbox[3] - bbox[1]
            
            pad_x, pad_y = 12, 10
            box_w = vw + (pad_x * 2)
            box_h = vh + (pad_y * 2)
            box_y = nome_y + 68 
            
            draw.rectangle([LEY_X, box_y, LEY_X + box_w, box_y + box_h], fill=color_rgb)
            
            cx_box = LEY_X + (box_w / 2)
            cy_box = box_y + (box_h / 2)
            draw.text((cx_box, cy_box - 2), vf, font=font_v, fill=WHITE, anchor="mm")

            # 4. Barra bicolor
            bar_w_total = 180
            bar_h = 16
            bar_y = box_y + box_h + 6
            pct_w = int(bar_w_total * (pct / 100)) if pct > 0 else bar_w_total // 2
            
            draw.rectangle([LEY_X, bar_y, LEY_X + pct_w, bar_y + bar_h], fill=color_rgb)
            draw.rectangle([LEY_X + pct_w, bar_y, LEY_X + bar_w_total, bar_y + bar_h], fill=NAVY)

            # 5. Porcentaje
            pct_y = bar_y + bar_h + 4 
            draw.text((LEY_X, pct_y), f"{pct:.2f} %".replace(".",","), font=_f(52,True), fill=DARK)

        canvas = _badge(canvas, boletin_text)
        return canvas

    # ── TARJETA 2: Todos los deptos en 2 columnas ─────────────────

    def render_todos_deptos(departamentos, candidatos_globales, boletin_text="", meta=None):
        canvas = _base()
        draw   = ImageDraw.Draw(canvas)
        cx     = (BOX_X1 + BOX_X2) // 2

        draw.text((cx, TITLE_Y), "RESULTADOS POR DEPARTAMENTO", font=_f(44,True), fill=DARK, anchor="mm")

        cands_sv = []
        for slug, info in SEGUNDA_VUELTA.items():
            match = next((c for c in candidatos_globales
                        if any(len(p)>3 and p in c.get("nombre","").upper()
                                for p in info["nombre"].split())), None)
            cands_sv.append({
                "slug":      slug,
                "info":      info,
                "color_rgb": BAR_COLORS.get(info["color_key"],(150,150,150)),
                "pct_nac":   match.get("porcentaje",0) if match else 0,
                "votos_nac": match.get("votos","0") if match else "0",
            })

        cand_deptos = {slug:[] for slug in SEGUNDA_VUELTA}
        for d in departamentos:
            p1   = d.get("primer_lugar",{})
            cand = p1.get("candidato","").upper()
            slug_m = _get_slug(cand)
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

            tx = col_x + FOTO_SZ + 16
            nome = info["display_l1"] + " " + info["display_l2"]
            nome = nome[:22] if len(nome) > 22 else nome
            draw.text((tx, START_Y+4),  nome,                font=_f(19,True), fill=DARK)
            draw.text((tx, START_Y+26), f"{pct_nac:.1f}%",  font=_f(18,True), fill=color_rgb)
            draw.text((tx, START_Y+46), vf+" votos",         font=_f(13),      fill=(110,110,110))

            H_LINE = START_Y + FOTO_SZ + 12
            draw.line([(col_x, H_LINE),(col_x+COL_W-4, H_LINE)], fill=color_rgb, width=2)

            LIST_Y  = H_LINE + 10
            avail   = BOX_Y2 - 32 - LIST_Y
            n_show  = min(n_ganados, 17)
            ROW_H   = max(26, min(38, avail // max(n_show,1)))

            for j, dep in enumerate(deptos):
                ry = LIST_Y + j * ROW_H
                if ry + ROW_H > BOX_Y2 - 32: break

                nd   = dep["nombre"]
                nd   = (nd[:19]+"…") if len(nd)>20 else nd
                pctd = dep.get("porcentaje",0)

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

        canvas = _badge(canvas, boletin_text)
        return canvas

    def render_carrusel_segunda_vuelta(candidatos_globales, departamentos,
                                        boletin_text="", meta=None):
        t1 = render_mapa_sv(      departamentos, candidatos_globales, boletin_text, meta)
        t2 = render_todos_deptos( departamentos, candidatos_globales, boletin_text, meta)
        return [t1, t2]

    def carrusel_a_zip(tarjetas, boletin_text=""):
        slug = boletin_text.lower().replace(" ","-").replace("ó","o") or "sv"
        nombres = [f"01-mapa-sv-{slug}.png", f"02-deptos-sv-{slug}.png"]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as zf:
            for img,n in zip(tarjetas,nombres):
                b = io.BytesIO(); img.save(b,format="PNG"); zf.writestr(n,b.getvalue())
        buf.seek(0)
        return buf.read()