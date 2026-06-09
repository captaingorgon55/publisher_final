"""
scraper_registraduria.py
Obtiene resultados electorales desde la API interna de El Espectador.

Sin LLM, sin Playwright, sin cuotas.
Solo requests + CSV parsing.

APIs usadas:
  Nacional:     https://elecciones.elespectador.com/api/presidentials
  CSV colombia: https://elecciones.elespectador.com/archives/resultados_colombia.csv
  CSV depto:    https://elecciones.elespectador.com/archives/resultados_{slug}.csv
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


def get_candidatos_resultados(url: str = None) -> list:
    """
    Resultados nacionales desde la API de El Espectador.
    Devuelve lista compatible con render_resultados_candidatos().
    """
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

        foto = None
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


def get_resultados_territoriales(url: str = None) -> dict:
    """
    Resultados por departamento desde los CSVs de El Espectador.
    """
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

            # Sumar votos por candidato en todos los municipios
            totales = {}
            for row in rows:
                for pos in ["Primero", "Segundo", "Tercero"]:
                    cand = row.get(pos, "").strip()
                    if not cand:
                        continue
                    try:
                        votos = int(str(row.get(f"Votos-{pos}", 0)).replace(",", "").replace(".", "") or 0)
                    except (ValueError, TypeError):
                        votos = 0
                    totales[cand] = totales.get(cand, 0) + votos

            if not totales:
                continue

            ordenados         = sorted(totales.items(), key=lambda x: x[1], reverse=True)
            total_votos_depto = sum(v for _, v in ordenados)

            def pct(votos):
                return round(votos / total_votos_depto * 100, 1) if total_votos_depto > 0 else 0.0

            depto_result = {"nombre": nombre_depto}

            if ordenados:
                n1, v1 = ordenados[0]
                depto_result["primer_lugar"] = {"candidato": n1, "votos": v1, "porcentaje": pct(v1)}
            if len(ordenados) >= 2:
                n2, v2 = ordenados[1]
                depto_result["segundo_lugar"] = {"candidato": n2, "votos": v2, "porcentaje": pct(v2)}

            departamentos.append(depto_result)
            log.info(f"  {nombre_depto}: 1° {ordenados[0][0]}")

        except Exception as e:
            log.warning(f"Error en {nombre_depto}: {e}")
            continue

    log.info(f"Departamentos procesados: {len(departamentos)}")
    return {"meta": meta, "departamentos": departamentos}


def _parsear_texto_libre(texto: str) -> list:
    lineas     = [l.strip() for l in texto.splitlines() if l.strip()]
    candidatos = []
    for idx, li in enumerate(lineas):
        if "presidenc" in li.lower() and "vice" not in li.lower():
            nombre = None
            for back in range(1, 4):
                if idx - back >= 0:
                    cand = lineas[idx - back]
                    if cand and not any(t in cand.lower() for t in ("porcentaje", "%", "votos", "presidenc", "vice")):
                        nombre = re.sub(r"^nombre[:\s]*", "", cand, flags=re.IGNORECASE).strip()
                        break
            pct, votos = 0.0, 0
            for j in range(max(0, idx-3), min(len(lineas), idx+4)):
                m = re.search(r"([0-9]+[\.,]?[0-9]*)\s*%", lineas[j])
                if m and pct == 0.0:
                    try: pct = float(m.group(1).replace(",", "."))
                    except: pass
                m2 = re.search(r"(\d{1,3}(?:[\.\d]{0,}|\d*))(?=$|\s|,)", lineas[j].replace(" ", ""))
                if m2 and votos == 0:
                    try: votos = int(m2.group(1).replace(".", "").replace(",", ""))
                    except: pass
            if nombre:
                candidatos.append({"nombre": nombre, "porcentaje": pct, "votos": votos})
    return candidatos


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
    """
    Resultados por departamento desde los CSVs de El Espectador.
    """
    import datetime

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

            import csv, io
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
                        votos = int(str(row.get(f"Votos-{pos}", 0)).replace(",", "").replace(".", "") or 0)
                    except (ValueError, TypeError):
                        votos = 0
                    totales[cand] = totales.get(cand, 0) + votos

            if not totales:
                continue

            ordenados         = sorted(totales.items(), key=lambda x: x[1], reverse=True)
            total_votos_depto = sum(v for _, v in ordenados)

            def pct(votos):
                return round(votos / total_votos_depto * 100, 1) if total_votos_depto > 0 else 0.0

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