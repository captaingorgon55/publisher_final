"""
hootsuite_helper.py - Integracion con la API REST de Hootsuite v1.

Soporta:
- OAuth 2.0 (Authorization Code flow) con refresh tokens
- Listar social profiles conectados
- Publicar de inmediato, programar o guardar como borrador
- Adjuntar imagenes (upload a media endpoint primero)

Requiere plan Hootsuite Business o Enterprise con acceso API.
Docs: https://developer.hootsuite.com/docs
"""

import base64
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests


# ============================================================
# CONSTANTES
# ============================================================
# Endpoints OAuth correctos confirmados via test
AUTH_ENDPOINT = "https://platform.hootsuite.com/oauth2/auth"
TOKEN_ENDPOINT = "https://platform.hootsuite.com/oauth2/token"

# Base de la API REST v1 (para llamadas autenticadas con Bearer)
API_BASE = "https://platform.hootsuite.com/v1"
AUTH_BASE = "https://platform.hootsuite.com"

# Endpoints
ME_ENDPOINT = API_BASE + "/me"
SOCIAL_PROFILES_ENDPOINT = API_BASE + "/socialProfiles"
MESSAGES_ENDPOINT = API_BASE + "/messages"
MEDIA_ENDPOINT = API_BASE + "/media"

# Estados que devuelve la API
STATE_SCHEDULED = "SCHEDULED"
STATE_SEND_FAILED_PERMANENTLY = "SEND_FAILED_PERMANENTLY"
STATE_SENT = "SENT"


# ============================================================
# OAUTH FLOW
# ============================================================

def build_authorize_url(client_id, redirect_uri, scope="offline", state=None):
    """
    Construye la URL a la que se debe redirigir al usuario para que
    autorice la app en Hootsuite.

    scope='offline' es requerido para recibir refresh_token.
    state es un string opcional para prevenir CSRF (Streamlit lo usa).
    """
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
    }
    if state:
        params["state"] = state
    return AUTH_ENDPOINT + "?" + urlencode(params)


def _basic_auth_header(client_id, client_secret):
    """Genera el header Authorization: Basic xxx para el endpoint /token."""
    creds = client_id + ":" + client_secret
    b64 = base64.b64encode(creds.encode("utf-8")).decode("ascii")
    return "Basic " + b64

def exchange_code_for_token(code, client_id, client_secret, redirect_uri):
    """
    Intercambia un authorization code por un access_token + refresh_token.
    """
    headers = {
        "Authorization": _basic_auth_header(client_id, client_secret),
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        # Tambien mandar credenciales en el body por si el tenant lo requiere
        "client_id": client_id,
        "client_secret": client_secret,
    }

    try:
        resp = requests.post(
            TOKEN_ENDPOINT,
            headers=headers,
            data=data,
            timeout=20,
        )

        # Debug: registrar en logs y propagar info real
        print("HS exchange_code STATUS:", resp.status_code)
        print("HS exchange_code TEXT:", resp.text[:500])

        if resp.status_code != 200:
            raise Exception(
                "Hootsuite respondio HTTP " + str(resp.status_code)
                + " en " + TOKEN_ENDPOINT
                + " -> " + resp.text[:500]
            )

        token_data = resp.json()

        expires_in = int(token_data.get("expires_in", 3600))
        token_data["expires_at"] = int(time.time()) + expires_in - 60

        return token_data

    except requests.exceptions.RequestException as e:
        raise Exception("Error de red llamando a Hootsuite: " + str(e))

def refresh_access_token(refresh_token, client_id, client_secret):
    """
    Renueva el access_token usando el refresh_token.
    Intenta primero el endpoint v1, luego el viejo si falla.
    """
    headers = {
        "Authorization": _basic_auth_header(client_id, client_secret),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }

    last_error = None
    for endpoint in [TOKEN_ENDPOINT, TOKEN_ENDPOINT_FALLBACK]:
        try:
            resp = requests.post(endpoint, headers=headers, data=data, timeout=20)
            if resp.status_code == 200:
                token_data = resp.json()
                expires_in = int(token_data.get("expires_in", 3600))
                token_data["expires_at"] = int(time.time()) + expires_in - 60
                return token_data
            last_error = "HTTP " + str(resp.status_code) + " en " + endpoint + ": " + resp.text[:200]
        except Exception as e:
            last_error = "Excepcion en " + endpoint + ": " + str(e)

    raise Exception("Error al refrescar token. " + (last_error or ""))


