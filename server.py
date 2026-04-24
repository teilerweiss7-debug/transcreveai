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
    """Copia cookies para arquivo temporário gravável (yt-dlp tenta escrever de volta nos cookies)."""
    conteudo = ''
    secret = '/etc/secrets/youtube_cookies.txt'
    if os.path.exists(secret):
        with open(secret, 'r', encoding='utf-8') as f:
            conteudo = f.read()
    if not conteudo:
        conteudo = os.environ.get('YOUTUBE_COOKIES', '')
    if not conteudo:
        return None
    tc = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
    tc.write(conteudo)
    tc.close()
    return tc.name


class _YDLLogger:
    """Captura logs do yt-dlp e imprime com prefixo."""
    def __init__(self, prefix):
        self.prefix = prefix
    def debug(self, msg):
        if msg.startswith('[debug]'):
            return
        print(f'[{self.prefix}] {msg}')
    def info(self, msg):
        print(f'[{self.prefix}] {msg}')
    def warning(self, msg):
        print(f'[{self.prefix}] AVISO: {msg}')
    def error(self, msg):
        print(f'[{self.prefix}] ERRO: {msg}')


# ── MÉTODO 1: youtube-transcript-api ─────────────────────────────────────────

def obter_legendas_api(video_id, idioma):
    print(f'[legendas-api] iniciando para {video_id}')
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        for lang in [idioma, 'pt', 'pt-BR', 'en']:
            try:
                t = transcript_list.find_transcript([lang])
                dados = t.fetch()
                resultado = _parsear_transcript(dados)
                if resultado:
                    print(f'[legendas-api] OK: {len(resultado)} segmentos (lang={lang})')
                    return resultado
            except Exception as e:
                print(f'[legendas-api] lang={lang} falhou: {e}')
        for t in transcript_list:
            try:
                dados = t.fetch()
                resultado = _parsear_transcript(dados)
                if resultado:
                    print(f'[legendas-api] OK: {len(resultado)} segmentos (qualquer idioma)')
                    return resultado
            except Exception as e:
                print(f'[legendas-api] idioma genérico falhou: {e}')
    except (TranscriptsDisabled, NoTranscriptFound) as e:
        print(f'[legendas-api] legendas desativadas/não encontradas: {e}')
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


# ── MÉTODO 2: yt-dlp só legendas (usa cookies) ───────────────────────────────

def obter_legendas_ytdlp(video_id, idioma):
    print(f'[legendas-ytdlp] iniciando para {video_id}')
    url = f'https://www.youtube.com/watch?v={video_id}'
    cookies = _cookies_path()

    try:
        with tempfile.TemporaryDirectory() as pasta:
            opcoes = {
                'skip_download': True,
                'writeautomaticsub': True,
                'writesubtitles': True,
                'subtitleslangs': [idioma, 'pt', 'en', 'pt-BR'],
                'subtitlesformat': 'json3',
                'outtmpl': os.path.join(pasta, 'sub'),
                'logger': _YDLLogger('ytdlp-sub'),
                'quiet': False,
                'no_warnings': False,
            }
            if cookies:
                opcoes['cookiefile'] = cookies
                print(f'[legendas-ytdlp] usando cookies: {cookies}')
            else:
                print('[legendas-ytdlp] sem cookies')

            try:
                with yt_dlp.YoutubeDL(opcoes) as ydl:
                    ydl.download([url])
            except Exception as e:
                print(f'[legendas-ytdlp] exceção no download: {e}')

            # Tenta ler os arquivos mesmo se houve exceção no cleanup do yt-dlp
            arquivos = glob.glob(os.path.join(pasta, '*.json3'))
            print(f'[legendas-ytdlp] arquivos encontrados: {arquivos}')
            if arquivos:
                resultado = _parsear_json3(arquivos[0])
                if resultado:
                    print(f'[legendas-ytdlp] OK: {len(resultado)} segmentos')
                    return resultado
                else:
                    print('[legendas-ytdlp] arquivo json3 vazio ou inválido')
            else:
                print('[legendas-ytdlp] nenhum arquivo json3 gerado')
    finally:
        if cookies and os.path.exists(cookies):
            os.unlink(cookies)

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
        print(f'[json3] erro: {e}')
        return None


# ── MÉTODO 3: Piped API + Groq (proxy intermediário, IP diferente do Render) ──

PIPED_INSTANCIAS = [
    'https://pipedapi.kavin.rocks',
    'https://piped-api.garudalinux.org',
    'https://api.piped.projectsegfau.lt',
    'https://api.piped.yt',
]

