"""
llm_enhancer.py - Mejorador de scraping usando Google Gemini (LLM) para extraer
datos estructurados de la Registraduría cuando los endpoints JSON fallan o
devuelven HTML. También intenta extraer resultados territoriales (por departamento).

Requisitos:
    pip install google-generativeai beautifulsoup4 lxml  (beautifulsoap4 y lxml ya están en requirements.txt)

Uso:
    from llm_enhancer import get_candidatos_resultados_llm
    resultado = get_candidatos_resultados_llm()
    # resultado es un dict: {'nacional': [...], 'territorial': [...]}
"""

import os
import re
import json
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

import requests
from bs4 import BeautifulSoup

# Importar utilidades de generator.py y scraper_registraduria
try:
    from generator import (
        load_candidato_image,
        CANDIDATOS_NOMBRES,
        CANDIDATOS_PARTIDOS,
        BAR_COLORS,
        FORMATS,
    )
    _GENERATOR_AVAILABLE = True
except ImportError as e:
    _GENERATOR_AVAILABLE = False
    print(f"[llm_enhancer] Advertencia: generator.py no encontrado: {e}")

try:
    # Reusar mapeos y constantes del scraper existente
    from scraper_registraduria import (
        COLORES_CANDIDATOS,
        _NOMBRE_A_KEY,
        _normalizar_nombre,
        _key_desde_nombre,
        _enriquecer_candidatos,
        SNAPSHOT_DIR,
        _guardar_snapshot,
    )
    _SCRAPER_AVAILABLE = True
except ImportError as e:
    _SCRAPER_AVAILABLE = False
    print(f"[llm_enhancer] Advertencia: scraper_registraduria no encontrado: {e}")

# Configuración de Gemini (reusar de ai_helper si está disponible)
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# --- Constantes ---
LLM_ENDPOINTS = [
    "https://resultados.registraduria.gov.co/",
    "https://resultados.registraduria.gov.co/resultados/0/00/",
    "https://resultados.registraduria.gov.co/territorios/0/00/",
    "https://resultados.registradurai.gov.co/resultados/0/60010/",
    "https://resultados.registraduria.gov.co/territorios/0/60/",
    "https://resultados.registraduria.gov.co/preconteo",
    "https://resultados.registraduria.gov.co/escrutinio",
    "https://resultados.registraduria.gov.co/resultados",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
    "Referer": "https://resultados.registraduria.gov.co/",
    "Cache-Control": "no-cache",
}

REQUEST_TIMEOUT = 20

# Prompt para Gemini - extracción nacional y territorial
LLM_EXTRACTION_PROMPT = """
Eres un experto en extracción de datos estructurados de páginas web de resultados electorales de la Registraduría Nacional de Colombia.
Tu tarea es analizar el HTML proporcionado de la página de resultados y extraer:

1. Resultados nacionales (totales país) de los candidatos a la Presidencia.
2. Resultados territoriales (por departamento) si están disponibles en la misma página.

Debes devolver ÚNICAMENTE un JSON válido con el siguiente formato:

{
  "nacional": [
    {
      "nombre": "Nombre completo del candidato tal como aparece en la página",
      "porcentaje": numero_decimal_con_puntos (ej: 42.5),
      "votos": entero_de_votos (ej: 5200000)
    },
    ...
  ],
  "territorial": [
    {
      "departamento": "Nombre del departamento",
      "candidatos": [
        {
          "nombre": "Nombre del candidato",
          "porcentaje": numero_decimal_con_puntos,
          "votos": entero_de_votos (opcional, puede ser 0 si no se proporciona)
        }
      ]
    },
    ...
  ]
}

Reglas:
1. Para nacional: extrae SOLO los candidatos a la Presidencia (no autoridades locales, gobernadores, etc.).
2. El porcentaje puede venir con formato "42,5%" o "42.5%" - conviértelo a número decimal usando punto.
3. Los votos pueden venir con separadores de miles (puntos o comas) - elimínalos y conviértelo a entero.
4. Si no encuentras votos, usa 0.
5. Si no encuentras porcentaje, usa 0.0.
6. Incluye todos los candidatos que aparezcan en el listado o tabla principal de resultados nacionales.
7. Ordena la lista nacional de mayor a menor porcentaje.
8. Para territorial: si la página muestra una desglose por departamento, extrae cada departamento con sus candidatos y porcentajes.
   Si no hay datos territoriales claros, devuelve una lista vacía para "territorial".
9. No inventes datos; si no hay información útil, devuelve {"nacional": [], "territorial": []}.
10. No incluyas texto adicional antes ni después del JSON.
"""

