#!/usr/bin/env python3
"""
TikTok Uploader — OAuth 2.0 + Content Posting API
Faz upload automatico de videos para o TikTok via API oficial.

Uso:
    python tiktok-uploader.py caminho/do/video.mp4 "Legenda do video #hashtag"
"""

import os
import argparse
import sys
import json
import time
import hashlib
import base64
import secrets
import webbrowser
import threading
import requests
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, urlparse, parse_qs
from dotenv import load_dotenv

load_dotenv()

CLIENT_KEY    = os.environ.get("TIKTOK_CLIENT_KEY", "")
CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET", "")
REDIRECT_URI  = "https://testes-app.github.io/-sinaluz-legal/callback.html"
TOKEN_FILE    = Path("output_tiktok/.tiktok_token.json")

SCOPES = "user.info.basic,video.upload,video.publish"
CALLBACK_URL = None

# ── OAuth Local Server ────────────────────────────────────────────────────────

_auth_code = None
_auth_code_verifier = threading.Event()


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "code" in params:
            _auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            html = """
            <html><body style="font-family:sans-serif;text-align:center;padding:60px;background:#0a0a1a;color:#fff">
            <h1 style="color:#00ff88">&#10003; Autorizado com sucesso!</h1>
            <p>Pode fechar esta janela e voltar ao terminal.</p>
            </body></html>
            """
            self.wfile.write(html.encode())
            _auth_code_verifier.set()
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # silencia logs do servidor


_code_verifier = None  # guarda globalmente para usar no exchange


def obter_auth_code() -> str:
    """Obtém o código de autorização.
    Se o script for chamado com a opção ``--callback URL`` ele usa essa URL
    diretamente; caso contrário abre o navegador e solicita que o usuário cole
    a URL de callback, como antes.
    """
    global _code_verifier

    # PKCE — obrigatório na API v2 do TikTok
    _code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(_code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    params = {
        "client_key": CLIENT_KEY,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = "https://www.tiktok.com/v2/auth/authorize/?" + urlencode(params)

    # Se um callback foi passado via linha de comando, usa ele direto
    if CALLBACK_URL:
        callback_url = CALLBACK_URL
        print("[INFO] Usando URL de callback fornecida via argumento.")
    else:
        print(f"\n[AUTH] Abrindo navegador para autorizacao TikTok...")
        print(f"[AUTH] Se nao abrir, acesse:\n{auth_url}\n")
        webbrowser.open(auth_url)

        print("=" * 60)
        print("INSTRUCOES:")
        print("1. Autorize o app na pagina do TikTok que abriu")
        print("2. Voce sera redirecionado para uma pagina GitHub")
        print("3. Copie a URL COMPLETA da barra de endereco do navegador")
        print("   Exemplo: https://testes-app.github.io/-sinaluz-legal/callback?code=ABC123...")
        print("=" * 60)

        callback_url = input("\nCole aqui a URL completa do callback: ").strip()

    # Extrai o code da URL
    parsed = urlparse(callback_url)
    params_cb = parse_qs(parsed.query)

    if "code" not in params_cb:
        raise ValueError(f"Nao encontrei 'code' na URL: {callback_url}")

    code = params_cb["code"][0]
    print(f"[OK] Codigo de autorizacao recebido!")
    return code


def trocar_code_por_token(code: str) -> dict:
    """Troca o authorization code por access_token."""
    resp = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": CLIENT_KEY,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
            "code_verifier": _code_verifier,  # PKCE obrigatorio
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise Exception(f"Erro ao obter token: {data}")

    # Salva token localmente
    TOKEN_FILE.parent.mkdir(exist_ok=True)
    data["expires_at"] = time.time() + data.get("expires_in", 86400)
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"[OK] Token salvo em {TOKEN_FILE}")
    return data


def renovar_token(refresh_token: str) -> dict:
    """Renova o access_token usando o refresh_token."""
    resp = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": CLIENT_KEY,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    data["expires_at"] = time.time() + data.get("expires_in", 86400)
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print("[OK] Token renovado!")
    return data


def obter_token_valido() -> str:
    """
    Retorna um access_token valido.
    - Se ja tiver token salvo e valido, reutiliza.
    - Se expirado, renova via refresh_token.
    - Se nao tiver nada, faz o fluxo OAuth completo.
    """
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE) as f:
            token_data = json.load(f)

        expires_at = token_data.get("expires_at", 0)
        access_token = token_data.get("access_token", "")
        refresh_token = token_data.get("refresh_token", "")

        # Token ainda valido (com 5min de margem)
        if access_token and time.time() < expires_at - 300:
            print("[OK] Usando token TikTok existente.")
            return access_token

        # Token expirado mas tem refresh_token
        if refresh_token:
            print("[INFO] Token expirado, renovando...")
            try:
                token_data = renovar_token(refresh_token)
                return token_data["access_token"]
            except Exception as e:
                print(f"[AVISO] Falha ao renovar: {e} — fazendo novo login...")

    # Fluxo OAuth completo
    code = obter_auth_code()
    token_data = trocar_code_por_token(code)
    return token_data["access_token"]