def baixar_via_piped(video_id, pasta):
    print(f'[piped] iniciando para {video_id}')
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    for instancia in PIPED_INSTANCIAS:
        try:
            r = requests.get(f'{instancia}/streams/{video_id}', timeout=15, headers=headers)
            print(f'[piped] {instancia}: HTTP {r.status_code}')
            if r.status_code != 200:
                continue

            dados = r.json()
            streams = dados.get('audioStreams', [])
            if not streams:
                print(f'[piped] {instancia}: sem audioStreams')
                continue

            melhor = sorted(streams, key=lambda x: x.get('bitrate', 0), reverse=True)[0]
            audio_url = melhor.get('url', '')
            mime = melhor.get('mimeType', '')
            print(f'[piped] URL obtida mime={mime}, baixando...')

            if not audio_url:
                continue

            ext = '.webm' if 'webm' in mime else '.m4a'
            destino = os.path.join(pasta, f'audio{ext}')

            with requests.get(audio_url, stream=True, timeout=300, headers=headers) as dl:
                dl.raise_for_status()
                with open(destino, 'wb') as f:
                    shutil.copyfileobj(dl.raw, f)

            tamanho = os.path.getsize(destino) if os.path.exists(destino) else 0
            print(f'[piped] tamanho={tamanho} bytes')
            if tamanho > 1000:
                return destino

        except Exception as e:
            print(f'[piped] {instancia} falhou: {e}')

    return None


# ── MÉTODO 4: yt-dlp áudio + Groq ────────────────────────────────────────────

def baixar_via_ytdlp(url, pasta):
    print('[ytdlp-audio] iniciando download')
    cookies = _cookies_path()
    opcoes = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(pasta, 'audio.%(ext)s'),
        'logger': _YDLLogger('ytdlp-audio'),
        'quiet': False,
        'no_warnings': False,
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
        print(f'[ytdlp-audio] exceção: {e}')
        return None


def transcrever_audio_groq(arquivo_audio, idioma):
    tamanho = os.path.getsize(arquivo_audio)
    extensao = os.path.splitext(arquivo_audio)[1]
    print(f'[groq] iniciando: arquivo={arquivo_audio} ext={extensao} tamanho={tamanho} bytes idioma={idioma}')

    cliente = Groq(api_key=GROQ_API_KEY)

    with open(arquivo_audio, 'rb') as f:
        resposta = cliente.audio.transcriptions.create(
            file=(f'audio{extensao}', f),
            model='whisper-large-v3',
            language=idioma,
            response_format='verbose_json',
            timestamp_granularities=['segment'],
        )

    print(f'[groq] resposta recebida, tipo={type(resposta).__name__}')

    def pegar(obj, chave, padrao=None):
        return obj.get(chave, padrao) if isinstance(obj, dict) else getattr(obj, chave, padrao)

    segments_raw   = pegar(resposta, 'segments') or []
    texto_completo = pegar(resposta, 'text') or ''

    print(f'[groq] segments={len(segments_raw)} texto_len={len(texto_completo)}')

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

    print(f'\n=== Transcrição: {video_id} idioma={idioma} ===')

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

        # MÉTODOS 3, 4 e 5: áudio + Groq
        with tempfile.TemporaryDirectory() as pasta_temp:
            # Piped: proxy intermediário com IP diferente do Render
            arquivo_audio = baixar_via_piped(video_id, pasta_temp)

            # pytubefix: API Android como fallback
            if not arquivo_audio:
                arquivo_audio = baixar_via_pytubefix(url, pasta_temp)

            # yt-dlp com cookies como último recurso
            if not arquivo_audio:
                arquivo_audio = baixar_via_ytdlp(url, pasta_temp)

            if not arquivo_audio:
                print('=== Todos os métodos falharam ===')
                return jsonify({'erro': 'Não foi possível obter a transcrição. Tente um vídeo público diferente.'}), 500

            segmentos = transcrever_audio_groq(arquivo_audio, idioma)
            if not segmentos:
                return jsonify({'erro': 'Não foi possível transcrever o áudio.'}), 500

            return jsonify({'sucesso': True, 'segmentos': segmentos, 'total': len(segmentos), 'fonte': 'audio_ia'})

    except Exception as e:
        print(f'[transcrever] exceção não tratada: {e}')
        return jsonify({'erro': str(e)}), 500


if __name__ == '__main__':
    print('\n  TranscreveAí — Servidor rodando!')
    print('  Acesse: http://localhost:8080\n')
    porta = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=porta, debug=False)