def _configure_gemini(api_key: Optional[str] = None) -> bool:
    """Configura la API de Gemini si está disponible."""
    print(f"[llm_enhancer DEBUG] GEMINI_AVAILABLE={GEMINI_AVAILABLE}")
    if not GEMINI_AVAILABLE:
        print("[llm_enhancer DEBUG] Gemini not available")
        return False
    if not api_key:
        # Intentar leer de variable de entorno
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        print(f"[llm_enhancer DEBUG] API key from env: {api_key is not None}")
    if not api_key:
        print("[llm_enhancer] No se encontró API key para Gemini. Configure la variable de entorno GEMINI_API_KEY.")
        return False
    try:
        genai.configure(api_key=api_key)
        print("[llm_enhancer DEBUG] Gemini configured successfully")
        return True
    except Exception as e:
        print(f"[llm_enhancer] Error configurando Gemini: {e}")
        return False

def _fetch_page(url: str) -> Optional[str]:
    """Descarga la página HTML y devuelve el texto."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        print(f"[llm_enhancer DEBUG] GET {url} -> {resp.status_code}")
        if resp.status_code != 200:
            print(f"[llm_enhancer] HTTP {resp.status_code} para {url}")
            return None
        # Detectar si es probable que sea JSON y devolverlo tal cual para reuso
        ct = resp.headers.get("content-type", "")
        if "application/json" in ct:
            print(f"[llm_enhancer DEBUG] JSON content-type for {url}")
            return resp.text
        print(f"[llm_enhancer DEBUG] HTML length {len(resp.text)} for {url}")
        return resp.text
    except Exception as e:
        print(f"[llm_enhancer] Error descargando {url}: {e}")
        return None

def _extract_with_gemini(html_content: str) -> Optional[Dict[str, Any]]:
    """Envía el HTML a Gemini y intenta extraer la lista de candidatos nacionales y territoriales."""
    if not GEMINI_AVAILABLE:
        print("[llm_enhancer] Gemini no disponible.")
        return None
    # API key ya debería estar configurada vía _configure_gemini; Intentamos llamar y capturamos errores.
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = LLM_EXTRACTION_PROMPT + "\n\nHTML:\n" + html_content[:8000]
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.2,
                "max_output_tokens": 2000,
            },
        )
        if not response or not response.text:
            print("[llm_enhancer] Respuesta vacía de Gemini")
            return None
        print(f"[llm_enhancer DEBUG] Gemini raw response: {response.text[:200]}")
        # Extraer JSON
        text = response.text.strip()
        # Quitar bloques markdown si aparecen
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```\s*$", "", text)
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            print("[llm_enhancer] No se encontraron llaves en la respuesta de Gemini")
            return None
        json_str = text[start:end+1]
        data = json.loads(json_str)
        # Validar estructura mínima
        if not isinstance(data, dict):
            print("[llm_enhancer] Gemini no devolvió un dict")
            return None
        nacional = data.get("nacional", [])
        territorial = data.get("territorial", [])
        # Asegurar que sean listas
        if not isinstance(nacional, list):
            nacional = []
        if not isinstance(territorial, list):
            territorial = []
        return {"nacional": nacional, "territorial": territorial}
    except Exception as e:
        print(f"[llm_enhancer] Error en llamada a Gemini: {e}")
        return None

def _parse_html_fallback(html_content: str) -> Dict[str, Any]:
    """Intento de extracción usando BeautifulSoup en caso de que Gemini no esté disponible o falle."""
    # Intentar extraer nacionales con heurística básica
    nacionales_raw = []
    territoriales_raw = []
    soup = BeautifulSoup(html_content, "lxml")
    # Buscar tablas que puedan contener resultados
    tables = soup.find_all("table")
    for table in tables:
        # Analizar encabezados para decidir si es nacional o territorial
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if not headers:
            continue
        # Si la tabla tiene columnas como "Candidato", "Porcentaje", "Votos" probablemente sea nacional
        if any("candidato" in h for h in headers) and any("porcentaje" in h or "%" in h for h in headers):
            filas = table.find_all("tr")
            for fila in filas[1:]:  # saltar encabezado
                cols = fila.find_all(["td", "th"])
                if len(cols) >= 3:
                    texto = [c.get_text(strip=True) for c in cols]
                    # Heurística muy básica: primera columna nombre, segunda porcentaje, tercera votos
                    nombre = texto[0] if len(texto) > 0 else ""
                    pct_str = texto[1] if len(texto) > 1 else "0"
                    votos_str = texto[2] if len(texto) > 2 else "0"
                    try:
                        pct = float(pct_str.replace("%", "").replace(",", ".").strip())
                    except:
                        pct = 0.0
                    try:
                        votos = int(re.sub(r"[^\d]", "", votos_str))
                    except:
                        votos = 0
                    if nombre:
                        nacionales_raw.append({"nombre_raw": nombre, "porcentaje": pct, "votos": votos})
        # Si la tabla tiene una primera columna de departamento y luego columnas de candidatos, tratar como territorial
        elif any("departamento" in h or "depto" in h or "ciudad" in h for h in headers):
            # Asumir que la primera columna es departamento y el resto son candidatos
            filas = table.find_all("tr")
            if len(filas) > 1:
                # Encabezados de candidatos (excluyendo primera columna)
                candidato_headers = [th.get_text(strip=True) for th in filas[0].find_all("td")]  # simplificado
                # Mejor: usar th de la fila de encabezado
                # Para simplificar, dejaremos territorial vacío y dependeremos de LLM
                pass
    # Enriquecer nacionales si los tenemos
    nacionales = []
    if nacionales_raw:
        nacionales = _enriquecer_candidatos(nacionales_raw)
    # Territoriales: por ahora vacío (requiere LLM o heurística más compleja)
    territoriales = []
    return {"nacional": nacionales, "territorial": territoriales}

def get_candidatos_resultados_llm(max_candidatos: int = 5, verbose: bool = True) -> Dict[str, Any]:
    """
    Obtiene los resultados de candidatos usando:
    1. Primero intenta los endpoints JSON existentes (reuso de scraper_registraduria).
    2. Si falla, usa LLM (Gemini) sobre el HTML de la página principal.
    3. Si LLM no está disponible o falla, intenta extracción heurística con BeautifulSoup.
    Enriquece los datos con key, nombre formal, foto, color de barra, etc.
    Retorna un dict con claves 'nacional' y 'territorial'.
    """
    if verbose:
        print(f"[llm_enhancer] Iniciando obtención de resultados ({datetime.now().strftime('%H:%M:%S')})")

    # --- 1. Intentar con el scraper existente (endpoints JSON) ---
    if _SCRAPER_AVAILABLE:
        try:
            from scraper_registraduria import get_candidatos_resultados
            nacionales = get_candidatos_resultados(max_candidatos=max_candidatos, verbose=False)
            if nacionales:
                if verbose:
                    print(f"[llm_enhancer] ✓ Resultados obtenidos vía scraper tradicional: {len(nacionales)} candidatos")
                # Devolver nacional y territorial vacío (el scraper tradicional no da territorial)
                return {"nacional": nacionales, "territorial": []}
        except Exception as e:
            if verbose:
                print(f"[llm_enhancer] Scraper tradicional falló: {e}")

    # --- 2. Intentar con LLM sobre HTML ---
    if _configure_gemini():
        for url in LLM_ENDPOINTS:
            if verbose:
                print(f"[llm_enhancer] Consultando {url} para LLM...")
            html = _fetch_page(url)
            if not html:
                continue
            # Si parece JSON, intentar parsearlo directamente
            stripped = html.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    data = json.loads(html)
                    # Intentar extraer nacional usando la lógica existente
                    nacionales_raw = []
                    if isinstance(data, dict) and "candidatos" in data:
                        raw = data["candidatos"]
                    elif isinstance(data, list):
                        raw = data
                    else:
                        raw = []
                    if raw:
                        nacionales = _enriquecer_candidatos(raw)
                        nacionales = nacionales[:max_candidatos]
                        if verbose:
                            print(f"[llm_enhancer] ✓ Resultados nacionales obtenidos vía JSON directo: {len(nacionales)} candidatos")
                        # Intentar extraer territorial si el JSON tiene alguna estructura de departamentos
                        # Por ahora dejamos territorial vacío
                        return {"nacional": nacionales, "territorial": []}
                except Exception:
                    pass  # no es JSON válido, continuar a LLM
            # Llamar a Gemini
            resultado = _extract_with_gemini(html)
            if resultado:
                nationals = resultado.get("nacional", [])
                territorio = resultado.get("territorial", [])
                # Enriquecer nacionales
                if nationals:
                    nationals_raw = [{"nombre_raw": c["nombre"], "porcentaje": c["porcentaje"], "votos": c["votos"]} for c in nationals]
                    nationals = _enriquecer_candidatos(nationals_raw)
                    nationals = nationals[:max_candidatos]
                if verbose:
                    print(f"[llm_enhancer] ✓ Resultados obtenidos vía LLM: {len(nationals)} nacionales, {len(territorio)} territoriales")
                return {"nacional": nationals, "territorial": territorio}
            else:
                if verbose:
                    print(f"[llm_enhancer] LLM no retornó datos válidos para {url}")

    # --- 3. Fallback heurístico con BeautifulSoup ---
    for url in LLM_ENDPOINTS:
        html = _fetch_page(url)
        if not html:
            continue
        resultado = _parse_html_fallback(html)
        nationals = resultado.get("nacional", [])
        territorio = resultado.get("territorial", [])
        if nationals:
            if verbose:
                print(f"[llm_enhancer] ✓ Resultados obtenidos vía heurística: {len(nationals)} nacionales, {len(territorio)} territoriales")
            return {"nacional": nationals, "territorial": territorio}

    # Si llegamos aquí, no se obtuvieron datos
    msg = (
        f"\n[llm_enhancer] ✗ No se pudo obtener datos de ningún método.\n"
        f"  Posibles causas:\n"
        f"  1. La Registraduría aún no ha publicado resultados.\n"
        f"  2. Todos los endpoints están bloqueados o cambiaron de estructura.\n"
        f"  3. Falta API key válida para Gemini (variable de entorno GEMINI_API_KEY).\n"
        f"  4. Problemas de conectividad o timeout.\n"
    )
    if verbose:
        print(msg)
    # Devolver estructuras vacías en lugar de lanzar excepción para no romper flujo
    return {"nacional": [], "territorial": []}

# --- Funciones de alto nivel para generar tarjetas (similar a scraper_registraduria) ---
def generar_tarjeta_resultados_llm(
    format_key: str = "post",
    boletin_text: str = "",
    output_path: Optional[str] = None,
    candidatos: Optional[List[Dict[str, Any]]] = None,
    max_candidatos: int = 5,
    usar_snapshot_si_falla: bool = True,
    verbose: bool = True,
):
    """
    Flujo completo: obtiene datos (vía LLM si es necesario) + genera tarjeta PIL.
    Reutiliza la lógica de generator.py para renderizado.
    Si se proporciona 'candidatos', se asume que son los nacionales.
    """
    if not _GENERATOR_AVAILABLE:
        raise ImportError("generator.py no encontrado. Asegúrate de ejecutar desde el mismo directorio.")

    # 1. Obtener candidatos
    if candidatos is None:
        resultado = get_candidatos_resultados_llm(max_candidatos=max_candidatos, verbose=verbose)
        candidatos = resultado.get("nacional", [])
        if not candidatos and usar_snapshot_si_falla:
            try:
                from scraper_registraduria import cargar_ultimo_snapshot
                candidatos = cargar_ultimo_snapshot()
                if verbose:
                    print("[llm_enhancer] Usando snapshot como fallback.")
            except Exception:
                pass
        if not candidatos:
            raise ValueError("No hay candidatos para renderizar.")

    # 2. Generar imagen (reutilizando render_resultados_candidatos de generator)
    try:
        from generator import render_resultados_candidatos
    except ImportError:
        raise ImportError("No se encontró render_resultados_candidatos en generator.py")

    img = render_resultados_candidatos(
        candidatos=candidatos,
        format_key=format_key,
        boletin_text=boletin_text,
    )

    # 3. Guardar o retornar
    if output_path:
        img.save(output_path, "PNG", quality=95)
        if verbose:
            print(f"[llm_enhancer] ✓ Tarjeta guardada: {output_path}")
        return None
    return img

if __name__ == "__main__":
    # Ejemplo de uso rápido
    print("=== LLM Enhancer Test ===")
    resultado = get_candidatos_resultados_llm(verbose=True)
    cands = resultado.get("nacional", [])
    territorio = resultado.get("territorial", [])
    if cands:
        print(f"Obtenidos {len(cands)} candidatos nacionales:")
        for c in cands:
            print(f"  {c.get('nombre')} - {c.get('porcentaje')}% ({c.get('votos'):,} votos)")
    else:
        print("No se obtuvieron candidatos nacionales.")
    if territorio:
        print(f"Territorial: {len(territorio)} departamentos")
        for depto in territorio[:3]:  # mostrar solo primeros 3
            print(f"  {depto.get('departamento')}: {len(depto.get('candidatos', []))} candidatos")