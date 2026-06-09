# ============================================================
# INTEGRACIÓN SCRAPER REGISTRADURÍA 2026
# Agregar en generator.py justo DESPUÉS de la sección
# "Colores disponibles para barras de candidatos" (BAR_COLORS)
# y ANTES de "Carpeta de candidatos preconfigurados" (CANDIDATOS_DIR)
# ============================================================

# ── Endpoints de la API de resultados (se prueban en orden) ──────────────────
REGISTRADURIA_ENDPOINTS = [
    "https://resultados.registraduria.gov.co/api/v1/presidencia",
    "https://resultados.registraduria.gov.co/api/presidencia/resultados",
    "https://resultados.registraduria.gov.co/api/resultados/0/00",
    "https://resultados.registraduria.gov.co/data/0/00.json",
    "https://resultados.registraduria.gov.co/json/presidencia.json",
    "https://resultados.registraduria.gov.co/preconteo/presidencia.json",
]

# ── Color de barra asignado a cada candidato ─────────────────────────────────
COLORES_CANDIDATOS_2026 = {
    "ivan-cepeda":                "Morado",
    "abelardo-de-la-espriella":   "Naranja",
    "paloma-valencia":            "Azul",
    "claudia-lopez":              "Verde",
    "sergio-fajardo":             "Amarillo",
    "roy-barreras":               "Rojo",
    "gustavo-matamoros":          "Azul",
    "luis-gilberto-murillo":      "Verde",
    "carlos-caicedo":             "Naranja",
    "clara-lopez":                "Rosa",
    "miguel-uribe":               "Azul",
}

# ── Mapeo nombre normalizado → key de archivo en assets/candidatos/ ───────────
_REGISTRADURIA_NOMBRE_KEY = {
    "ivan cepeda":                   "ivan-cepeda",
    "ivan cepeda castro":            "ivan-cepeda",
    "abelardo de la espriella":      "abelardo-de-la-espriella",
    "paloma valencia":               "paloma-valencia",
    "paloma valencia abello":        "paloma-valencia",
    "claudia lopez":                 "claudia-lopez",
    "claudia lopez medina":          "claudia-lopez",
    "sergio fajardo":                "sergio-fajardo",
    "sergio fajardo valderrama":     "sergio-fajardo",
    "roy barreras":                  "roy-barreras",
    "gustavo matamoros":             "gustavo-matamoros",
    "luis gilberto murillo":         "luis-gilberto-murillo",
    "luis gilberto murillo urrutia": "luis-gilberto-murillo",
    "carlos caicedo":                "carlos-caicedo",
    "clara lopez":                   "clara-lopez",
    "miguel uribe":                  "miguel-uribe",
    "miguel uribe turbay":           "miguel-uribe",
}


def _registraduria_key_desde_nombre(nombre_raw):
    """Mapea un nombre de candidato de la API al key de assets/candidatos/."""
    s = nombre_raw.lower().strip()
    # Quitar acentos
    s = "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )
    # 1. Match exacto
    if s in _REGISTRADURIA_NOMBRE_KEY:
        return _REGISTRADURIA_NOMBRE_KEY[s]
    # 2. Match parcial: la key está contenida en el nombre o viceversa
    for k, v in _REGISTRADURIA_NOMBRE_KEY.items():
        if k in s or s in k:
            return v
    # 3. Derivar de las dos primeras palabras
    palabras = s.split()
    if len(palabras) >= 2:
        candidata = "-".join(palabras[:2])
        if candidata in COLORES_CANDIDATOS_2026:
            return candidata
    return None


def _registraduria_parse_json(data):
    """
    Extrae lista cruda [{nombre_raw, porcentaje, votos}] de la respuesta JSON
    de la Registraduría. Soporta múltiples estructuras posibles.
    """
    raw = []

    if isinstance(data, list):
        raw = data
    elif isinstance(data, dict):
        for k in ("candidatos", "resultados", "results", "data", "preconteo"):
            v = data.get(k)
            if isinstance(v, list):
                raw = v
                break
            if isinstance(v, dict) and "candidatos" in v:
                raw = v["candidatos"]
                break

    candidatos = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        nombre = (
            item.get("nombre") or item.get("name") or
            item.get("candidato") or item.get("nombreCandidato") or ""
        ).strip()
        if not nombre:
            continue

        pct_raw = (
            item.get("porcentaje") or item.get("pct") or
            item.get("percentage") or item.get("porcentajeVotos") or 0
        )
        try:
            pct = float(str(pct_raw).replace(",", ".").replace("%", "").strip())
        except (ValueError, TypeError):
            pct = 0.0

        votos_raw = (
            item.get("votos") or item.get("votes") or
            item.get("totalVotos") or item.get("sufragios") or 0
        )
        try:
            votos = int(str(votos_raw).replace(".", "").replace(",", "").strip())
        except (ValueError, TypeError):
            votos = 0

        candidatos.append({"nombre_raw": nombre, "porcentaje": pct, "votos": votos})

    return candidatos


