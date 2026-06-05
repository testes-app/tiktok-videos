# 🎬 TikTok Tech Pipeline

Cria vídeos de tecnologia para TikTok automaticamente usando IA.

## Fluxo
```
Tema → Claude (roteiro) → ElevenLabs (voz) → Pillow (frames) → MoviePy (vídeo)
```

## Instalação

```bash
pip install anthropic elevenlabs moviepy pillow python-dotenv requests
```

## Configuração

```bash
cp .env.example .env
# Edite o .env com suas chaves de API
```

## Uso

```bash
# Tema aleatório, estilo cyberpunk (padrão)
python tiktok_pipeline.py

# Tema específico
python tiktok_pipeline.py "5 repos python que vão te surpreender"

# Tema + estilo visual
python tiktok_pipeline.py "ferramentas de IA 2026" neon
python tiktok_pipeline.py "linguagens populares" matrix
python tiktok_pipeline.py "dicas de produtividade" minimal
```

## Estilos visuais disponíveis
| Estilo     | Visual                          |
|------------|---------------------------------|
| `cyberpunk`| Verde neon no fundo escuro      |
| `matrix`   | Verde matrix clássico           |
| `neon`     | Roxo e ciano                    |
| `minimal`  | Branco e cinza limpo            |

## Saída
Os arquivos ficam na pasta `output_tiktok/`:
- `tiktok_TITULO.mp4` — vídeo pronto (1080×1920, 30fps)
- `roteiro.json` — roteiro completo com hashtags e legenda
- `narracao.mp3` — áudio gerado
- `frame_XX.png` — frames individuais

## Custo estimado por vídeo
| API         | Custo aprox. |
|-------------|-------------|
| Claude      | ~R$ 0,05    |
| ElevenLabs  | ~R$ 0,25    |
| **Total**   | **~R$ 0,30**|

## APIs necessárias
- **Anthropic**: https://console.anthropic.com
- **ElevenLabs**: https://elevenlabs.io (plano gratuito = 10k chars/mês)