def ensure_valid_token(token_data, client_id, client_secret):
    """
    Verifica que el access_token este vigente. Si no, lo refresca.
    Retorna el token_data actualizado (puede ser el mismo o uno nuevo).
    """
    if not token_data:
        raise Exception("No hay token. Conecta Hootsuite primero.")

    expires_at = token_data.get("expires_at", 0)
    if int(time.time()) < expires_at:
        return token_data  # todavia vigente

    refresh = token_data.get("refresh_token")
    if not refresh:
        raise Exception("Token expirado y no hay refresh_token. Reconecta Hootsuite.")

    return refresh_access_token(refresh, client_id, client_secret)


# ============================================================
# HEADERS Y HELPERS
# ============================================================

def _auth_headers(access_token):
    return {
        "Authorization": "Bearer " + access_token,
        "Content-Type": "application/json",
    }


def _check_response(resp, context=""):
    """Lanza excepcion con detalle si la respuesta no es 2xx."""
    if resp.status_code >= 400:
        prefix = ("[" + context + "] ") if context else ""
        raise Exception(prefix + "HTTP " + str(resp.status_code) + ": " + resp.text)
    return resp


# ============================================================
# ENDPOINTS DE LA API
# ============================================================

def get_me(access_token):
    """Devuelve info del usuario autenticado."""
    resp = requests.get(ME_ENDPOINT, headers=_auth_headers(access_token), timeout=15)
    _check_response(resp, "get_me")
    return resp.json().get("data", {})


def list_social_profiles(access_token):
    """
    Lista todos los social profiles conectados a la cuenta del usuario.

    Cada profile tiene: id, type (TWITTER, FACEBOOK, INSTAGRAM, ...),
    socialNetworkUsername, socialNetworkId, etc.
    """
    resp = requests.get(
        SOCIAL_PROFILES_ENDPOINT,
        headers=_auth_headers(access_token),
        timeout=15,
    )
    _check_response(resp, "list_social_profiles")
    return resp.json().get("data", [])

def upload_media(access_token, image_bytes, mime_type="image/png"):
    """
    Sube una imagen a Hootsuite en 2 pasos:
    1. POST /media -> devuelve uploadUrl (S3) e id
    2. PUT uploadUrl con los bytes de la imagen
    Retorna el id del media para usar en createMessage.
    """
    # === Paso 1: pedir uploadUrl ===
    payload = {
        "mimeType": mime_type,
        "sizeBytes": len(image_bytes),
    }

    resp = requests.post(
        MEDIA_ENDPOINT,
        headers=_auth_headers(access_token),
        json=payload,
        timeout=30,
    )

    print("HS upload_media STEP1 STATUS:", resp.status_code)
    print("HS upload_media STEP1 RESPONSE:", resp.text[:500])

    _check_response(resp, "upload_media (step 1)")

    data = resp.json().get("data", {})
    upload_url = data.get("uploadUrl")
    media_id = data.get("id")

    if not upload_url or not media_id:
        raise Exception(
            "upload_media: respuesta incompleta de Hootsuite: " + resp.text[:300]
        )

    # === Paso 2: subir bytes a S3 ===
    put_resp = requests.put(
        upload_url,
        data=image_bytes,
        headers={"Content-Type": mime_type},
        timeout=60,
    )

    print("HS upload_media STEP2 STATUS:", put_resp.status_code)
    print("HS upload_media STEP2 RESPONSE:", put_resp.text[:300])

    if put_resp.status_code not in (200, 201, 204):
        raise Exception(
            "upload_media (step 2 S3): HTTP " + str(put_resp.status_code)
            + ": " + put_resp.text[:300]
        )

    return media_id