# ── Upload do Video ───────────────────────────────────────────────────────────

def inicializar_upload(access_token: str, video_path: Path, legenda: str, privacidade: str = "SELF_ONLY") -> dict:
    """Inicializa o upload do video na API do TikTok (modo rascunho/inbox)."""
    tamanho = video_path.stat().st_size

    payload = {
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": tamanho,
            "chunk_size": tamanho,
            "total_chunk_count": 1,
        },
    }

    resp = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("error", {}).get("code") != "ok":
        raise Exception(f"Erro ao inicializar upload: {data}")

    return data["data"]


def enviar_video(upload_url: str, video_path: Path) -> None:
    """Envia o arquivo de video para a URL de upload fornecida pelo TikTok."""
    tamanho = video_path.stat().st_size
    print(f"[UPLOAD] Enviando {tamanho / 1024 / 1024:.1f} MB...")

    with open(video_path, "rb") as f:
        video_bytes = f.read()

    resp = requests.put(
        upload_url,
        headers={
            "Content-Range": f"bytes 0-{tamanho - 1}/{tamanho}",
            "Content-Length": str(tamanho),
            "Content-Type": "video/mp4",
        },
        data=video_bytes,
        timeout=300,
    )
    resp.raise_for_status()
    print("[OK] Video enviado!")


def verificar_status(access_token: str, publish_id: str) -> str:
    """Aguarda o TikTok processar e retorna o status final."""
    print("[INFO] Aguardando processamento do TikTok...")
    for tentativa in range(20):
        time.sleep(5)
        resp = requests.post(
            "https://open.tiktokapis.com/v2/post/publish/status/fetch/",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={"publish_id": publish_id},
            timeout=30,
        )
        data = resp.json()
        status = data.get("data", {}).get("status", "UNKNOWN")
        print(f"  [{tentativa+1}/20] Status: {status}")

        if status == "PUBLISH_COMPLETE":
            return "PUBLICADO COM SUCESSO no TikTok!"
        elif status == "SEND_TO_USER_INBOX":
            return "RASCUNHO ENVIADO — abra o TikTok e publique!"
        elif status in ("FAILED", "PUBLISH_FAILED"):
            raise Exception(f"Falha no upload: {data}")

    return "PROCESSANDO (verifique o TikTok manualmente)"


# ── Funcao Principal ──────────────────────────────────────────────────────────

def publicar_no_tiktok(video_path: str | Path, legenda: str,
                        privacidade: str = "SELF_ONLY") -> str:
    """
    Publica um video no TikTok.

    Args:
        video_path: Caminho para o arquivo .mp4
        legenda:    Texto da publicacao (com hashtags)
        privacidade: "SELF_ONLY" (privado) | "PUBLIC_TO_EVERYONE" | "FOLLOWER_OF_CREATOR"

    Returns:
        Status final da publicacao
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video nao encontrado: {video_path}")

    if not CLIENT_KEY or not CLIENT_SECRET:
        raise ValueError("TIKTOK_CLIENT_KEY e TIKTOK_CLIENT_SECRET nao configurados no .env")

    print(f"\n[TIKTOK] Iniciando upload de: {video_path.name}")
    print(f"[TIKTOK] Legenda: {legenda[:80]}...")

    # 1. Obtem token valido (OAuth se necessario)
    access_token = obter_token_valido()

    # 2. Inicializa o upload
    print("[INFO] Inicializando upload...")
    upload_info = inicializar_upload(access_token, video_path, legenda, privacidade)
    publish_id = upload_info["publish_id"]
    upload_url = upload_info["upload_url"]
    print(f"[OK] Publish ID: {publish_id}")

    # 3. Envia o video
    enviar_video(upload_url, video_path)

    # 4. Aguarda processamento
    status = verificar_status(access_token, publish_id)
    print(f"\n[RESULTADO] {status}")
    return status


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload de vídeo para TikTok")
    parser.add_argument("video", help="Caminho do arquivo de vídeo")
    parser.add_argument("legenda", nargs="?", default="Video gerado automaticamente #tech #ia #python", help="Legenda do vídeo")
    parser.add_argument("--callback", dest="callback", help="URL de callback completa obtida após autorização", default=None)
    args = parser.parse_args()

    CALLBACK_URL = args.callback

    try:
        publicar_no_tiktok(args.video, args.legenda)
    except Exception as e:
        print(f"\n[ERRO] {e}")
        sys.exit(1)