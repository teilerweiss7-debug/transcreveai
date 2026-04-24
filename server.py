"""
TranscreveAí — Servidor Backend
"""

import os
import re
import glob
import json
import shutil
import tempfile
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from groq import Groq
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

app = Flask(__name__)
CORS(app)

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')


def extrair_video_id(url):
    match = re.search(r'(?:v=|youtu\.be/|embed/)([a-zA-Z0-9_-]{11})', url)
    return match.group(1) if match else None


def _cookies_path():
    """Retorna o caminho do arquivo de cookies, ou None se não existir."""
    path = '/etc/secrets/youtube_cookies.txt'
    if os.path.exists(path):
        return path
    env_cookies = os.environ.get('YOUTUBE_COOKIES', '')
    if env_cookies:
        tc = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        tc.write(env_cookies)
        tc.close()
        return tc.name
    return None


# ── MÉTODO 1: youtube-transcript-api ────────────────────────────────────────

def obter_legendas_api(video_id, idioma):
    print(f'[legendas-api] tentando video_id={video_id} idioma={idioma}')
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        for lang in [idioma, 'pt', 'pt-BR', 'en']:
            try:
                t = transcript_list.find_transcript([lang])
                dados = t.fetch()
                resultado = _parsear_transcript(dados)
                if resultado:
                    print(f'[legendas-api] sucesso com idioma={lang}, {len(resultado)} segmentos')
                    return resultado
            except Exception as e:
                print(f'[legendas-api] falhou lang={lang}: {e}')
                continue
        # Pega qualquer idioma disponível
        for t in transcript_list:
            try:
                dados = t.fetch()
                resultado = _parsear_transcript(dados)
                if resultado:
                    print(f'[legendas-api] sucesso com qualquer idioma, {len(resultado)} segmentos')
                    return resultado
            except Exception as e:
                print(f'[legendas-api] falhou idioma genérico: {e}')
                continue
    except (TranscriptsDisabled, NoTranscriptFound) as e:
        print(f'[legendas-api] legendas desativadas ou não encontradas: {e}')
    except Exception as e:
        print(f'[legendas-api] erro geral: {e}')
    return None


def _parsear_transcript(dados):
    segmentos = []
    for s in dados:
        texto = (s.get('text', '') if isinstance(s, dict) else getattr(s, 'text', '')).replace('\n', ' ').strip()
        inicio = s.get('start', 0) if isinstance(s, dict) else getattr(s, 'start', 0)
        if texto:
            segmentos.append({'inicio': round(float(inicio), 1), 'texto': texto})
    return segmentos if segmentos else None


# ── MÉTODO 2: yt-dlp só para legendas (usa cookies) ─────────────────────────

def obter_legendas_ytdlp(video_id, idioma):
    print(f'[legendas-ytdlp] tentando video_id={video_id}')
    url = f'https://www.youtube.com/watch?v={video_id}'
    cookies = _cookies_path()

    with tempfile.TemporaryDirectory() as pasta:
        opcoes = {
            'skip_download': True,
            'writeautomaticsub': True,
            'writesubtitles': True,
            'subtitleslangs': [idioma, 'pt', 'en', 'pt-BR'],
            'subtitlesformat': 'json3',
            'outtmpl': os.path.join(pasta, 'sub'),
            'quiet': True,
            'no_warnings': True,
        }
        if cookies:
            opcoes['cookiefile'] = cookies

        try:
            with yt_dlp.YoutubeDL(opcoes) as ydl:
                ydl.download([url])

            arquivos = glob.glob(os.path.join(pasta, '*.json3'))
            print(f'[legendas-ytdlp] arquivos encontrados: {arquivos}')
            if arquivos:
                resultado = _parsear_json3(arquivos[0])
                if resultado:
                    print(f'[legendas-ytdlp] sucesso, {len(resultado)} segmentos')
                    return resultado
        except Exception as e:
            print(f'[legendas-ytdlp] erro: {e}')

    return None


def _parsear_json3(caminho):
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        segmentos = []
        for evento in dados.get('events', []):
            inicio = evento.get('tStartMs', 0) / 1000
            texto = ''.join(s.get('utf8', '') for s in evento.get('segs', [])).replace('\n', ' ').strip()
            if texto:
                segmentos.append({'inicio': round(float(inicio), 1), 'texto': texto})
        return segmentos if segmentos else None
    except Exception as e:
        print(f'[json3] erro ao parsear: {e}')
        return None


# ── MÉTODO 3: cobalt.tools + Groq ────────────────────────────────────────────

