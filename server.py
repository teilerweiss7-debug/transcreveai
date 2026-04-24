"""
TranscreveAí — Servidor Backend
Recebe um link do YouTube, baixa o áudio e transcreve usando Groq Whisper (gratuito).
"""

import os
import re
import glob
import shutil
import tempfile
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from groq import Groq
import yt_dlp

app = Flask(__name__)
CORS(app)

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')

# Instâncias públicas do Invidious — intermediários que baixam o áudio do YouTube
INVIDIOUS_INSTANCES = [
    'https://invidious.io',
    'https://inv.nadeko.net',
    'https://invidious.privacyredirect.com',
    'https://yt.cdaut.de',
    'https://invidious.nerdvpn.de',
]


def extrair_video_id(url):
    match = re.search(r'(?:v=|youtu\.be/|embed/)([a-zA-Z0-9_-]{11})', url)
    return match.group(1) if match else None


def baixar_via_invidious(video_id, pasta):
    """Baixa áudio via Invidious — evita o bloqueio de bot do YouTube."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    for instancia in INVIDIOUS_INSTANCES:
        try:
            r = requests.get(
                f'{instancia}/api/v1/videos/{video_id}',
                timeout=15,
                headers=headers,
            )
            if r.status_code != 200:
                continue

            dados = r.json()
            audios = [
                f for f in dados.get('adaptiveFormats', [])
                if 'audio' in f.get('type', '')
            ]
            if not audios:
                continue

            melhor = sorted(audios, key=lambda x: x.get('bitrate', 0), reverse=True)[0]
            url_audio = melhor.get('url', '')
            if not url_audio:
                continue

            ext = '.webm' if 'webm' in melhor.get('type', '') else '.m4a'
            destino = os.path.join(pasta, f'audio{ext}')

            with requests.get(url_audio, stream=True, timeout=120, headers=headers) as dl:
                dl.raise_for_status()
                with open(destino, 'wb') as f:
                    shutil.copyfileobj(dl.raw, f)

            return destino

        except Exception:
            continue

    return None


def baixar_via_ytdlp(url, pasta, caminho_cookies=None):
    """Baixa áudio via yt-dlp (fallback caso Invidious falhe)."""
    opcoes = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'outtmpl': os.path.join(pasta, 'audio.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {'youtube': {'player_client': ['ios', 'web_creator']}},
    }
    if caminho_cookies:
        opcoes['cookiefile'] = caminho_cookies

    with yt_dlp.YoutubeDL(opcoes) as ydl:
        ydl.download([url])

    arquivos = glob.glob(os.path.join(pasta, 'audio.*'))
    return arquivos[0] if arquivos else None


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/api/status', methods=['GET'])
def status():
    return jsonify({
        'online': True,
        'groq_configurado': bool(GROQ_API_KEY),
    })


@app.route('/api/transcrever', methods=['POST'])
def transcrever():
    dados = request.get_json()
    url    = dados.get('url', '').strip()
    idioma = dados.get('idioma', 'pt')

    if not url:
        return jsonify({'erro': 'Nenhum link foi enviado.'}), 400

    if not GROQ_API_KEY:
        return jsonify({'erro': 'Chave da API Groq não configurada.'}), 500

    try:
        with tempfile.TemporaryDirectory() as pasta_temp:
            arquivo_audio = None

            # PASSO 1a: Tenta baixar via Invidious (sem bloqueio de bot)
            video_id = extrair_video_id(url)
            if video_id:
                arquivo_audio = baixar_via_invidious(video_id, pasta_temp)

            # PASSO 1b: Fallback — yt-dlp com cookies
            if not arquivo_audio:
                CAMINHO_SECRET = '/etc/secrets/youtube_cookies.txt'
                cookies_conteudo = ''
                temp_cookies = None

                if os.path.exists(CAMINHO_SECRET):
                    with open(CAMINHO_SECRET, 'r') as f:
                        cookies_conteudo = f.read()
                else:
                    cookies_conteudo = os.environ.get('YOUTUBE_COOKIES', '')

                if cookies_conteudo:
                    tc = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
                    tc.write(cookies_conteudo)
                    tc.close()
                    temp_cookies = tc.name

                try:
                    arquivo_audio = baixar_via_ytdlp(url, pasta_temp, temp_cookies)
                finally:
                    if temp_cookies:
                        os.unlink(temp_cookies)

            if not arquivo_audio:
                return jsonify({
                    'erro': 'Não foi possível baixar o áudio. O vídeo pode ser privado ou bloqueado.'
                }), 500

            # PASSO 2: Transcrever com Groq Whisper
            extensao = os.path.splitext(arquivo_audio)[1]
            cliente = Groq(api_key=GROQ_API_KEY)

            with open(arquivo_audio, 'rb') as f:
                resposta = cliente.audio.transcriptions.create(
                    file=(f'audio{extensao}', f),
                    model='whisper-large-v3',
                    language=idioma,
                    response_format='verbose_json',
                    timestamp_granularities=['segment'],
                )

            def pegar(obj, chave, padrao=None):
                if isinstance(obj, dict):
                    return obj.get(chave, padrao)
                return getattr(obj, chave, padrao)

            segments_raw   = pegar(resposta, 'segments') or []
            texto_completo = pegar(resposta, 'text') or ''

            if segments_raw:
                segmentos = [
                    {
                        'inicio': round(float(pegar(seg, 'start') or 0), 1),
                        'texto': (pegar(seg, 'text') or '').strip(),
                    }
                    for seg in segments_raw
                    if (pegar(seg, 'text') or '').strip()
                ]
            else:
                segmentos = [{'inicio': 0, 'texto': texto_completo.strip()}]

            return jsonify({
                'sucesso': True,
                'segmentos': segmentos,
                'total': len(segmentos),
            })

    except Exception as e:
        return jsonify({'erro': str(e)}), 500


if __name__ == '__main__':
    print('')
    print('  TranscreveAí — Servidor rodando!')
    print('  Acesse: http://localhost:8080')
    print('  Para parar: Ctrl+C')
    print('')
    porta = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=porta)
