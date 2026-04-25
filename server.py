"""
Transcreve IA — Plataforma de Aprendizado
"""

import os, re, glob, json, shutil, tempfile, secrets, subprocess
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from groq import Groq
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import requests

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # aceita até 500 MB

# Permite o frontend Vercel fazer requisições com cookies
_FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000')
CORS(app, supports_credentials=True, origins=[_FRONTEND_URL, 'http://localhost:3000'])
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE']   = True
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-fixo-local')

GROQ_API_KEY  = os.environ.get('GROQ_API_KEY', '')
DATABASE_URL  = os.environ.get('DATABASE_URL', '')  # PostgreSQL no Render
_USE_PG       = bool(DATABASE_URL)

if _USE_PG:
    import psycopg2
    import psycopg2.extras
    _IntegrityError = psycopg2.IntegrityError
else:
    import sqlite3
    _DB_PATH = os.environ.get('DB_PATH', '/tmp/transcrevai.db')
    _IntegrityError = sqlite3.IntegrityError


# ── DATABASE — wrapper compatível SQLite / PostgreSQL ─────────────────────────

class _Cur:
    """Cursor unificado para capturar lastrowid em ambos os bancos."""
    def __init__(self, cursor, pg=False):
        self._c = cursor
        self._pg = pg

    @property
    def lastrowid(self):
        if self._pg:
            row = self._c.fetchone()
            return row['id'] if row else None
        return self._c.lastrowid

    def fetchone(self):  return self._c.fetchone()
    def fetchall(self):  return self._c.fetchall()


class _DB:
    def __init__(self):
        if _USE_PG:
            self._conn = psycopg2.connect(DATABASE_URL,
                                          cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            self._conn = sqlite3.connect(_DB_PATH)
            self._conn.row_factory = sqlite3.Row

    def execute(self, sql, params=()):
        if _USE_PG:
            sql = sql.replace('?', '%s')
            if sql.strip().upper().startswith('INSERT'):
                sql = sql.rstrip().rstrip(';') + ' RETURNING id'
        cur = self._conn.cursor()
        cur.execute(sql, params)
        return _Cur(cur, pg=_USE_PG)

    def executescript(self, sql):
        if _USE_PG:
            sql = (sql
                   .replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
                   .replace("datetime('now')", 'NOW()')
                   .replace('TEXT DEFAULT (NOW())', "TEXT DEFAULT (NOW()::TEXT)"))
            cur = self._conn.cursor()
            for stmt in [s.strip() for s in sql.split(';') if s.strip()]:
                cur.execute(stmt)
        else:
            self._conn.executescript(sql)

    def __enter__(self): return self
    def __exit__(self, exc, *_):
        if exc is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self._conn.close()


def get_db():
    return _DB()


_SCHEMA = '''
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
'''


def init_db():
    with get_db() as db:
        db.executescript(_SCHEMA)


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
    except _IntegrityError:
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

EXTS_OK  = {'.mp3', '.mp4', '.m4a', '.wav', '.ogg', '.webm', '.mov', '.mkv', '.flac', '.aac', '.opus'}
MAX_GROQ = 24 * 1024 * 1024  # 24 MB — margem abaixo do limite de 25 MB do Groq


def _tem_ffmpeg():
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        return True
    except Exception:
        return False


def _preparar_chunks(arquivo, pasta):
    """Converte para MP3 mono 16kHz 32kbps e divide em partes se necessário.
    Retorna lista de (caminho_do_chunk, offset_em_segundos)."""

    audio_path = os.path.join(pasta, 'audio.mp3')

    # Converte/extrai áudio: mono, 16 kHz, 32 kbps — ideal para fala, tamanho mínimo
    cmd = ['ffmpeg', '-i', arquivo, '-vn', '-ar', '16000', '-ac', '1',
           '-b:a', '32k', audio_path, '-y']
    res = subprocess.run(cmd, capture_output=True, timeout=600)
    if res.returncode != 0 or not os.path.exists(audio_path):
        print(f'[ffmpeg] erro na conversão: {res.stderr.decode()[:300]}')
        return None

    tamanho = os.path.getsize(audio_path)
    print(f'[ffmpeg] áudio convertido: {tamanho} bytes')

    if tamanho <= MAX_GROQ:
        return [(audio_path, 0.0)]

    # Descobre duração total para calcular número de chunks
    probe = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', audio_path],
        capture_output=True, text=True, timeout=30
    )
    try:
        duracao_total = float(json.loads(probe.stdout)['format']['duration'])
    except Exception:
        duracao_total = 7200.0  # assume 2h se não conseguir detectar

    # Cada chunk de 20 minutos — a 32kbps mono, ~15 MB por chunk
    duracao_chunk = 1200
    chunks = []
    offset = 0.0
    i = 0
    while offset < duracao_total:
        chunk_path = os.path.join(pasta, f'chunk_{i:03d}.mp3')
        subprocess.run(
            ['ffmpeg', '-i', audio_path, '-ss', str(offset), '-t', str(duracao_chunk),
             '-c', 'copy', chunk_path, '-y'],
            capture_output=True, timeout=120
        )
        if os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 1000:
            chunks.append((chunk_path, offset))
            print(f'[ffmpeg] chunk {i}: offset={offset}s tamanho={os.path.getsize(chunk_path)} bytes')
        offset += duracao_chunk
        i += 1

    return chunks if chunks else None


