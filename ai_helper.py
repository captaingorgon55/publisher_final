"""
ai_helper.py - Integracion con Google Gemini para mejorar contenido de posts.

Genera titulares optimizados, captions para Instagram, hashtags y sugiere
la plantilla mas apropiada segun el contenido del articulo.

Requiere:
    pip install google-generativeai

API key gratuita: https://aistudio.google.com/apikey
"""

import os
import json
import re

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


# Modelo recomendado: rapido y gratuito
DEFAULT_MODEL = "gemini-2.5-flash"

# Plantillas disponibles (deben coincidir con generator.TEMPLATES)
AVAILABLE_TEMPLATES = [
    "classic", "card", "with_cta", "attention", "story_minimal",
    "echemos_cuentas", "overlay_rojo", "overlay_negro", "overlay_gris",
    "colombia_20", "elecciones_2026",
    "foro_presidencial", "en_vivo", "gastronomia",
]

# Descripciones para guiar a la IA en la eleccion de plantilla
TEMPLATE_HINTS = {
    "classic": "Noticia general, foto principal con titulo blanco abajo. Default seguro.",
    "card": "Noticias suaves, cultura, entretenimiento. Fondo claro, sobrio.",
    "with_cta": "Cuando quieres invitar a leer la nota completa (formato lectura).",
    "attention": "Noticias de impacto, escandalos, denuncias. Bloque morado fuerte.",
    "story_minimal": "Solo para STORY 9:16. Formato vertical limpio.",
    "overlay_rojo": "Foto a sangre con overlay rojo y título blanco sencillo.",
    "overlay_negro": "Foto a sangre con overlay negro y título blanco sencillo.",
    "overlay_gris": "Foto a sangre con overlay gris y título blanco sencillo.",
    "echemos_cuentas": "Economia, finanzas personales, mercados. Marca Echemos Cuentas.",
    "colombia_20": "Ambiente, sostenibilidad, cambio climatico, biodiversidad. Marca Colombia +20.",
    "elecciones_2026": "Politica electoral, candidatos, campanas, votaciones 2026.",
    "foro_presidencial": "Entrevistas con candidatos presidenciales o eventos del foro.",
    "en_vivo": "Noticias en desarrollo, ultima hora, eventos en directo.",
    "gastronomia": "Recetas, restaurantes, cocina, chefs, criticas gastronomicas.",
}


def is_available():
    """True si la libreria google-generativeai esta instalada."""
    return GEMINI_AVAILABLE


def configure(api_key):
    """Configura la API key de Gemini."""
    if not GEMINI_AVAILABLE:
        raise ImportError(
            "google-generativeai no esta instalado. "
            "Ejecuta: pip install google-generativeai"
        )
    if not api_key:
        raise ValueError("API key vacia. Obten una en https://aistudio.google.com/apikey")
    genai.configure(api_key=api_key)


def _build_prompt(title, section, article_text, current_template=None):
    """Construye el prompt SEO en espanol para Gemini."""
    templates_list = "\n".join([
        f"- {t}: {TEMPLATE_HINTS[t]}" for t in AVAILABLE_TEMPLATES
    ])

    article_excerpt = (article_text or "")[:2500]

    return f"""Eres un editor digital experto en SEO y redes sociales para El Espectador, un periodico colombiano de calidad.

Tu tarea: optimizar este articulo para Instagram (post y story) con un enfoque SEO solido y atractivo, sin caer en clickbait barato. Manten el rigor periodistico.

ARTICULO ORIGINAL:
- Titulo: {title}
- Seccion: {section or "no especificada"}
- Contenido: {article_excerpt}

PLANTILLAS DISPONIBLES (elige la mas apropiada segun el contenido):
{templates_list}

DEVUELVE UNICAMENTE un JSON valido con esta estructura exacta (sin texto antes ni despues, sin markdown):

{{
  "titulo_post": "Titular optimizado para el post de Instagram. Maximo 90 caracteres. Que enganche pero sea preciso. Sin emojis. Sin signos de exclamacion abusivos.",
  "titulo_story": "Version mas corta del titular para story (vertical). Maximo 60 caracteres.",
  "caption_ig": "Caption completo para Instagram. 3-5 parrafos cortos. Inicia con un hook fuerte. Incluye contexto clave del articulo. Termina con una pregunta o invitacion a leer la nota completa en elespectador.com. Sin hashtags aqui. Tono profesional pero cercano.",
  "hashtags": ["lista", "de", "8", "a", "12", "hashtags", "relevantes", "sin", "numeral"],
  "plantilla_sugerida": "nombre_exacto_de_la_plantilla",
  "razon_plantilla": "Una frase breve explicando por que elegiste esa plantilla.",
  "palabras_clave_seo": ["3", "a", "5", "palabras", "clave"]
}}

REGLAS:
1. El titulo_post debe ser claro, preciso y atrapante. Nada de "no creeras lo que paso".
2. Los hashtags deben mezclar generales (#Colombia, #Noticias) con especificos del tema.
3. La plantilla_sugerida debe ser UNO de: {", ".join(AVAILABLE_TEMPLATES)}.
4. Si dudas entre plantillas, prefiere "classic" como default seguro.
5. NO uses comillas dobles dentro de los strings del JSON (usa simples si necesitas).
6. Responde SOLO el JSON. Nada mas."""


