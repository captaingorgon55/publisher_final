"""
scraper_registraduria.py
Obtiene resultados electorales desde la API interna de El Espectador.
"""

import requests
import csv
import io
import re
import logging
import datetime
from pathlib import Path

log = logging.getLogger("scraper_registraduria")

BASE_API = "https://elecciones.elespectador.com/api/presidentials"
BASE_CSV = "https://elecciones.elespectador.com/archives"
HEADERS  = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

DEFAULT_COLORS = ["Azul", "Rojo", "Naranja", "Verde", "Amarillo", "Morado", "Rosa"]

DEPTO_SLUGS = {
    "AMAZONAS":                 "amazonas",
    "ANTIOQUIA":                "antioquia",
    "ARAUCA":                   "arauca",
    "ATLÁNTICO":                "atlantico",
    "BOGOTÁ D.C.":              "bogotadc",
    "BOLÍVAR":                  "bolivar",
    "BOYACÁ":                   "boyaca",
    "CALDAS":                   "caldas",
    "CAQUETÁ":                  "caqueta",
    "CASANARE":                 "casanare",
    "CAUCA":                    "cauca",
    "CESAR":                    "cesar",
    "CHOCÓ":                    "choco",
    "CÓRDOBA":                  "cordoba",
    "CUNDINAMARCA":             "cundinamarca",
    "GUAINÍA":                  "guainia",
    "GUAVIARE":                 "guaviare",
    "HUILA":                    "huila",
    "LA GUAJIRA":               "laguajira",
    "MAGDALENA":                "magdalena",
    "META":                     "meta",
    "NARIÑO":                   "narino",
    "NORTE DE SANTANDER":       "nortedesantander",
    "PUTUMAYO":                 "putumayo",
    "QUINDÍO":                  "quindio",
    "RISARALDA":                "risaralda",
    "SAN ANDRÉS Y PROVIDENCIA": "sanandres",
    "SANTANDER":                "santander",
    "SUCRE":                    "sucre",
    "TOLIMA":                   "tolima",
    "VALLE DEL CAUCA":          "valle",
    "VAUPÉS":                   "vaupes",
    "VICHADA":                  "vichada",
}

# Palabras que indican que una línea NO es un nombre de candidato
_SKIP_WORDS = {
    "candidatos", "candidato", "candidata", "presidencia", "presidencial",
    "vicepresidencia", "vicepresidente", "vicepresidenta",
    "votos", "porcentaje", "mesas", "informadas", "escrutado",
    "resultados", "boletín", "boletin", "colombia", "total",
}


def _es_linea_nombre(linea: str) -> bool:
    """True si la línea parece un nombre de candidato (no un dato ni un cargo)."""
    l = linea.lower().strip()
    # Descartar líneas con números o %
    if re.search(r"\d+\s*%", l):
        return False
    if re.match(r"^\d[\d\.\,\s]*$", l):
        return False
    # Descartar líneas que SON un cargo (empieza con "candidato/a a la")
    if re.match(r'^(candidato|candidata).{0,30}(presidencia|vice)', l):
        return False
    # Descartar líneas que contienen solo palabras de skip
    for w in _SKIP_WORDS:
        if l == w or l == w + "s":
            return False
    # Tiene al menos 2 palabras con mayúscula inicial
    palabras = linea.strip().split()
    if len(palabras) >= 2 and all(p[0].isupper() for p in palabras if p):
        return True
    # Nombre pegado: secuencia larga de mayúsculas
    if re.search(r'[A-ZÁÉÍÓÚÑÜ]{4,}', linea):
        return True
    return False


# Mapeo directo de nombres de candidatos conocidos (segunda vuelta 2026)
_CANDIDATOS_MAP = {
    r"IV[AÁ]N?\s*CEPEDA?\s*CASTRO?":      "IVÁN CEPEDA CASTRO",
    r"ABELARDO\s*DE?\s*LA?\s*ESPRIELLA?":  "ABELARDO DE LA ESPRIELLA",
    r"\bCEPEDA\b":                          "IVÁN CEPEDA CASTRO",
    r"\bESPRIELLA\b":                       "ABELARDO DE LA ESPRIELLA",
}


def _normalizar_nombre_candidato(nombre: str) -> str:
    """
    Normaliza nombres pegados o con errores.
    Usa mapeo directo para candidatos conocidos.
    Fallback: separar por vocales acentuadas.
    """
    nombre_up = nombre.upper().strip()
    for patron, correcto in _CANDIDATOS_MAP.items():
        if re.search(patron, nombre_up, re.IGNORECASE):
            return correcto
    # Fallback genérico: vocal acentuada seguida de consonante
    resultado = re.sub(r'([ÁÉÍÓÚÑ])([A-Z])', r'\1 \2', nombre_up)
    return re.sub(r'  +', ' ', resultado).strip()


