"""
TranscreveAí — Servidor Backend
"""

import os
import re
import glob
import shutil
import tempfile
import html as html_module
import xml.etree.ElementTree as ET
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from groq import Groq
import yt_dlp

app = Flask(__name__)
CORS(app)

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')

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


# ── MÉTODO 1: Legendas do YouTube (rápido, confiável) ────────────────────────

def obter_legendas_xml(video_id, idioma):
    """Busca legendas via timedtext API. Retorna XML ou None."""
    base = 'https://video.google.com/timedtext'
    headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        r = requests.get(f'{base}?type=list&v={video_id}', timeout=10, headers=headers)
        if '<track' not in r.text:
            return None
    except Exception:
        return None

    for lang in [idioma, 'pt', 'en']:
        for kind in ['', 'asr']:
            try:
                params = {'v': video_id, 'lang': lang}
                if kind:
                    params['kind'] = kind
                r = requests.get(base, params=params, timeout=10, headers=headers)
                if r.status_code == 200 and '<text' in r.text:
                    return r.text
            except Exception:
                continue
    return None


def parsear_legendas(xml_texto):
    """Converte XML de legendas em lista de segmentos."""
    try:
        root = ET.fromstring(xml_texto)
        segmentos = []
        for el in root.findall('text'):
            inicio = round(float(el.get('start', 0)), 1)
            texto = html_module.unescape((el.text or '').replace('\n', ' ')).strip()
            if texto:
                segmentos.append({'inicio': inicio, 'texto': texto})
        return segmentos if segmentos else None
    except Exception:
        return None


# ── MÉTODO 2: Download de áudio via Invidious + Groq ─────────────────────────

def baixar_via_invidious(video_id, pasta):
    """Baixa áudio via Invidious API."""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'}

    for instancia in INVIDIOUS_INSTANCES:
        try:
            r = requests.get(f'{instancia}/api/v1/videos/{video_id}', timeout=15, headers=headers)
            if r.status_code != 200:
                continue
            dados = r.json()
            audios = [f for f in dados.get('adaptiveFormats', []) if 'audio' in f.get('type', '')]
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
            if os.path.getsize(destino) > 1000:
                return destino
        except Exception:
            continue
    return None


def baixar_via_ytdlp(url, pasta, caminho_cookies=None):
    """Baixa áudio via yt-dlp (último recurso)."""
    opcoes = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(pasta, 'audio.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
    }
    if caminho_cookies:
        opcoes['cookiefile'] = caminho_cookies

    with yt_dlp.YoutubeDL(opcoes) as ydl:
        ydl.download([url])

    arquivos = glob.glob(os.path.join(pasta, 'audio.*'))
    return arquivos[0] if arquivos else None


def transcrever_audio_groq(arquivo_audio, idioma):
    """Envia áudio para o Groq Whisper e retorna segmentos."""
    cliente = Groq(api_key=GROQ_API_KEY)
    extensao = os.path.splitext(arquivo_audio)[1]

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
        return [
            {
                'inicio': round(float(pegar(seg, 'start') or 0), 1),
                'texto': (pegar(seg, 'text') or '').strip(),
            }
            for seg in segments_raw
            if (pegar(seg, 'text') or '').strip()
        ]
    elif texto_completo:
        return [{'inicio': 0, 'texto': texto_completo.strip()}]
    return None


# ── ROTAS ─────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/api/status', methods=['GET'])
def status():
    return jsonify({'online': True, 'groq_configurado': bool(GROQ_API_KEY)})


@app.route('/api/transcrever', methods=['POST'])
def transcrever():
    dados = request.get_json()
    url    = dados.get('url', '').strip()
    idioma = dados.get('idioma', 'pt')

    if not url:
        return jsonify({'erro': 'Nenhum link foi enviado.'}), 400
    if not GROQ_API_KEY:
        return jsonify({'erro': 'Chave da API Groq não configurada.'}), 500

    video_id = extrair_video_id(url)
    if not video_id:
        return jsonify({'erro': 'Link do YouTube inválido.'}), 400

    try:
        # TENTATIVA 1: Legendas do YouTube (rápido, sem download de áudio)
        xml_legendas = obter_legendas_xml(video_id, idioma)
        if xml_legendas:
            segmentos = parsear_legendas(xml_legendas)
            if segmentos:
                return jsonify({
                    'sucesso': True,
                    'segmentos': segmentos,
                    'total': len(segmentos),
                })

        # TENTATIVA 2 e 3: Download de áudio + Groq Whisper
        with tempfile.TemporaryDirectory() as pasta_temp:
            arquivo_audio = None

            # Tenta Invidious primeiro
            arquivo_audio = baixar_via_invidious(video_id, pasta_temp)

            # Fallback: yt-dlp com cookies
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
                    'erro': 'Este vídeo não tem legendas e não foi possível baixar o áudio. Tente outro vídeo público.'
                }), 500

            segmentos = transcrever_audio_groq(arquivo_audio, idioma)
            if not segmentos:
                return jsonify({'erro': 'Não foi possível transcrever o áudio.'}), 500

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
