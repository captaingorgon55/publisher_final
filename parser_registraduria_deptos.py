"""
parser_registraduria_deptos.py
Parser del formato de texto de la Registraduría Nacional (segunda vuelta).

Uso:
    from parser_registraduria_deptos import parsear_texto_registraduria
    deptos = parsear_texto_registraduria(texto_pegado)
"""

DEPTO_ALIAS = {
    "BOGOTA D.C.":   "BOGOTÁ D.C.",
    "BOGOTÁ D.C.":   "BOGOTÁ D.C.",
    "NORTE DE SAN":  "NORTE DE SANTANDER",
    "ATLANTICO":     "ATLÁNTICO",
    "BOLIVAR":       "BOLÍVAR",
    "BOYACA":        "BOYACÁ",
    "CAQUETA":       "CAQUETÁ",
    "CHOCO":         "CHOCÓ",
    "CORDOBA":       "CÓRDOBA",
    "GUAINIA":       "GUAINÍA",
    "NARINO":        "NARIÑO",
    "QUINDIO":       "QUINDÍO",
    "SAN ANDRES":    "SAN ANDRÉS Y PROVIDENCIA",
    "VAUPES":        "VAUPÉS",
    "VALLE":         "VALLE DEL CAUCA",
    "CONSULADOS":    None,   # ignorar
}

PARTIDO_CANDIDATO = {
    "PACTO":      "IVÁN CEPEDA",
    "DEFENSORES": "ABELARDO DE LA ESPRIELLA",
}

PALABRAS_NO_DEPTO = {
    "MOVIMIENTO","POLÍTICO","PACTO","HISTÓRICO","DEFENSORES","PATRIA",
    "POLITICO","HISTORICO","COLOMBIA","REPÚBLICA","NACIONAL",
}


def _es_nombre_depto(linea):
    l = linea.strip()
    if not l or l == "-": return False
    if "%" in l: return False
    if any(c.isdigit() for c in l): return False
    if l != l.upper(): return False
    if set(l.split()) & PALABRAS_NO_DEPTO: return False
    if l.startswith("Pte") or l.startswith("Vpte"): return False
    if len(l) < 3: return False
    return True


def parsear_texto_registraduria(texto: str) -> list:
    """
    Parsea el texto copiado de la Registraduría Nacional y devuelve
    una lista de departamentos con su ganador.

    Returns:
        Lista de dicts compatible con render_mapa_sv():
        [{ nombre, primer_lugar: { candidato, porcentaje, votos } }, ...]
    """
    lineas     = [l.strip() for l in texto.splitlines()]
    resultados = []
    i          = 0

    while i < len(lineas):
        linea = lineas[i]
        if _es_nombre_depto(linea):
            nombre_depto = linea.strip()
            nombre_norm  = DEPTO_ALIAS.get(nombre_depto, nombre_depto)

            if nombre_norm is None:   # CONSULADOS u otros ignorados
                i += 1
                continue

            partido = pct = votos = None
            j = i + 1

            while j < len(lineas) and j < i + 30:
                l = lineas[j].strip()

                if not partido:
                    for key, cand in PARTIDO_CANDIDATO.items():
                        if key in l.upper():
                            partido = cand
                            # votos: línea siguiente con solo dígitos
                            if j+1 < len(lineas):
                                v = lineas[j+1].strip().replace(".","").replace(",","")
                                if v.isdigit():
                                    votos = int(v)
                            # porcentaje: línea siguiente+1 con %
                            if j+2 < len(lineas):
                                p = lineas[j+2].strip()
                                if "%" in p:
                                    try:
                                        pct = float(p.replace("%","").replace(",",".").strip())
                                    except ValueError:
                                        pass
                            break

                # Fin de bloque cuando empieza el siguiente departamento
                if j > i+3 and _es_nombre_depto(l):
                    break
                j += 1

            if partido and pct is not None:
                resultados.append({
                    "nombre": nombre_norm,
                    "primer_lugar": {
                        "candidato":  partido.upper(),
                        "porcentaje": pct,
                        "votos":      votos or 0,
                    }
                })
            i = j
        else:
            i += 1

    return resultados