def _parsear_texto_nuevo_formato(texto: str) -> list:
    """
    Parser para el formato de El Espectador segunda vuelta:

        IVÁNCEPEDA CASTRO
        Candidato a la          ← puede estar en 1 o 2 líneas
        presidencia
        AIDA MARINAQUILCUE VIVAS
        Candidato a la
        vicepresidencia
        0                       ← votos (0 o número real)
        0 votos 0 %             ← ancla: "VOTOS votos PCT %"
        0 %

    Estrategia: unir líneas de cargo partidas, luego buscar
    "Candidato a la presidencia" y tomar el nombre de la línea anterior.
    """
    # Unir líneas de cargo que vienen partidas en 2 líneas
    texto_u = re.sub(r'[Cc]andidat[oa] a la\s*\n\s*presidencia',
                     'Candidato a la presidencia', texto)
    texto_u = re.sub(r'[Cc]andidat[oa] a la\s*\n\s*vicepresidencia',
                     'Candidato a la vicepresidencia', texto_u)

    lineas = [l.strip() for l in texto_u.splitlines() if l.strip()]
    candidatos = []

    for i, linea in enumerate(lineas):
        # Ancla: línea de cargo presidencial (sin vice)
        if not re.match(r'^[Cc]andidat[oa] a la presidencia$', linea):
            continue

        # El nombre del presidente está en la línea anterior
        if i == 0:
            continue
        nombre_raw = lineas[i - 1]
        nombre = _normalizar_nombre_candidato(nombre_raw)
        if not nombre:
            continue

        # Buscar "VOTOS votos PCT %" en las próximas líneas
        pct, votos = 0.0, 0
        for j in range(i + 1, min(i + 8, len(lineas))):
            m = re.match(
                r'^([\d][\d\.\,]*)\s+votos?\s+([\d][\d\.\,]*)\s*%$',
                lineas[j], re.IGNORECASE
            )
            if m:
                try: votos = int(m.group(1).replace('.', '').replace(',', ''))
                except: votos = 0
                try: pct = float(m.group(2).replace(',', '.'))
                except: pct = 0.0
                break
            # Parar si llegamos a otro candidato
            if re.match(r'^[Cc]andidat[oa] a la presidencia$', lineas[j]):
                break

        # Evitar duplicados
        if not any(c["nombre"] == nombre.upper() for c in candidatos):
            candidatos.append({
                "nombre":     nombre.upper(),
                "porcentaje": pct,
                "votos":      votos,
            })

    return candidatos


def _parsear_texto_libre(texto: str) -> list:
    """
    Parser unificado: intenta el formato nuevo primero,
    luego el clásico como fallback.
    """
    # Detectar si es el formato nuevo (tiene "Candidato a la presidencia")
    if re.search(r'candidato.{0,10}presidencia', texto, re.IGNORECASE | re.DOTALL):
        resultado = _parsear_texto_nuevo_formato(texto)
        if resultado:
            return resultado

    # Formato clásico: "NOMBRE 43.7% 10.361.499"
    lineas     = [l.strip() for l in texto.splitlines() if l.strip()]
    candidatos = []

    for linea in lineas:
        # Línea tipo: "ABELARDO DE LA ESPRIELLA 43.7% 10.361.499"
        m = re.match(
            r'^([A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ\s]+?)\s+'
            r'([\d]+[\.,][\d]+)\s*%\s+'
            r'([\d][\d\.\,]*)',
            linea.strip()
        )
        if m:
            nombre = m.group(1).strip()
            try: pct = float(m.group(2).replace(',','.'))
            except: pct = 0.0
            try: votos = int(m.group(3).replace('.','').replace(',',''))
            except: votos = 0
            candidatos.append({"nombre": nombre, "porcentaje": pct, "votos": votos})
            continue

        # Línea tipo: "NOMBRE\n43.7%\n10.361.499" (ya parseado antes)
        # Formato antiguo con "Candidato a la presidencia"
        if "presidenc" in linea.lower() and "vice" not in linea.lower():
            for back in range(1, 4):
                idx = lineas.index(linea)
                if idx - back >= 0:
                    cand = lineas[idx - back]
                    if cand and not any(t in cand.lower() for t in _SKIP_WORDS):
                        nombre = re.sub(r"^nombre[:\s]*", "", cand, flags=re.IGNORECASE).strip()
                        if nombre:
                            pct, votos = 0.0, 0
                            for j in range(max(0, idx-3), min(len(lineas), idx+4)):
                                mp = re.search(r"([0-9]+[\.,]?[0-9]*)\s*%", lineas[j])
                                if mp and pct == 0.0:
                                    try: pct = float(mp.group(1).replace(",","."))
                                    except: pass
                            candidatos.append({"nombre": nombre, "porcentaje": pct, "votos": votos})
                        break

    return candidatos