def create_message(access_token, text, social_profile_ids,
                   scheduled_send_time=None, media_ids=None,
                   email_notification=False):
    """
    Crea un mensaje (publicacion) en Hootsuite.

    Args:
        text: texto del post (caption)
        social_profile_ids: lista de IDs de perfiles a publicar
        scheduled_send_time:
            None         -> programar para el proximo minuto (envio inmediato)
                            (Hootsuite no permite enviar exactamente "ahora",
                            pero podemos programar para 1-2 min en el futuro)
            datetime obj -> programar para esa fecha/hora (UTC)
        media_ids: lista de IDs devueltos por upload_media (opcional)
        email_notification: si Hootsuite debe mandar email cuando se publique

    Retorna: el mensaje creado con su id y state.
    """
    if not social_profile_ids:
        raise Exception("Se requiere al menos un socialProfileId")

    # Determinar fecha de envio
    if scheduled_send_time is None:
        # Envio "inmediato": +90 segundos para asegurar que pase validacion
        send_dt = datetime.now(timezone.utc).timestamp() + 90
        send_iso = datetime.fromtimestamp(send_dt, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    else:
        if isinstance(scheduled_send_time, datetime):
            if scheduled_send_time.tzinfo is None:
                # Asumir UTC si no tiene timezone
                scheduled_send_time = scheduled_send_time.replace(tzinfo=timezone.utc)
            send_iso = scheduled_send_time.astimezone(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        else:
            send_iso = str(scheduled_send_time)

    payload = {
        "text": text,
        "socialProfileIds": [str(pid) for pid in social_profile_ids],
        "scheduledSendTime": send_iso,
        "emailNotification": bool(email_notification),
    }

    if media_ids:
        payload["mediaIds"] = [str(m) for m in media_ids]

    # DEBUG: ver payload exacto
    print("HS create_message PAYLOAD:", payload)

    resp = requests.post(
        MESSAGES_ENDPOINT,
        headers=_auth_headers(access_token),
        json=payload,
        timeout=30,
    )

    # DEBUG: ver respuesta exacta
    print("HS create_message STATUS:", resp.status_code)
    print("HS create_message RESPONSE:", resp.text[:1000])

    _check_response(resp, "create_message")

    return resp.json().get("data", [])


def create_draft(access_token, text, social_profile_ids, media_ids=None):
    """
    Guarda un borrador en Hootsuite (no se publica).

    Nota: la API REST v1 no tiene un endpoint /drafts publico estable.
    Lo emulamos programando el mensaje muy en el futuro (year 2099),
    para que el usuario lo pueda mover/editar manualmente en Hootsuite.

    Si tu plan tiene acceso al endpoint privado /drafts, podes cambiar
    esta funcion para usarlo.
    """
    far_future = datetime(2099, 12, 31, 12, 0, 0, tzinfo=timezone.utc)
    return create_message(
        access_token,
        text=text,
        social_profile_ids=social_profile_ids,
        scheduled_send_time=far_future,
        media_ids=media_ids,
    )


def delete_message(access_token, message_id):
    """Elimina un mensaje programado."""
    url = MESSAGES_ENDPOINT + "/" + str(message_id)
    resp = requests.delete(url, headers=_auth_headers(access_token), timeout=15)
    _check_response(resp, "delete_message")
    return True


# ============================================================
# UTILIDADES DE ALTO NIVEL
# ============================================================

def publish_post(access_token, text, social_profile_ids,
                 image_bytes=None, image_mime="image/png",
                 mode="now", scheduled_time=None):
    """
    Wrapper de alto nivel para publicar.

    Args:
        text: caption del post
        social_profile_ids: lista de IDs de perfiles
        image_bytes: bytes de la imagen (opcional)
        image_mime: mime type de la imagen
        mode: "now" | "schedule" | "draft"
        scheduled_time: datetime requerido si mode="schedule"

    Retorna: respuesta de la API con info del/los mensajes creados.
    """
    media_ids = []
    if image_bytes:
        print("HS publish_post: subiendo imagen,", len(image_bytes), "bytes,", image_mime)
        try:
            media_id = upload_media(access_token, image_bytes, image_mime)
            print("HS publish_post: media_id recibido:", media_id, "tipo:", type(media_id).__name__)
            media_ids.append(media_id)
        except Exception as e:
            print("HS publish_post: ERROR subiendo imagen:", str(e))
            raise
    else:
        print("HS publish_post: SIN imagen (image_bytes vacio o None)")

    if mode == "now":
        return create_message(
            access_token, text, social_profile_ids,
            scheduled_send_time=None, media_ids=media_ids,
        )
    elif mode == "schedule":
        if not scheduled_time:
            raise Exception("scheduled_time es requerido para mode='schedule'")
        return create_message(
            access_token, text, social_profile_ids,
            scheduled_send_time=scheduled_time, media_ids=media_ids,
        )
    elif mode == "draft":
        return create_draft(
            access_token, text, social_profile_ids, media_ids=media_ids,
        )
    else:
        raise Exception("mode desconocido: " + str(mode))


# ============================================================
# FORMATEO PARA UI
# ============================================================

NETWORK_LABELS = {
    "TWITTER": "Twitter/X",
    "FACEBOOK": "Facebook (perfil)",
    "FACEBOOKPAGE": "Facebook (pagina)",
    "FACEBOOKGROUP": "Facebook (grupo)",
    "INSTAGRAM": "Instagram (personal)",
    "INSTAGRAMBUSINESS": "Instagram Business",
    "LINKEDIN": "LinkedIn (perfil)",
    "LINKEDINCOMPANY": "LinkedIn (empresa)",
    "YOUTUBECHANNEL": "YouTube",
    "PINTEREST": "Pinterest",
    "TIKTOKBUSINESS": "TikTok Business",
    "THREADS": "Threads",
}


def format_profile_label(profile):
    """Devuelve un label legible para un social profile."""
    net = profile.get("type", "?")
    username = profile.get("socialNetworkUsername", "")
    net_label = NETWORK_LABELS.get(net, net)
    if username:
        return net_label + " — @" + username
    return net_label + " (id " + str(profile.get("id", "?")) + ")"
