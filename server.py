"""
TranscreveAí — Servidor Backend
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
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

app = Flask(__name__)
CORS(app)

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')


def extrair_video_id(url):
    match = re.search(r'(?:v=|youtu\.be/|embed/)([a-zA-Z0-9_-]{11})', url)
    return match.group(1) if match else None


# ── MÉTODO 1: Legendas do YouTube via youtube-transcript-api ─────────────────

def obter_legendas(video_id, idioma):
    """Busca legendas usando youtube-transcript-api. Retorna lista de segmentos ou None."""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # Ordem de preferência de idiomas
        for lang in [idioma, 'pt', 'pt-BR', 'en']:
            try:
                t = transcript_list.find_transcript([lang])
                dados = t.fetch()
                return _parsear_transcript(dados)
            except Exception:
                continue

        # Nenhum idioma preferido encontrado — pega qualquer disponível
        for t in transcript_list:
            try:
                dados = t.fetch()
                resultado = _parsear_transcript(dados)
                if resultado:
                    return resultado
            except Exception:
                continue

    except (TranscriptsDisabled, NoTranscriptFound):
        pass
    except Exception:
        pass

    return None


def _parsear_transcript(dados):
    """Converte o resultado do youtube-transcript-api em lista de segmentos."""
    segmentos = []
    for s in dados:
        # Compatível com dicionário (versões antigas) e objeto (versões novas)
        if isinstance(s, dict):
            texto = s.get('text', '')
            inicio = s.get('start', 0)
        else:
            texto = getattr(s, 'text', '')
            inicio = getattr(s, 'start', 0)

        texto = texto.replace('\n', ' ').strip()
        if texto:
            segmentos.append({'inicio': round(float(inicio), 1), 'texto': texto})

    return segmentos if segmentos else None


# ── MÉTODO 2: Download de áudio via cobalt.tools + Groq ──────────────────────

def baixar_via_cobalt(url, pasta):
    """Baixa áudio via cobalt.tools."""
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
            if r.status_code != 200:
                continue

            dados = r.json()
            status = dados.get('status')
            download_url = dados.get('url')

            if status not in ('stream', 'redirect') or not download_url:
                continue

            ext = '.mp3' if fmt == 'mp3' else '.opus'
            destino = os.path.join(pasta, f'audio{ext}')

            with requests.get(download_url, stream=True, timeout=180) as dl:
                dl.raise_for_status()
                with open(destino, 'wb') as f:
                    shutil.copyfileobj(dl.raw, f)

            if os.path.getsize(destino) > 1000:
                return destino

        except Exception:
            continue

    return None


def baixar_via_ytdlp(url, pasta):
    """Baixa áudio via yt-dlp (fallback)."""
    opcoes = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(pasta, 'audio.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
    }

    cookies_path = '/etc/secrets/youtube_cookies.txt'
    temp_cookies = None

    if os.path.exists(cookies_path):
        opcoes['cookiefile'] = cookies_path
    elif os.environ.get('YOUTUBE_COOKIES'):
        tc = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        tc.write(os.environ['YOUTUBE_COOKIES'])
        tc.close()
        temp_cookies = tc.name
        opcoes['cookiefile'] = temp_cookies

    try:
        with yt_dlp.YoutubeDL(opcoes) as ydl:
            ydl.download([url])
        arquivos = glob.glob(os.path.join(pasta, 'audio.*'))
        return arquivos[0] if arquivos else None
    except Exception:
        return None
    finally:
        if temp_cookies and os.path.exists(temp_cookies):
            os.unlink(temp_cookies)


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
        return obj.get(chave, padrao) if isinstance(obj, dict) else getattr(obj, chave, padrao)

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

    video_id = extrair_video_id(url)
    if not video_id:
        return jsonify({'erro': 'Link do YouTube inválido.'}), 400

    try:
        # TENTATIVA 1: Legendas do YouTube (instantâneo, sem IA)
        segmentos = obter_legendas(video_id, idioma)
        if segmentos:
            return jsonify({
                'sucesso': True,
                'segmentos': segmentos,
                'total': len(segmentos),
                'fonte': 'legendas',
            })

        # Para a rota de áudio, precisa da chave Groq
        if not GROQ_API_KEY:
            return jsonify({
                'erro': 'Este vídeo não tem legendas disponíveis e a chave Groq não está configurada.'
            }), 500

        # TENTATIVA 2: cobalt.tools + Groq Whisper
        with tempfile.TemporaryDirectory() as pasta_temp:
            arquivo_audio = baixar_via_cobalt(url, pasta_temp)

            # TENTATIVA 3: yt-dlp como último recurso
            if not arquivo_audio:
                arquivo_audio = baixar_via_ytdlp(url, pasta_temp)

            if not arquivo_audio:
                return jsonify({
                    'erro': 'Este vídeo não tem legendas disponíveis. Tente um vídeo público diferente.'
                }), 500

            segmentos = transcrever_audio_groq(arquivo_audio, idioma)
            if not segmentos:
                return jsonify({'erro': 'Não foi possível transcrever o áudio.'}), 500

            return jsonify({
                'sucesso': True,
                'segmentos': segmentos,
                'total': len(segmentos),
                'fonte': 'audio_ia',
            })

    except Exception as e:
        return jsonify({'erro': str(e)}), 500


if __name__ == '__main__':
    print('\n  TranscreveAí — Servidor rodando!')
    print('  Acesse: http://localhost:8080')
    print('  Para parar: Ctrl+C\n')
    porta = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=porta, debug=False)