@app.route('/api/transcrever/arquivo', methods=['POST'])
@login_required
def transcrever_arquivo():
    if not GROQ_API_KEY:
        return jsonify({'erro': 'Chave Groq não configurada.'}), 500

    arq    = request.files.get('arquivo')
    idioma = request.form.get('idioma', 'pt')
    fonte  = request.form.get('fonte', 'arquivo')

    if not arq:
        return jsonify({'erro': 'Nenhum arquivo enviado.'}), 400

    nome = arq.filename or 'audio.m4a'
    ext  = os.path.splitext(nome)[1].lower()

    if ext not in EXTS_OK:
        return jsonify({'erro': 'Formato não suportado. Use: MP3, MP4, M4A, WAV, OGG, MOV, MKV, WEBM, AAC...'}), 400

    pasta_temp = tempfile.mkdtemp()
    original   = os.path.join(pasta_temp, f'original{ext}')
    arq.save(original)
    tamanho = os.path.getsize(original)
    print(f'[arquivo] {nome} fonte={fonte} tamanho={tamanho} bytes')

    try:
        EXTS_AUDIO_DIRETO = {'.mp3', '.m4a', '.wav', '.ogg', '.flac', '.aac', '.opus'}

        if tamanho <= MAX_GROQ and ext in EXTS_AUDIO_DIRETO:
            # Pequeno e já é áudio — transcreve direto sem ffmpeg
            segmentos = transcrever_audio_groq(original, idioma)
        else:
            # Grande ou é vídeo — precisa do ffmpeg para comprimir/dividir
            if not _tem_ffmpeg():
                return jsonify({'erro': 'Arquivo muito grande e o servidor não tem ffmpeg instalado. Contate o suporte.'}), 500

            chunks = _preparar_chunks(original, pasta_temp)
            if not chunks:
                return jsonify({'erro': 'Erro ao processar o arquivo. Verifique se ele não está corrompido.'}), 500

            segmentos = []
            for chunk_path, offset in chunks:
                print(f'[arquivo] transcrevendo chunk offset={offset}s')
                segs = transcrever_audio_groq(chunk_path, idioma)
                if segs:
                    for s in segs:
                        s['inicio'] = round(s['inicio'] + offset, 1)
                    segmentos.extend(segs)

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
        shutil.rmtree(pasta_temp, ignore_errors=True)


# ── PLAUD WEBHOOK (automático via Zapier) ────────────────────────────────────

@app.route('/api/plaud/webhook/<token>', methods=['POST'])
def plaud_webhook(token):
    """Recebe gravação do Plaud via Zapier (JSON com texto transcrito)."""
    with get_db() as db:
        user = db.execute('SELECT * FROM usuarios WHERE plaud_token = ?', (token,)).fetchone()
    if not user:
        return jsonify({'erro': 'Token inválido.'}), 401

    # Aceita JSON (Zapier) ou form-data
    if request.is_json:
        dados = request.get_json(silent=True) or {}
    else:
        dados = request.form.to_dict()

    print(f'[plaud-webhook] payload recebido: {list(dados.keys())}')

    # Campos que o Plaud pode enviar via Zapier
    titulo = (dados.get('title') or dados.get('name') or
              dados.get('recording_title') or dados.get('Note Title') or
              'Gravação Plaud')

    # Texto da transcrição — tenta vários nomes de campo possíveis
    texto = (dados.get('transcription') or dados.get('transcript') or
             dados.get('content') or dados.get('text') or
             dados.get('Transcription') or dados.get('Content') or
             dados.get('note_content') or '')

    # Se não tiver texto, tenta juntar todos os campos de texto
    if not texto:
        partes = [str(v) for v in dados.values() if isinstance(v, str) and len(v) > 50]
        texto = '\n\n'.join(partes)

    if not texto:
        print(f'[plaud-webhook] payload sem texto: {dados}')
        return jsonify({'erro': 'Nenhum texto recebido. Campos disponíveis: ' + str(list(dados.keys()))}), 400

    # Converte texto em segmentos (sem timestamps, vindo do Plaud)
    paragrafos = [p.strip() for p in texto.split('\n') if p.strip()]
    segmentos  = [{'inicio': 0, 'texto': p} for p in paragrafos] if paragrafos else [{'inicio': 0, 'texto': texto.strip()}]

    with get_db() as db:
        db.execute(
            'INSERT INTO transcricoes (user_id, titulo, fonte, segmentos) VALUES (?, ?, ?, ?)',
            (user['id'], titulo, 'plaud', json.dumps(segmentos))
        )
    print(f'[plaud-webhook] nova nota para user {user["id"]}: {titulo}')
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
