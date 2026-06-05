#!/usr/bin/env python3
"""
TikTok Tech Pipeline - powered by Groq + Pexels Videos + ElevenLabs
Dependencias:
    pip install groq moviepy pillow elevenlabs python-dotenv requests

Uso:
    python tiktok-pipeline.py                          # tema aleatorio
    python tiktok-pipeline.py "meu tema" cyberpunk     # tema e estilo especificos
    python tiktok-pipeline.py "meu tema" cyberpunk --upload   # gera E sobe para o TikTok!
"""

import os
import json
import textwrap
import requests
import random
import tempfile
from io import BytesIO
from groq import Groq
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from moviepy import (
    AudioFileClip, ImageClip, VideoFileClip,
    concatenate_videoclips, CompositeVideoClip
)
from elevenlabs.client import ElevenLabs

load_dotenv()

TIKTOK_W, TIKTOK_H = 1080, 1920
MAX_DURATION        = 58
OUTPUT_DIR          = Path("output_tiktok")
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Limpeza de arquivos antigos ───────────────────────────────────────────────

def limpar_output_antigo():
    """Remove arquivos temporarios e videos antigos antes de gerar novo conteudo."""
    padroes = [
        "bg_video_*.mp4",
        "overlay_*.png", 
        "narracao.mp3",
        "roteiro.json",
        "tiktok_*.mp4",
    ]
    total = 0
    for padrao in padroes:
        for arquivo in OUTPUT_DIR.glob(padrao):
            arquivo.unlink()
            total += 1
    if total:
        print(f"[LIMPEZA] {total} arquivo(s) antigo(s) removido(s).")
    else:
        print("[LIMPEZA] Nenhum arquivo antigo encontrado.")

TEMAS = [
    "github repos mais estrelados esta semana",
    "ferramentas de IA que poucos conhecem",
    "linguagens de programacao em alta em 2026",
    "projetos open source incriveis para desenvolvedores",
    "dicas de produtividade para programadores",
]

# Queries de fallback tech para Pexels
QUERIES_TECH_VIDEO = [
    "technology",
    "coding",
    "artificial intelligence",
    "futuristic city",
    "data network",
    "digital abstract",
    "computer screen",
    "cyber security",
    "innovation",
    "programming",
]


# ── 0. Busca de Video de Fundo (Pexels API) ───────────────────────────────────

def buscar_video_pexels(query: str, duracao_slide: float, indice: int = 0) -> Path | None:
    """
    Busca um video portrait na Pexels API, baixa e retorna o caminho local.
    Tenta a query original e depois fallbacks tech.
    """
    api_key = os.environ.get("PEXELS_API_KEY", "")
    if not api_key:
        print("    [AVISO] PEXELS_API_KEY nao encontrada no .env")
        return None

    headers = {"Authorization": api_key}
    termos = [query] + [QUERIES_TECH_VIDEO[(indice + i) % len(QUERIES_TECH_VIDEO)] for i in range(5)]

    for termo in termos:
        print(f"    [VIDEO] Pexels: '{termo}'")
        try:
            params = {
                "query": termo,
                "orientation": "portrait",
                "size": "medium",
                "per_page": 15,
            }
            resp = requests.get(
                "https://api.pexels.com/videos/search",
                headers=headers,
                params=params,
                timeout=15,
            )
            videos = resp.json().get("videos", [])
            if not videos:
                continue

            # Embaralha levemente para variedade entre slides
            candidatos = videos[:]
            random.shuffle(candidatos)

            for vid in candidatos:
                dur = vid.get("duration", 0)
                # Aceita qualquer duracao (vamos fazer loop se necessario)
                arquivos = vid.get("video_files", [])

                # Prefere HD portrait (720p ou 1080p)
                hd_files = [
                    f for f in arquivos
                    if f.get("width", 0) <= f.get("height", 1)  # portrait
                    and f.get("height", 0) >= 720
                ]
                if not hd_files:
                    hd_files = [
                        f for f in arquivos
                        if f.get("width", 0) <= f.get("height", 1)
                    ]
                if not hd_files:
                    hd_files = arquivos  # fallback: qualquer arquivo

                if not hd_files:
                    continue

                # Escolhe o de melhor qualidade disponivel
                hd_files.sort(key=lambda f: f.get("height", 0), reverse=True)
                video_url = hd_files[0].get("link")
                if not video_url:
                    continue

                # Baixa o video
                print(f"    [OK] Baixando video ({dur}s, {hd_files[0].get('width')}x{hd_files[0].get('height')})...")
                vid_resp = requests.get(video_url, timeout=60, stream=True)
                vid_resp.raise_for_status()

                caminho = OUTPUT_DIR / f"bg_video_{indice:02d}.mp4"
                with open(caminho, "wb") as f:
                    for chunk in vid_resp.iter_content(chunk_size=1024 * 256):
                        f.write(chunk)

                print(f"    [OK] Video salvo: {caminho}")
                return caminho

        except Exception as e:
            print(f"    [ERRO] {e}")
            continue

    print("    [AVISO] Sem video disponivel — usando gradiente como fallback")
    return None