def _extract_json(text):
    """Extrae el JSON de la respuesta de Gemini (limpia markdown si aparece)."""
    if not text:
        return None
    # Quitar bloques markdown si vienen
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)
    # Buscar el primer { y el ultimo }
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    candidate = text[start:end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # Intento agresivo: reemplazar comillas simples por dobles donde aplique
        try:
            return json.loads(candidate.replace("'", '"'))
        except json.JSONDecodeError:
            return None


def enhance_content(title, section=None, article_text=None,
                    current_template=None, model=DEFAULT_MODEL):
    """
    Mejora el contenido del articulo usando Gemini.

    Args:
        title: Titulo original del articulo
        section: Seccion del articulo (opcional)
        article_text: Cuerpo del articulo extraido del HTML (opcional pero recomendado)
        current_template: Plantilla actualmente seleccionada (opcional, contexto)
        model: Modelo de Gemini a usar

    Returns:
        dict con keys:
            titulo_post, titulo_story, caption_ig, hashtags,
            plantilla_sugerida, razon_plantilla, palabras_clave_seo
        o None si falla.

    Raises:
        ImportError si google-generativeai no esta instalado.
        ValueError si la API key no esta configurada.
        Exception en otros errores de la API.
    """
    if not GEMINI_AVAILABLE:
        raise ImportError(
            "google-generativeai no esta instalado. "
            "Ejecuta: pip install google-generativeai"
        )

    prompt = _build_prompt(title, section, article_text, current_template)

    try:
        model_instance = genai.GenerativeModel(model)
        response = model_instance.generate_content(
            prompt,
            generation_config={
                "temperature": 0.7,
                "max_output_tokens": 8000,
                "response_mime_type": "application/json",
                "thinking_config": {"thinking_budget": 0},
            },
        )
    except Exception:
        # Algunos modelos viejos no soportan response_mime_type o thinking_config
        model_instance = genai.GenerativeModel(model)
        response = model_instance.generate_content(
            prompt,
            generation_config={
                "temperature": 0.7,
                "max_output_tokens": 8000,
            },
        )

    if not response or not response.text:
        print("[AI DEBUG] Respuesta vacia de Gemini")
        return None

    print("[AI DEBUG] Respuesta cruda de Gemini:")
    print("=" * 60)
    print(response.text)
    print("=" * 60)

    data = _extract_json(response.text)
    if not data:
        print("[AI DEBUG] No se pudo parsear JSON de la respuesta")
        return None

    print("[AI DEBUG] JSON parseado OK:")
    print(data)

    # Validar y normalizar la plantilla sugerida
    suggested = data.get("plantilla_sugerida", "").strip().lower()
    if suggested not in AVAILABLE_TEMPLATES:
        # Buscar match parcial
        match = None
        for t in AVAILABLE_TEMPLATES:
            if t in suggested or suggested in t:
                match = t
                break
        data["plantilla_sugerida"] = match or "classic"

    # Asegurar tipos
    if not isinstance(data.get("hashtags"), list):
        data["hashtags"] = []
    if not isinstance(data.get("palabras_clave_seo"), list):
        data["palabras_clave_seo"] = []

    # Limpiar hashtags (quitar # si vinieron con el)
    data["hashtags"] = [h.lstrip("#").strip() for h in data["hashtags"] if h]

    return data


def format_caption_with_hashtags(caption, hashtags):
    """Une el caption con los hashtags al final, listo para copiar a Instagram."""
    if not caption:
        return ""
    hashtag_str = " ".join([f"#{h}" for h in (hashtags or []) if h])
    if hashtag_str:
        return f"{caption}\n\n.\n.\n.\n{hashtag_str}"
    return caption