def get_candidatos_resultados(url: str = None) -> list:
    try:
        from generator import load_candidato_image, CANDIDATOS_NOMBRES
    except ImportError:
        load_candidato_image = lambda k: None
        CANDIDATOS_NOMBRES   = {}

    log.info("Consultando API nacional...")
    resp = requests.get(BASE_API, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    datos = resp.json()

    candidatos_raw = datos.get("candidates", [])
    if not candidatos_raw:
        raise ValueError("La API no devolvió candidatos.")

    resultado = []
    for i, cand in enumerate(candidatos_raw):
        nombre = cand.get("name", "").upper().strip()
        color  = DEFAULT_COLORS[i % len(DEFAULT_COLORS)]
        foto   = None
        for key, nombre_formal in CANDIDATOS_NOMBRES.items():
            partes = nombre_formal.upper().split()
            if any(len(p) > 3 and p in nombre for p in partes):
                foto = load_candidato_image(key)
                break
        resultado.append({
            "foto":        foto,
            "nombre":      nombre,
            "porcentaje":  float(cand.get("percentage", 0)),
            "votos":       str(int(cand.get("votes", 0))),
            "color_barra": color,
        })

    log.info(f"Boletín {datos.get('bulletin')} — {datos.get('scrutinized')}% escrutado — {len(resultado)} candidatos")
    return resultado


def get_candidatos_manual(datos_raw) -> list:
    try:
        from generator import load_candidato_image, CANDIDATOS_NOMBRES
    except ImportError:
        load_candidato_image = lambda k: None
        CANDIDATOS_NOMBRES   = {}

    if isinstance(datos_raw, str):
        datos_raw = _parsear_texto_libre(datos_raw)
    if not datos_raw:
        return []

    resultado = []
    for i, cand in enumerate(datos_raw):
        nombre = str(cand.get("nombre", f"Candidato {i+1}")).upper().strip()
        color  = DEFAULT_COLORS[i % len(DEFAULT_COLORS)]
        foto   = None
        for key, nf in CANDIDATOS_NOMBRES.items():
            if any(len(p) > 3 and p in nombre for p in nf.upper().split()):
                foto = load_candidato_image(key)
                break
        resultado.append({
            "foto":        foto,
            "nombre":      nombre,
            "porcentaje":  float(cand.get("porcentaje", 0)),
            "votos":       str(cand.get("votos", "")),
            "color_barra": color,
        })
    return resultado


def get_resultados_territoriales(url: str = None) -> dict:
    meta = {
        "boletin":          None,
        "mesas_reportadas": None,
        "timestamp":        datetime.datetime.now().isoformat(),
    }
    try:
        r = requests.get(BASE_API, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            d = r.json()
            meta["boletin"]          = d.get("bulletin")
            meta["mesas_reportadas"] = d.get("scrutinized")
            meta["total_votos"]      = d.get("totalVotes")
    except Exception:
        pass

    departamentos = []

    for nombre_depto, slug in DEPTO_SLUGS.items():
        csv_url = f"{BASE_CSV}/resultados_{slug}.csv"
        try:
            resp = requests.get(csv_url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
            reader = csv.DictReader(io.StringIO(resp.text))
            rows   = list(reader)
            if not rows:
                continue
            totales = {}
            for row in rows:
                for pos in ["Primero", "Segundo", "Tercero"]:
                    cand = row.get(pos, "").strip()
                    if not cand:
                        continue
                    try:
                        votos = int(str(row.get(f"Votos-{pos}", 0)).replace(",","").replace(".","") or 0)
                    except (ValueError, TypeError):
                        votos = 0
                    totales[cand] = totales.get(cand, 0) + votos
            if not totales:
                continue
            ordenados         = sorted(totales.items(), key=lambda x: x[1], reverse=True)
            total_votos_depto = sum(v for _, v in ordenados)
            def pct(v):
                return round(v / total_votos_depto * 100, 1) if total_votos_depto > 0 else 0.0
            depto_result = {"nombre": nombre_depto}
            if ordenados:
                n1, v1 = ordenados[0]
                depto_result["primer_lugar"] = {"candidato": n1, "votos": v1, "porcentaje": pct(v1)}
            if len(ordenados) >= 2:
                n2, v2 = ordenados[1]
                depto_result["segundo_lugar"] = {"candidato": n2, "votos": v2, "porcentaje": pct(v2)}
            departamentos.append(depto_result)
        except Exception:
            continue

    return {"meta": meta, "departamentos": departamentos}