def criar_fundo_gradiente_video(cor1="#0a0a1a", cor2="#1a0a2e", duracao=12.0) -> ImageClip:
    """Cria um ImageClip com gradiente colorido como fallback de video."""
    img = Image.new("RGB", (TIKTOK_W, TIKTOK_H))
    draw = ImageDraw.Draw(img)
    r1,g1,b1 = int(cor1[1:3],16), int(cor1[3:5],16), int(cor1[5:7],16)
    r2,g2,b2 = int(cor2[1:3],16), int(cor2[3:5],16), int(cor2[5:7],16)
    for y in range(TIKTOK_H):
        t = y / TIKTOK_H
        draw.line([(0,y),(TIKTOK_W,y)], fill=(int(r1+(r2-r1)*t), int(g1+(g2-g1)*t), int(b1+(b2-b1)*t)))
    arr = __import__("numpy").array(img)
    return ImageClip(arr).with_duration(duracao)


# ── 1. Roteiro via Groq ───────────────────────────────────────────────────────

def gerar_roteiro(tema: str) -> dict:
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    prompt = f"""Crie um roteiro para um TikTok de tecnologia de 60 segundos sobre: {tema}

Retorne APENAS JSON valido, sem markdown, sem backticks:
{{
  "titulo": "titulo chamativo com emoji (max 60 chars)",
  "topicos": [
    {{"tempo": "0-10s", "texto": "gancho inicial"}},
    {{"tempo": "10-25s", "texto": "ponto 1"}},
    {{"tempo": "25-40s", "texto": "ponto 2"}},
    {{"tempo": "40-55s", "texto": "ponto 3"}},
    {{"tempo": "55-60s", "texto": "call to action"}}
  ],
  "narracao_completa": "texto corrido para narrar em 60 segundos (max 150 palavras)",
  "palavras_chave_imagem": ["frase em ingles slide1", "frase em ingles slide2", "frase em ingles slide3", "frase em ingles slide4", "frase em ingles slide5"],
  "hashtags": ["#tech", "#programacao", "#ia", "#python", "#github", "#developer", "#codigo", "#tecnologia"],
  "legenda_tiktok": "legenda completa para postar com hashtags"
}}"""

    resposta = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=1000,
    )
    texto = resposta.choices[0].message.content.strip()
    if "```" in texto:
        partes = texto.split("```")
        texto = partes[1]
        if texto.startswith("json"):
            texto = texto[4:]
    return json.loads(texto.strip())


# ── 2. Narracao via ElevenLabs ────────────────────────────────────────────────

def gerar_narracao(texto: str) -> Path:
    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    audio = client.text_to_speech.convert(
        text=texto,
        voice_id="JBFqnCBsd6RMkjVDRZzb",
        model_id="eleven_multilingual_v2",
        output_format="mp3_44100_128",
    )
    audio_bytes = b"".join(audio)
    caminho = OUTPUT_DIR / "narracao.mp3"
    with open(caminho, "wb") as f:
        f.write(audio_bytes)
    print(f"  [OK] Narracao salva: {caminho}")
    return caminho


# ── 3. Overlay de Texto (PNG RGBA transparente) ───────────────────────────────