def baixar_via_cobalt(url, pasta):
    print('[cobalt] tentando download de áudio')
    for fmt in ['mp3', 'opus', 'best']:
        try:
            r = requests.post(
                'https://api.cobalt.tools/',
                json={'url': url, 'downloadMode': 'audio', 'audioFormat': fmt},
                headers={
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'User-Agent': 'Mozilla/5.0',
                },
                timeout=30,
            )
            print(f'[cobalt] status HTTP={r.status_code} formato={fmt} resposta={r.text[:200]}')
            if r.status_code != 200:
                continue
            dados = r.json()
            status = dados.get('status')
            download_url = dados.get('url')
            if status not in ('stream', 'redirect') or not download_url:
                print(f'[cobalt] status inválido: {status}')
                continue
            ext = '.mp3' if fmt == 'mp3' else '.opus'
            destino = os.path.join(pasta, f'audio{ext}')
            with requests.get(download_url, stream=True, timeout=180) as dl:
                dl.raise_for_status()
                with open(destino, 'wb') as f:
                    shutil.copyfileobj(dl.raw, f)
            tamanho = os.path.getsize(destino)
            print(f'[cobalt] arquivo baixado: {tamanho} bytes')
            if tamanho > 1000:
                return destino
        except Exception as e:
            print(f'[cobalt] erro formato={fmt}: {e}')
            continue
    return None


# ── MÉTODO 4: yt-dlp áudio + Groq ────────────────────────────────────────────

def baixar_via_ytdlp(url, pasta):
    print('[ytdlp-audio] tentando download de áudio')
    cookies = _cookies_path()
    opcoes = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(pasta, 'audio.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
    }
    if cookies:
        opcoes['cookiefile'] = cookies
        print(f'[ytdlp-audio] usando cookies: {cookies}')
    else:
        print('[ytdlp-audio] sem cookies')

    try:
        with yt_dlp.YoutubeDL(opcoes) as ydl:
            ydl.download([url])
        arquivos = glob.glob(os.path.join(pasta, 'audio.*'))
        print(f'[ytdlp-audio] arquivos: {arquivos}')
        return arquivos[0] if arquivos else None
    except Exception as e:
        print(f'[ytdlp-audio] erro: {e}')
        return None


def transcrever_audio_groq(arquivo_audio, idioma):
    print(f'[groq] transcrevendo {arquivo_audio}')
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
        return obj.get(chave, padrao) if isinstance(obj, dict) else getattr(obj, chave, padrao)

    segments_raw   = pegar(resposta, 'segments') or []
    texto_completo = pegar(resposta, 'text') or ''

    if segments_raw:
        return [
            {'inicio': round(float(pegar(seg, 'start') or 0), 1), 'texto': (pegar(seg, 'text') or '').strip()}
            for seg in segments_raw if (pegar(seg, 'text') or '').strip()
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

    video_id = extrair_video_id(url)
    if not video_id:
        return jsonify({'erro': 'Link do YouTube inválido.'}), 400

    print(f'\n=== Nova transcrição: {video_id} idioma={idioma} ===')

    try:
        # MÉTODO 1: youtube-transcript-api
        segmentos = obter_legendas_api(video_id, idioma)
        if segmentos:
            return jsonify({'sucesso': True, 'segmentos': segmentos, 'total': len(segmentos), 'fonte': 'legendas'})

        # MÉTODO 2: yt-dlp legendas com cookies
        segmentos = obter_legendas_ytdlp(video_id, idioma)
        if segmentos:
            return jsonify({'sucesso': True, 'segmentos': segmentos, 'total': len(segmentos), 'fonte': 'legendas'})

        if not GROQ_API_KEY:
            return jsonify({'erro': 'Vídeo sem legendas e chave Groq não configurada.'}), 500

        # MÉTODO 3: cobalt.tools + Groq
        with tempfile.TemporaryDirectory() as pasta_temp:
            arquivo_audio = baixar_via_cobalt(url, pasta_temp)

            # MÉTODO 4: yt-dlp áudio + Groq
            if not arquivo_audio:
                arquivo_audio = baixar_via_ytdlp(url, pasta_temp)

            if not arquivo_audio:
                print('[transcrever] todos os métodos falharam')
                return jsonify({'erro': 'Não foi possível obter a transcrição deste vídeo. Tente outro vídeo público.'}), 500

            segmentos = transcrever_audio_groq(arquivo_audio, idioma)
            if not segmentos:
                return jsonify({'erro': 'Não foi possível transcrever o áudio.'}), 500

            return jsonify({'sucesso': True, 'segmentos': segmentos, 'total': len(segmentos), 'fonte': 'audio_ia'})

    except Exception as e:
        print(f'[transcrever] exceção: {e}')
        return jsonify({'erro': str(e)}), 500


if __name__ == '__main__':
    print('\n  TranscreveAí — Servidor rodando!')
    print('  Acesse: http://localhost:8080\n')
    porta = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=porta, debug=False)
