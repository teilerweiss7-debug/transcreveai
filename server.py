"""
Transcreve IA — Plataforma de Aprendizado
"""

import os, re, glob, json, shutil, tempfile, sqlite3, secrets
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from groq import Groq
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import requests

app = Flask(__name__)
CORS(app, supports_credentials=True)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
DB_PATH = os.environ.get('DB_PATH', '/tmp/transcrevai.db')


# ── DATABASE ──────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                nome TEXT NOT NULL,
                senha_hash TEXT NOT NULL,
                plaud_token TEXT UNIQUE,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS transcricoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                titulo TEXT NOT NULL,
                fonte TEXT NOT NULL,
                segmentos TEXT NOT NULL,
                video_url TEXT,
                filename TEXT,
                plaud_id TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(user_id) REFERENCES usuarios(id)
            );
            CREATE TABLE IF NOT EXISTS chat (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transcricao_id INTEGER NOT NULL,
                papel TEXT NOT NULL,
                conteudo TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(transcricao_id) REFERENCES transcricoes(id)
            );
        ''')


init_db()


# ── AUTH ──────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def dec(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'erro': 'Não autenticado.'}), 401
        return f(*args, **kwargs)
    return dec


@app.route('/api/auth/cadastrar', methods=['POST'])
def cadastrar():
    d = request.get_json()
    email = d.get('email', '').strip().lower()
    nome  = d.get('nome', '').strip()
    senha = d.get('senha', '')

    if not email or not nome or not senha:
        return jsonify({'erro': 'Preencha todos os campos.'}), 400
    if len(senha) < 6:
        return jsonify({'erro': 'Senha deve ter pelo menos 6 caracteres.'}), 400

    try:
        with get_db() as db:
            token = secrets.token_urlsafe(32)
            db.execute(
                'INSERT INTO usuarios (email, nome, senha_hash, plaud_token) VALUES (?, ?, ?, ?)',
                (email, nome, generate_password_hash(senha), token)
            )
            user = db.execute('SELECT * FROM usuarios WHERE email = ?', (email,)).fetchone()
        session['user_id'] = user['id']
        session['nome'] = user['nome']
        return jsonify({'sucesso': True, 'nome': user['nome']})
    except sqlite3.IntegrityError:
        return jsonify({'erro': 'Este e-mail já está cadastrado.'}), 400


@app.route('/api/auth/entrar', methods=['POST'])
def entrar():
    d = request.get_json()
    email = d.get('email', '').strip().lower()
    senha = d.get('senha', '')

    if not email or not senha:
        return jsonify({'erro': 'Preencha todos os campos.'}), 400

    with get_db() as db:
        user = db.execute('SELECT * FROM usuarios WHERE email = ?', (email,)).fetchone()

    if not user or not check_password_hash(user['senha_hash'], senha):
        return jsonify({'erro': 'E-mail ou senha incorretos.'}), 401

    session['user_id'] = user['id']
    session['nome'] = user['nome']
    return jsonify({'sucesso': True, 'nome': user['nome']})


@app.route('/api/auth/sair', methods=['POST'])
def sair():
    session.clear()
    return jsonify({'sucesso': True})


@app.route('/api/auth/eu', methods=['GET'])
def eu():
    if 'user_id' not in session:
        return jsonify({'autenticado': False})
    with get_db() as db:
        user = db.execute('SELECT * FROM usuarios WHERE id = ?', (session['user_id'],)).fetchone()
    if not user:
        return jsonify({'autenticado': False})
    base = request.host_url.rstrip('/')
    return jsonify({
        'autenticado': True,
        'nome': user['nome'],
        'email': user['email'],
        'plaud_webhook_url': f"{base}/api/plaud/webhook/{user['plaud_token']}"
    })


# ── TRANSCRIÇÕES ──────────────────────────────────────────────────────────────

@app.route('/api/transcricoes', methods=['GET'])
@login_required
def listar():
    with get_db() as db:
        rows = db.execute(
            'SELECT id, titulo, fonte, video_url, filename, created_at FROM transcricoes WHERE user_id = ? ORDER BY created_at DESC',
            (session['user_id'],)
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/transcricoes/<int:tid>', methods=['GET'])
@login_required
def obter(tid):
    with get_db() as db:
        t = db.execute(
            'SELECT * FROM transcricoes WHERE id = ? AND user_id = ?',
            (tid, session['user_id'])
        ).fetchone()
    if not t:
        return jsonify({'erro': 'Não encontrada.'}), 404
    return jsonify(dict(t))


@app.route('/api/transcricoes/<int:tid>', methods=['DELETE'])
@login_required
def deletar(tid):
    with get_db() as db:
        db.execute('DELETE FROM chat WHERE transcricao_id = ?', (tid,))
        db.execute('DELETE FROM transcricoes WHERE id = ? AND user_id = ?', (tid, session['user_id']))
    return jsonify({'sucesso': True})


# ── CHAT COM IA ───────────────────────────────────────────────────────────────

@app.route('/api/transcricoes/<int:tid>/chat', methods=['GET'])
@login_required
def chat_get(tid):
    with get_db() as db:
        ok = db.execute('SELECT id FROM transcricoes WHERE id = ? AND user_id = ?', (tid, session['user_id'])).fetchone()
        if not ok:
            return jsonify({'erro': 'Não encontrada.'}), 404
        msgs = db.execute('SELECT papel, conteudo, created_at FROM chat WHERE transcricao_id = ? ORDER BY id', (tid,)).fetchall()
    return jsonify([dict(m) for m in msgs])


@app.route('/api/transcricoes/<int:tid>/chat', methods=['POST'])
@login_required
def chat_post(tid):
    if not GROQ_API_KEY:
        return jsonify({'erro': 'Chave Groq não configurada.'}), 500

    d = request.get_json()
    pergunta = d.get('mensagem', '').strip()
    if not pergunta:
        return jsonify({'erro': 'Mensagem vazia.'}), 400

    with get_db() as db:
        t = db.execute('SELECT * FROM transcricoes WHERE id = ? AND user_id = ?', (tid, session['user_id'])).fetchone()
        if not t:
            return jsonify({'erro': 'Não encontrada.'}), 404
        historico = db.execute('SELECT papel, conteudo FROM chat WHERE transcricao_id = ? ORDER BY id', (tid,)).fetchall()

    segmentos = json.loads(t['segmentos'])
    texto = ' '.join(s['texto'] for s in segmentos)[:8000]

    sistema = f"""Você é um assistente que ajuda o usuário a entender o conteúdo de uma transcrição chamada "{t['titulo']}".

TRANSCRIÇÃO:
{texto}

Responda em português, de forma clara e objetiva. Se a pergunta não está no conteúdo, responda normalmente."""

    msgs = [{'role': 'system', 'content': sistema}]
    for m in historico:
        msgs.append({'role': m['papel'], 'content': m['conteudo']})
    msgs.append({'role': 'user', 'content': pergunta})

    cliente = Groq(api_key=GROQ_API_KEY)
    resp = cliente.chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=msgs,
        max_tokens=1000,
    )
    resposta = resp.choices[0].message.content

    with get_db() as db:
        db.execute('INSERT INTO chat (transcricao_id, papel, conteudo) VALUES (?, ?, ?)', (tid, 'user', pergunta))
        db.execute('INSERT INTO chat (transcricao_id, papel, conteudo) VALUES (?, ?, ?)', (tid, 'assistant', resposta))

    return jsonify({'resposta': resposta})


# ── TRANSCREVER YOUTUBE ───────────────────────────────────────────────────────

@app.route('/api/transcrever/youtube', methods=['POST'])
@login_required
def transcrever_youtube():
    d = request.get_json()
    url    = d.get('url', '').strip()
    idioma = d.get('idioma', 'pt')

    if not url:
        return jsonify({'erro': 'Nenhum link enviado.'}), 400
    video_id = extrair_video_id(url)
    if not video_id:
        return jsonify({'erro': 'Link do YouTube inválido.'}), 400

    titulo = _titulo_youtube(video_id) or f'Vídeo {video_id}'
    print(f'\n=== YouTube: {video_id} idioma={idioma} ===')

    try:
        segmentos = obter_legendas_api(video_id, idioma)
        fonte = 'youtube_legendas'

        if not segmentos:
            segmentos = obter_legendas_ytdlp(video_id, idioma)

        if not segmentos:
            if not GROQ_API_KEY:
                return jsonify({'erro': 'Vídeo sem legendas e chave Groq não configurada.'}), 500
            with tempfile.TemporaryDirectory() as pasta:
                arq = (baixar_via_piped(video_id, pasta)
                       or baixar_via_invidious(video_id, pasta)
                       or baixar_via_ytdlp(url, pasta))
                if not arq:
                    return jsonify({'erro': 'Não foi possível obter o áudio deste vídeo.'}), 500
                segmentos = transcrever_audio_groq(arq, idioma)
                fonte = 'youtube_ia'

        if not segmentos:
            return jsonify({'erro': 'Não foi possível transcrever este vídeo.'}), 500

        with get_db() as db:
            cur = db.execute(
                'INSERT INTO transcricoes (user_id, titulo, fonte, segmentos, video_url) VALUES (?, ?, ?, ?, ?)',
                (session['user_id'], titulo, fonte, json.dumps(segmentos), url)
            )
            tid = cur.lastrowid

        return jsonify({'sucesso': True, 'id': tid, 'titulo': titulo, 'segmentos': segmentos, 'total': len(segmentos), 'fonte': fonte})

    except Exception as e:
        print(f'[youtube] exceção: {e}')
        return jsonify({'erro': str(e)}), 500


def _titulo_youtube(video_id):
    try:
        r = requests.get(
            f'https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json',
            timeout=5
        )
        if r.status_code == 200:
            return r.json().get('title', '')
    except Exception:
        pass
    return None


# ── TRANSCREVER ARQUIVO ───────────────────────────────────────────────────────

EXTS_OK = {'.mp3', '.mp4', '.m4a', '.wav', '.ogg', '.webm', '.mov', '.mkv', '.flac', '.aac', '.opus'}
MAX_BYTES = 25 * 1024 * 1024


@app.route('/api/transcrever/arquivo', methods=['POST'])
@login_required
def transcrever_arquivo():
    if not GROQ_API_KEY:
        return jsonify({'erro': 'Chave Groq não configurada.'}), 500

    arq    = request.files.get('arquivo')
    idioma = request.form.get('idioma', 'pt')
    fonte  = request.form.get('fonte', 'arquivo')  # 'arquivo' ou 'plaud'

    if not arq:
        return jsonify({'erro': 'Nenhum arquivo enviado.'}), 400

    nome = arq.filename or 'audio.m4a'
    ext  = os.path.splitext(nome)[1].lower()

    if ext not in EXTS_OK:
        return jsonify({'erro': f'Formato não suportado. Use: MP3, MP4, M4A, WAV, OGG, WEBM, AAC...'}), 400

    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    arq.save(tmp.name)
    tmp.close()

    try:
        if os.path.getsize(tmp.name) > MAX_BYTES:
            return jsonify({'erro': 'Arquivo muito grande. Limite: 25 MB.'}), 400

        print(f'[arquivo] {nome} fonte={fonte}')
        segmentos = transcrever_audio_groq(tmp.name, idioma)

        if not segmentos:
            return jsonify({'erro': 'Não foi possível transcrever o arquivo.'}), 500

        titulo = os.path.splitext(nome)[0]

        with get_db() as db:
            cur = db.execute(
                'INSERT INTO transcricoes (user_id, titulo, fonte, segmentos, filename) VALUES (?, ?, ?, ?, ?)',
                (session['user_id'], titulo, fonte, json.dumps(segmentos), nome)
            )
            tid = cur.lastrowid

        return jsonify({'sucesso': True, 'id': tid, 'titulo': titulo, 'segmentos': segmentos, 'total': len(segmentos)})

    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)


# ── PLAUD WEBHOOK (automático) ────────────────────────────────────────────────

@app.route('/api/plaud/webhook/<token>', methods=['POST'])
def plaud_webhook(token):
    """Recebe gravação do Plaud automaticamente via webhook."""
    with get_db() as db:
        user = db.execute('SELECT * FROM usuarios WHERE plaud_token = ?', (token,)).fetchone()
    if not user:
        return jsonify({'erro': 'Token inválido.'}), 401

    arq      = request.files.get('audio') or request.files.get('file')
    plaud_id = request.form.get('recording_id', '')
    titulo   = request.form.get('title', 'Gravação Plaud')
    idioma   = request.form.get('language', 'pt')

    if not arq:
        # Tenta JSON com URL de áudio
        dados = request.get_json(silent=True) or {}
        audio_url = dados.get('audio_url', '')
        if audio_url:
            try:
                r = requests.get(audio_url, timeout=120)
                r.raise_for_status()
                tmp = tempfile.NamedTemporaryFile(suffix='.m4a', delete=False)
                tmp.write(r.content)
                tmp.close()
                segmentos = transcrever_audio_groq(tmp.name, idioma)
                os.unlink(tmp.name)
                titulo = dados.get('title', titulo)
                plaud_id = dados.get('recording_id', plaud_id)
            except Exception as e:
                return jsonify({'erro': f'Erro ao baixar áudio: {e}'}), 500
        else:
            return jsonify({'erro': 'Nenhum arquivo de áudio recebido.'}), 400
    else:
        nome = arq.filename or 'plaud.m4a'
        ext  = os.path.splitext(nome)[1].lower() or '.m4a'
        tmp  = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        arq.save(tmp.name)
        tmp.close()
        try:
            segmentos = transcrever_audio_groq(tmp.name, idioma)
        finally:
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)

    if not segmentos:
        return jsonify({'erro': 'Falha na transcrição.'}), 500

    with get_db() as db:
        db.execute(
            'INSERT INTO transcricoes (user_id, titulo, fonte, segmentos, plaud_id) VALUES (?, ?, ?, ?, ?)',
            (user['id'], titulo, 'plaud', json.dumps(segmentos), plaud_id)
        )
    print(f'[plaud-webhook] nova gravação para user {user["id"]}: {titulo}')
    return jsonify({'sucesso': True})


# ── YOUTUBE HELPER FUNCTIONS ──────────────────────────────────────────────────

def extrair_video_id(url):
    match = re.search(r'(?:v=|youtu\.be/|embed/)([a-zA-Z0-9_-]{11})', url)
    return match.group(1) if match else None


def _cookies_path():
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
    def __init__(self, p):
        self.p = p
    def debug(self, msg):
        if not msg.startswith('[debug]'):
            print(f'[{self.p}] {msg}')
    def info(self, msg): print(f'[{self.p}] {msg}')
    def warning(self, msg): print(f'[{self.p}] AVISO: {msg}')
    def error(self, msg): print(f'[{self.p}] ERRO: {msg}')


def obter_legendas_api(video_id, idioma):
    print(f'[legendas-api] {video_id}')
    try:
        tl = YouTubeTranscriptApi.list_transcripts(video_id)
        for lang in [idioma, 'pt', 'pt-BR', 'en']:
            try:
                dados = tl.find_transcript([lang]).fetch()
                res = _parsear_transcript(dados)
                if res:
                    print(f'[legendas-api] OK {len(res)} seg lang={lang}')
                    return res
            except Exception:
                pass
        for t in tl:
            try:
                res = _parsear_transcript(t.fetch())
                if res:
                    return res
            except Exception:
                pass
    except (TranscriptsDisabled, NoTranscriptFound) as e:
        print(f'[legendas-api] {e}')
    except Exception as e:
        print(f'[legendas-api] erro: {e}')
    return None


def _parsear_transcript(dados):
    segs = []
    for s in dados:
        texto  = (s.get('text', '') if isinstance(s, dict) else getattr(s, 'text', '')).replace('\n', ' ').strip()
        inicio = s.get('start', 0) if isinstance(s, dict) else getattr(s, 'start', 0)
        if texto:
            segs.append({'inicio': round(float(inicio), 1), 'texto': texto})
    return segs if segs else None


def obter_legendas_ytdlp(video_id, idioma):
    print(f'[legendas-ytdlp] {video_id}')
    url = f'https://www.youtube.com/watch?v={video_id}'
    cookies = _cookies_path()
    try:
        with tempfile.TemporaryDirectory() as pasta:
            opts = {
                'skip_download': True, 'writeautomaticsub': True, 'writesubtitles': True,
                'subtitleslangs': [idioma, 'pt', 'en', 'pt-BR'], 'subtitlesformat': 'json3',
                'outtmpl': os.path.join(pasta, 'sub'), 'logger': _YDLLogger('ytdlp-sub'),
                'quiet': False,
            }
            if cookies:
                opts['cookiefile'] = cookies
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
            except Exception as e:
                print(f'[legendas-ytdlp] exceção: {e}')
            arquivos = glob.glob(os.path.join(pasta, '*.json3'))
            if arquivos:
                res = _parsear_json3(arquivos[0])
                if res:
                    print(f'[legendas-ytdlp] OK {len(res)} seg')
                    return res
    finally:
        if cookies and os.path.exists(cookies):
            os.unlink(cookies)
    return None


def _parsear_json3(caminho):
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        segs = []
        for ev in dados.get('events', []):
            inicio = ev.get('tStartMs', 0) / 1000
            texto  = ''.join(s.get('utf8', '') for s in ev.get('segs', [])).replace('\n', ' ').strip()
            if texto:
                segs.append({'inicio': round(float(inicio), 1), 'texto': texto})
        return segs if segs else None
    except Exception as e:
        print(f'[json3] {e}')
        return None


PIPED_INSTANCIAS = [
    'https://piapi.adminforge.de',
    'https://pipedapi.privacydev.net',
    'https://pipedapi.tokhmi.xyz',
    'https://pipedapi.kavin.rocks',
]

INVIDIOUS_INSTANCIAS = [
    'https://invidious.io',
    'https://yewtu.be',
    'https://inv.vern.cc',
    'https://invidious.privacyredirect.com',
]


def baixar_via_piped(video_id, pasta):
    print(f'[piped] {video_id}')
    h = {'User-Agent': 'Mozilla/5.0'}
    for inst in PIPED_INSTANCIAS:
        try:
            r = requests.get(f'{inst}/streams/{video_id}', timeout=15, headers=h)
            if r.status_code != 200:
                continue
            streams = r.json().get('audioStreams', [])
            if not streams:
                continue
            melhor = sorted(streams, key=lambda x: x.get('bitrate', 0), reverse=True)[0]
            url = melhor.get('url', '')
            if not url:
                continue
            mime = melhor.get('mimeType', '')
            ext  = '.webm' if 'webm' in mime else '.m4a'
            dest = os.path.join(pasta, f'audio{ext}')
            with requests.get(url, stream=True, timeout=300, headers=h) as dl:
                dl.raise_for_status()
                with open(dest, 'wb') as f:
                    shutil.copyfileobj(dl.raw, f)
            if os.path.getsize(dest) > 1000:
                return dest
        except Exception as e:
            print(f'[piped] {inst}: {e}')
    return None


def baixar_via_invidious(video_id, pasta):
    print(f'[invidious] {video_id}')
    h = {'User-Agent': 'Mozilla/5.0'}
    for inst in INVIDIOUS_INSTANCIAS:
        try:
            r = requests.get(f'{inst}/api/v1/videos/{video_id}', timeout=15, headers=h)
            if r.status_code != 200:
                continue
            audios = [f for f in r.json().get('adaptiveFormats', []) if 'audio' in f.get('type', '')]
            if not audios:
                continue
            melhor = sorted(audios, key=lambda x: x.get('bitrate', 0), reverse=True)[0]
            url  = melhor.get('url', '')
            tipo = melhor.get('type', '')
            if not url:
                continue
            ext  = '.webm' if 'webm' in tipo else '.m4a'
            dest = os.path.join(pasta, f'audio{ext}')
            with requests.get(url, stream=True, timeout=300, headers=h) as dl:
                dl.raise_for_status()
                with open(dest, 'wb') as f:
                    shutil.copyfileobj(dl.raw, f)
            if os.path.getsize(dest) > 1000:
                return dest
        except Exception as e:
            print(f'[invidious] {inst}: {e}')
    return None


def baixar_via_ytdlp(url, pasta):
    print('[ytdlp-audio] iniciando')
    cookies = _cookies_path()
    opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(pasta, 'audio.%(ext)s'),
        'logger': _YDLLogger('ytdlp-audio'),
        'quiet': False,
    }
    if cookies:
        opts['cookiefile'] = cookies
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        arquivos = glob.glob(os.path.join(pasta, 'audio.*'))
        return arquivos[0] if arquivos else None
    except Exception as e:
        print(f'[ytdlp-audio] {e}')
        return None
    finally:
        if cookies and os.path.exists(cookies):
            os.unlink(cookies)


def transcrever_audio_groq(arq, idioma):
    tamanho = os.path.getsize(arq)
    ext     = os.path.splitext(arq)[1]
    print(f'[groq] {arq} ext={ext} {tamanho} bytes')

    cliente = Groq(api_key=GROQ_API_KEY)
    with open(arq, 'rb') as f:
        resp = cliente.audio.transcriptions.create(
            file=(f'audio{ext}', f),
            model='whisper-large-v3',
            language=idioma,
            response_format='verbose_json',
            timestamp_granularities=['segment'],
        )

    def pegar(obj, k, pad=None):
        return obj.get(k, pad) if isinstance(obj, dict) else getattr(obj, k, pad)

    segs_raw = pegar(resp, 'segments') or []
    texto    = pegar(resp, 'text') or ''

    if segs_raw:
        return [
            {'inicio': round(float(pegar(s, 'start') or 0), 1), 'texto': (pegar(s, 'text') or '').strip()}
            for s in segs_raw if (pegar(s, 'text') or '').strip()
        ]
    elif texto:
        return [{'inicio': 0, 'texto': texto.strip()}]
    return None


# ── ROTAS ESTÁTICAS ───────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/api/status', methods=['GET'])
def status():
    return jsonify({'online': True, 'groq_configurado': bool(GROQ_API_KEY)})


if __name__ == '__main__':
    print('\n  Transcreve IA — Servidor rodando!')
    print('  Acesse: http://localhost:8080\n')
    porta = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=porta, debug=False)