def _hex_to_rgb(hex_color: str):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def criar_overlay_texto(titulo: str, texto: str, numero: int, total: int,
                        tema_cor: str = "cyberpunk") -> Path:
    """
    Gera um PNG RGBA com fundo transparente contendo apenas os elementos
    de texto/UI (barra de progresso, titulo, texto do slide, CTA).
    Este PNG sera sobreposto ao video de fundo via CompositeVideoClip.
    """
    paletas = {
        "cyberpunk": {"accent": "#00ff88", "secondary": "#ff0080", "text": "#ffffff"},
        "matrix":    {"accent": "#00ff41", "secondary": "#00aa00", "text": "#00ff41"},
        "neon":      {"accent": "#bf5fff", "secondary": "#06b6d4", "text": "#ffffff"},
        "minimal":   {"accent": "#ffffff", "secondary": "#aaaaaa", "text": "#ffffff"},
    }
    c = paletas.get(tema_cor, paletas["cyberpunk"])

    # Canvas totalmente transparente
    overlay = Image.new("RGBA", (TIKTOK_W, TIKTOK_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")

    # ── Barra de progresso no topo ──────────────────────────
    prog_w = int(TIKTOK_W * numero / total)
    draw.rectangle([0, 0, TIKTOK_W, 10], fill=(255, 255, 255, 40))
    draw.rectangle([0, 0, prog_w, 10], fill=(*_hex_to_rgb(c["accent"]), 230))

    # ── Fontes ──────────────────────────────────────────────
    try:
        fn = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 40)
        ft = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 64)
        fb = ImageFont.truetype("C:/Windows/Fonts/arial.ttf",   50)
        fr = ImageFont.truetype("C:/Windows/Fonts/arial.ttf",   38)
    except Exception:
        fn = ft = fb = fr = ImageFont.load_default()

    # ── Contador no topo esquerdo ───────────────────────────
    draw.text((28, 20), f"{numero:02d}/{total:02d}", font=fn, fill=(*_hex_to_rgb(c["accent"]), 230))

    # ── Gradiente escuro na metade inferior (para legibilidade do texto) ────
    # Faixa semi-opaca cobrindo os 38% inferiores (texto posicionado mais abaixo)
    TEXTO_TOP = int(TIKTOK_H * 0.62)
    for y in range(TEXTO_TOP, TIKTOK_H):
        t = (y - TEXTO_TOP) / (TIKTOK_H - TEXTO_TOP)
        alpha = int(180 * min(t * 1.5, 1.0))
        draw.line([(0, y), (TIKTOK_W, y)], fill=(0, 0, 0, alpha))

    # ── Titulo centralizado ──────────────────────────────────
    TEXTO_INICIO = int(TIKTOK_H * 0.64)

    palavras = titulo.upper().split()
    linha, linhas_tit = "", []
    for p in palavras:
        t_text = f"{linha} {p}".strip()
        if draw.textbbox((0, 0), t_text, font=ft)[2] <= TIKTOK_W - 80:
            linha = t_text
        else:
            if linha:
                linhas_tit.append(linha)
            linha = p
    if linha:
        linhas_tit.append(linha)

    for i, l in enumerate(linhas_tit):
        w = draw.textbbox((0, 0), l, font=ft)[2]
        x = (TIKTOK_W - w) // 2
        y = TEXTO_INICIO + i * 76
        # Sombra
        draw.text((x + 3, y + 3), l, font=ft, fill=(0, 0, 0, 180))
        draw.text((x, y), l, font=ft, fill=(*_hex_to_rgb(c["text"]), 255))

    # ── Linha separadora ────────────────────────────────────
    sep_y = TEXTO_INICIO + len(linhas_tit) * 76 + 24
    draw.rectangle([60, sep_y, TIKTOK_W - 60, sep_y + 4],
                   fill=(*_hex_to_rgb(c["secondary"]), 200))

    # ── Caixa de texto do slide ──────────────────────────────
    texto_y = sep_y + 40
    linhas_texto = textwrap.wrap(texto, width=28)[:5]
    box_h = len(linhas_texto) * 66 + 30

    # Fundo da caixa semi-transparente
    draw.rectangle([40, texto_y - 15, TIKTOK_W - 40, texto_y + box_h],
                   fill=(0, 0, 0, 150))

    for i, l in enumerate(linhas_texto):
        draw.text((73, texto_y + i * 66 + 3), l, font=fb, fill=(0, 0, 0, 180))
        draw.text((70, texto_y + i * 66), l, font=fb, fill=(*_hex_to_rgb(c["text"]), 255))

    # ── CTA rodape ──────────────────────────────────────────
    cta = "Segue para mais conteudo tech!"
    w_cta = draw.textbbox((0, 0), cta, font=fr)[2]
    draw.text(((TIKTOK_W - w_cta) // 2, TIKTOK_H - 90), cta, font=fr,
              fill=(*_hex_to_rgb(c["accent"]), 220))

    caminho = OUTPUT_DIR / f"overlay_{numero:02d}.png"
    overlay.save(caminho)
    return caminho


# ── 4. Clip de fundo (video ou gradiente) ────────────────────────────────────

def preparar_clip_fundo(video_path: Path | None, duracao: float,
                        tema_cor: str) -> VideoFileClip | ImageClip:
    """
    A partir do arquivo de video baixado, cria um VideoFileClip
    recortado em 9:16 (1080x1920), com loop/trim para a duracao do slide.
    Se nao houver video, retorna um ImageClip com gradiente.
    """
    paletas_grad = {
        "cyberpunk": ("#0a0a1a", "#1a0030"),
        "matrix":    ("#000000", "#001100"),
        "neon":      ("#0d0d1a", "#1a0d2e"),
        "minimal":   ("#111111", "#222222"),
    }
    grad_cores = paletas_grad.get(tema_cor, paletas_grad["cyberpunk"])

    if not video_path or not video_path.exists():
        return criar_fundo_gradiente_video(*grad_cores, duracao=duracao)

    try:
        clip = VideoFileClip(str(video_path))

        # ── Crop para cobrir 1080x1920 (cover) ──────────────
        vw, vh = clip.w, clip.h
        alvo_w, alvo_h = TIKTOK_W, TIKTOK_H
        aspect_alvo = alvo_w / alvo_h
        aspect_clip = vw / vh

        if aspect_clip > aspect_alvo:
            # Video mais largo: crop nas laterais
            new_w = int(vh * aspect_alvo)
            x1 = (vw - new_w) // 2
            clip = clip.cropped(x1=x1, y1=0, x2=x1 + new_w, y2=vh)
        else:
            # Video mais alto: crop em cima e embaixo
            new_h = int(vw / aspect_alvo)
            y1 = (vh - new_h) // 2
            clip = clip.cropped(x1=0, y1=y1, x2=vw, y2=y1 + new_h)

        clip = clip.resized((alvo_w, alvo_h))

        # ── Loop ou trim para a duracao do slide ─────────────
        if clip.duration < duracao:
            # Loop: repete o video ate preencher a duracao
            repeticoes = int(duracao / clip.duration) + 1
            from moviepy import concatenate_videoclips as _cat
            clip = _cat([clip] * repeticoes).subclipped(0, duracao)
        else:
            clip = clip.subclipped(0, duracao)

        # Remove audio do video de fundo (vamos usar apenas a narracao)
        clip = clip.without_audio()
        return clip

    except Exception as e:
        print(f"    [ERRO] Falha ao processar video de fundo: {e}")
        return criar_fundo_gradiente_video(*grad_cores, duracao=duracao)


# ── 5. Montagem do Video ──────────────────────────────────────────────────────

def montar_video(roteiro: dict, audio_path: Path, tema_cor: str) -> Path:
    slides_clips = []
    print("  [INFO] Baixando videos de fundo e montando slides...")

    palavras = roteiro.get(
        "palavras_chave_imagem",
        ["technology", "code", "artificial intelligence", "developer", "innovation"]
    )

    # Carrega audio para sincronizar duracao
    audio = AudioFileClip(str(audio_path))
    audio_dur = min(audio.duration, MAX_DURATION)
    n_slides = len(roteiro["topicos"])
    dur_por_slide = audio_dur / n_slides
    print(f"  [INFO] Audio: {audio_dur:.1f}s -> {dur_por_slide:.1f}s por slide")

    for i, topico in enumerate(roteiro["topicos"]):
        query = palavras[i] if i < len(palavras) else palavras[0]
        print(f"\n  [SLIDE {i+1}/{n_slides}] Query: '{query}'")

        # 1. Baixa video da Pexels
        video_path = buscar_video_pexels(query, dur_por_slide, indice=i)

        # 2. Prepara clip de fundo (video ou gradiente)
        clip_fundo = preparar_clip_fundo(video_path, dur_por_slide, tema_cor)

        # 3. Cria overlay de texto (PNG transparente)
        overlay_path = criar_overlay_texto(
            roteiro["titulo"], topico["texto"], i + 1, n_slides, tema_cor
        )

        # 4. Converte overlay PNG para ImageClip
        overlay_clip = (
            ImageClip(str(overlay_path))
            .with_duration(dur_por_slide)
        )

        # 5. Compoe: video de fundo + overlay de texto
        slide_final = CompositeVideoClip(
            [clip_fundo, overlay_clip],
            size=(TIKTOK_W, TIKTOK_H)
        )
        slides_clips.append(slide_final)
        print(f"  [OK] Slide {i+1} composto!")

    # Concatena todos os slides
    print("\n  [INFO] Concatenando slides...")
    video = concatenate_videoclips(slides_clips, method="compose")

    # Aplica audio da narracao
    if audio.duration > MAX_DURATION:
        audio = audio.subclipped(0, MAX_DURATION)
    video_final = video.with_audio(audio)

    # Exporta
    nome = "".join(
        ch for ch in roteiro["titulo"][:30] if ch.isalnum() or ch == "_"
    ).replace(" ", "_")
    saida = OUTPUT_DIR / f"tiktok_{nome}.mp4"

    print(f"\n  [EXPORTANDO] {saida}")
    video_final.write_videofile(
        str(saida),
        fps=30,
        codec="libx264",
        audio_codec="aac",
        bitrate="8000k",
        audio_bitrate="192k",
    )
    return saida


# ── 6. Pipeline Principal ─────────────────────────────────────────────────────

def rodar_pipeline(tema=None, tema_cor="cyberpunk", fazer_upload=False, fazer_upload_youtube=False, fazer_upload_instagram=False):
    limpar_output_antigo()  # ← adiciona essa linha aqui
    if not tema:
        tema = random.choice(TEMAS)

    print(f"\n[INICIO] Pipeline TikTok com Videos Pexels")
    print(f"[TEMA]   {tema}")
    print(f"[ESTILO] {tema_cor}")
    print(f"[UPLOAD TIKTOK]  {'SIM' if fazer_upload else 'NAO'}")
    print(f"[UPLOAD YOUTUBE] {'SIM' if fazer_upload_youtube else 'NAO'}\n")

    print("[1/3] Gerando roteiro com Groq (llama-3.3-70b)...")
    roteiro = gerar_roteiro(tema)
    print(f"  [OK] Titulo: {roteiro['titulo']}")

    with open(OUTPUT_DIR / "roteiro.json", "w", encoding="utf-8") as f:
        json.dump(roteiro, f, ensure_ascii=False, indent=2)

    print("\n[2/3] Gerando narracao com ElevenLabs...")
    audio = gerar_narracao(roteiro["narracao_completa"])

    print("\n[3/3] Montando video com fundos Pexels...")
    video = montar_video(roteiro, audio, tema_cor)

    print(f"\n[PRONTO] Video salvo: {video}")
    print(f"\n[LEGENDA]\n{roteiro['legenda_tiktok']}")

    # ── Upload automatico para o TikTok ───────────────────────────────────────
    if fazer_upload:
        try:
            import importlib.util, sys
            spec = importlib.util.spec_from_file_location("tiktok_uploader", "tiktok-uploader.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.CALLBACK_URL = None
            print("\n[UPLOAD TIKTOK] Iniciando publicacao no TikTok...")
            status = mod.publicar_no_tiktok(
                video_path=video,
                legenda=roteiro["legenda_tiktok"],
            )
            print(f"[UPLOAD TIKTOK] {status}")
        except Exception as e:
            print(f"[ERRO no upload TikTok] {e}")

    # ── Upload automatico para o YouTube ──────────────────────────────────────
    if fazer_upload_youtube:
        try:
            import importlib.util, sys
            spec = importlib.util.spec_from_file_location("youtube_uploader", "youtube-uploader.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            print("\n[UPLOAD YOUTUBE] Iniciando publicacao no YouTube Shorts...")
            mod.publicar_no_youtube(
                video_path=video,
                titulo=roteiro["titulo"],
                descricao=roteiro["legenda_tiktok"]
            )
        except Exception as e:
            print(f"[ERRO no upload YouTube] {e}")

    # ── Upload automatico para o Instagram ────────────────────────────────────
    if fazer_upload_instagram:
        try:
            import importlib.util, sys
            spec = importlib.util.spec_from_file_location("instagram_uploader", "instagram-uploader.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            print("\n[UPLOAD INSTAGRAM] Iniciando publicacao no Instagram Reels...")
            mod.upload_instagram(video, roteiro["legenda_tiktok"])
        except Exception as e:
            print(f"[ERRO no upload Instagram] {e}")

    if not fazer_upload and not fazer_upload_youtube and not fazer_upload_instagram:
        print("\n[DICA] Para publicar no TikTok, YouTube ou Instagram, use as flags correspondentes!")

    return video


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("tema", nargs="?", help="Tema do video")
    parser.add_argument("estilo", nargs="?", default="cyberpunk", help="Estilo visual")
    parser.add_argument("--upload", action="store_true", help="Faz o upload pro TikTok")
    parser.add_argument("--upload-youtube", action="store_true", help="Faz o upload pro YouTube Shorts")
    parser.add_argument("--upload-instagram", action="store_true", help="Faz o upload pro Instagram Reels")
    args = parser.parse_args()
    
    rodar_pipeline(
        tema=args.tema, 
        tema_cor=args.estilo, 
        fazer_upload=args.upload,
        fazer_upload_youtube=args.upload_youtube,
        fazer_upload_instagram=args.upload_instagram
    )