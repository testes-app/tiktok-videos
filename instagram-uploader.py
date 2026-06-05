import os
import sys
import argparse
import time
from pathlib import Path
from instagrapi import Client
from dotenv import load_dotenv

# Carrega as variaveis do .env
load_dotenv()

SESSION_FILE = Path("output_tiktok/.instagram_session.json")

def upload_instagram(video_path: str | Path, legenda: str) -> None:
    """Faz o upload de um video pro Instagram Reels."""
    username = os.environ.get("INSTAGRAM_USERNAME")
    password = os.environ.get("INSTAGRAM_PASSWORD")

    if not username or not password:
        raise ValueError("Credenciais do Instagram não encontradas! Adicione INSTAGRAM_USERNAME e INSTAGRAM_PASSWORD no arquivo .env")

    print("[INSTAGRAM] Iniciando integracao instagrapi...")
    cl = Client()

    # Tenta usar sessao salva para evitar bloqueios
    try:
        if SESSION_FILE.exists():
            print("[INFO] Usando sessao salva do Instagram...")
            cl.load_settings(SESSION_FILE)
            cl.login(username, password)
            cl.get_timeline_feed()  # Checagem de sanidade
        else:
            print("[INFO] Criando nova sessao de login...")
            cl.login(username, password)
    except Exception as e:
        print(f"[AVISO] Sessao invalida, recriando login: {e}")
        cl = Client()
        cl.login(username, password)
    
    # Salva a sessao valida
    cl.dump_settings(SESSION_FILE)
    print("[OK] Sessao autorizada no Instagram!")

    print(f"[UPLOAD] Enviando Reel: {video_path}...")
    # Faz upload (instagrapi extrai a thumbnail automaticamente se nao informada)
    # Adicionando um pequeno delay para seguranca de API
    time.sleep(2)
    
    media = cl.clip_upload(
        path=video_path,
        caption=legenda,
        extra_data={
            "custom_accessibility_caption": legenda[:100]
        }
    )

    print(f"[INSTAGRAM SUCESSO] Reels enviado! URL: https://www.instagram.com/reel/{media.code}/")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload automatico para Instagram Reels")
    parser.add_argument("video", help="Caminho para o arquivo MP4")
    parser.add_argument("legenda", help="Legenda do post")
    args = parser.parse_args()

    upload_instagram(args.video, args.legenda)