def _registraduria_enriquecer(candidatos_raw):
    """
    Enriquece la lista cruda con key, nombre formal, foto PIL y color de barra.
    Retorna lista ordenada de mayor a menor porcentaje.
    """
    resultado = []
    for c in candidatos_raw:
        nombre_raw = c["nombre_raw"]
        key = _registraduria_key_desde_nombre(nombre_raw)

        nombre_formal = CANDIDATOS_NOMBRES.get(key, nombre_raw.upper()) if key else nombre_raw.upper()
        foto = load_candidato_image(key) if key else None
        color = COLORES_CANDIDATOS_2026.get(key, "Amarillo")

        resultado.append({
            "key": key,
            "nombre": nombre_formal,
            "porcentaje": c["porcentaje"],
            "votos": c["votos"],
            "color_barra": color,
            "foto": foto,
        })

    resultado.sort(key=lambda x: x["porcentaje"], reverse=True)
    return resultado


def get_resultados_registraduria(max_candidatos=5, verbose=True):
    """
    Consulta la API pública de la Registraduría y retorna la lista de candidatos
    lista para pasar directamente a render_resultados_candidatos().

    Args:
        max_candidatos (int): máximo de candidatos a incluir (1-5).
        verbose (bool): imprime progreso y errores en consola.

    Returns:
        list[dict]: con claves key, nombre, porcentaje, votos, color_barra, foto

    Raises:
        RuntimeError: si ningún endpoint responde con datos válidos.

    Ejemplo:
        candidatos = get_resultados_registraduria()
        img = render_resultados_candidatos(candidatos, format_key="post",
                                           boletin_text="BOLETÍN No. 3")
        img.save("resultados.png")
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://resultados.registraduria.gov.co/",
        "Cache-Control": "no-cache",
    }

    ultimo_error = None

    for url in REGISTRADURIA_ENDPOINTS:
        try:
            if verbose:
                print(f"[Registraduría] Consultando {url}")
            resp = requests.get(url, headers=headers, timeout=15)

            if resp.status_code != 200:
                if verbose:
                    print(f"  HTTP {resp.status_code} — saltando")
                continue

            ct = resp.headers.get("content-type", "")
            if "json" not in ct and not resp.text.strip().startswith(("{", "[")):
                if verbose:
                    print(f"  Respuesta no es JSON — saltando")
                continue

            data = resp.json()
            candidatos_raw = _registraduria_parse_json(data)

            if not candidatos_raw:
                if verbose:
                    print(f"  Sin candidatos en la respuesta — saltando")
                continue

            candidatos = _registraduria_enriquecer(candidatos_raw)[:max_candidatos]

            if verbose:
                print(f"✓ {len(candidatos)} candidatos obtenidos")
                for c in candidatos:
                    print(f"  {c['nombre']:<40} {c['porcentaje']:.1f}%  ({c['votos']:,} votos)")

            return candidatos

        except requests.exceptions.ConnectionError as e:
            ultimo_error = str(e)
            if verbose:
                print(f"  ✗ Sin conexión")
        except requests.exceptions.Timeout:
            ultimo_error = "Timeout"
            if verbose:
                print(f"  ✗ Timeout")
        except Exception as e:
            ultimo_error = str(e)
            if verbose:
                print(f"  ✗ Error: {e}")

    raise RuntimeError(
        f"No se pudo obtener datos de la Registraduría.\n"
        f"Último error: {ultimo_error}\n"
        f"Usa get_resultados_manual() para ingresar datos manualmente."
    )


def get_resultados_manual(csv_o_lista):
    """
    Alternativa a get_resultados_registraduria() cuando la API no está disponible.
    Acepta datos en formato CSV (string) o lista de dicts.

    Formato CSV:
        "Iván Cepeda,38.5,4200000
         Paloma Valencia,22.0,2400000"

    Formato lista:
        [{"nombre": "Iván Cepeda", "porcentaje": 38.5, "votos": 4200000}, ...]

    Returns:
        list[dict] lista para usar en render_resultados_candidatos()

    Ejemplo:
        candidatos = get_resultados_manual(
            "Iván Cepeda,38.5,4200000\\n"
            "Paloma Valencia,22.0,2400000\\n"
            "Abelardo De la Espriella,19.5,2100000"
        )
        img = render_resultados_candidatos(candidatos, format_key="post")
    """
    if isinstance(csv_o_lista, str):
        candidatos_raw = []
        for linea in csv_o_lista.strip().splitlines():
            partes = [p.strip() for p in linea.split(",")]
            if len(partes) < 2:
                continue
            nombre = partes[0]
            try:
                pct = float(partes[1].replace("%", ""))
            except ValueError:
                continue
            votos = 0
            if len(partes) >= 3:
                try:
                    votos = int(partes[2].replace(".", "").replace(",", ""))
                except ValueError:
                    pass
            candidatos_raw.append({"nombre_raw": nombre, "porcentaje": pct, "votos": votos})
    elif isinstance(csv_o_lista, list):
        candidatos_raw = [
            {
                "nombre_raw": item.get("nombre", ""),
                "porcentaje": float(item.get("porcentaje", 0)),
                "votos": int(item.get("votos", 0)),
            }
            for item in csv_o_lista
        ]
    else:
        raise ValueError("Parámetro debe ser str (CSV) o list[dict]")

    return _registraduria_enriquecer(candidatos_raw)
