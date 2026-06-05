import os
import sys
import argparse
from pathlib import Path
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRETS_FILE = "client_secrets.json"
TOKEN_FILE = Path("output_tiktok/.youtube_token.json")

def obter_credenciais():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRETS_FILE):
                raise FileNotFoundError(
                    f"O arquivo {CLIENT_SECRETS_FILE} nao foi encontrado na raiz do projeto. "
                    "Baixe suas credenciais OAuth do Google Cloud Console e salve com esse nome."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Salva o token para proximas vezes
        TOKEN_FILE.parent.mkdir(exist_ok=True)
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
    return creds

def publicar_no_youtube(video_path: str | Path, titulo: str, descricao: str):
    print(f"\n[YOUTUBE] Iniciando upload de: {Path(video_path).name}")
    creds = obter_credenciais()
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": titulo[:100],  # Titulo no YouTube Shorts tem limite de 100 caracteres
            "description": descricao,
            "tags": ["tech", "programacao", "developer", "shorts"],
            "categoryId": "28" # 28 = Science & Technology
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }
    }

    print("[INFO] Preparando envio de video (pode demorar alguns minutos)...")
    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  [UPANDO] {int(status.progress() * 100)}%")

    print(f"\n[YOUTUBE SUCESSO] Video enviado! ID: {response.get('id')}")
    print(f"URL Direta: https://youtube.com/shorts/{response.get('id')}")
    return response.get('id')

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("video")
    parser.add_argument("titulo")
    parser.add_argument("descricao", nargs="?", default="")
    args = parser.parse_args()

    try:
        publicar_no_youtube(args.video, args.titulo, args.descricao)
    except Exception as e:
        print(f"\n[ERRO YOUTUBE] {e}")
        sys.exit(1)
