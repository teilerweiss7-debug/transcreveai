"""
TranscreveAí — Servidor Backend
Recebe um link do YouTube, baixa o áudio e transcreve usando Groq Whisper (gratuito).

Como configurar:
  1. Acesse https://console.groq.com e crie uma conta gratuita
  2. Gere uma API Key
  3. Cole a chave na linha abaixo (substitua o texto entre aspas)
  4. Rode: python3 server.py
"""

import os
import glob
import tempfile
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from groq import Groq
import yt_dlp

app = Flask(__name__)
CORS(app)  # Permite que o index.html se comunique com este servidor

# ─── COLOQUE SUA CHAVE GROQ AQUI ─────────────────────────────────────────────
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
# ─────────────────────────────────────────────────────────────────────────────


# ─── ROTA PRINCIPAL: serve o dashboard HTML ──────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


# ─── ROTA DE STATUS ──────────────────────────────────────────────────────────
# O dashboard usa essa rota para verificar se o servidor está ligado
@app.route('/api/status', methods=['GET'])
def status():
    return jsonify({
        'online': True,
        'groq_configurado': bool(GROQ_API_KEY),
    })


# ─── ROTA PRINCIPAL: TRANSCRIÇÃO ─────────────────────────────────────────────
@app.route('/api/transcrever', methods=['POST'])
def transcrever():
    dados = request.get_json()
    url    = dados.get('url', '').strip()
    idioma = dados.get('idioma', 'pt')

    if not url:
        return jsonify({'erro': 'Nenhum link foi enviado.'}), 400

    if not GROQ_API_KEY:
        return jsonify({
            'erro': 'Chave da API Groq não configurada. '
                    'Abra o arquivo server.py e cole sua chave na variável GROQ_API_KEY.'
        }), 500

    try:
        # Pasta temporária — tudo é apagado automaticamente ao terminar
        with tempfile.TemporaryDirectory() as pasta_temp:

            # PASSO 1: Baixar o áudio do YouTube
            opcoes = {
                'format': 'bestaudio[ext=m4a]/bestaudio/best',
                'outtmpl': os.path.join(pasta_temp, 'audio.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
                'extractor_args': {'youtube': {'player_client': ['ios', 'web_creator']}},
            }

            # Se houver cookies do YouTube configurados, usa para autenticar
            cookies_conteudo = os.environ.get('YOUTUBE_COOKIES', '')
            arquivo_cookies = None
            if cookies_conteudo:
                import tempfile as tf
                arquivo_cookies = tf.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
                arquivo_cookies.write(cookies_conteudo)
                arquivo_cookies.close()
                opcoes['cookiefile'] = arquivo_cookies.name

            with yt_dlp.YoutubeDL(opcoes) as ydl:
                ydl.download([url])

            if arquivo_cookies:
                os.unlink(arquivo_cookies.name)

            # Encontra o arquivo de áudio baixado
            arquivos = glob.glob(os.path.join(pasta_temp, 'audio.*'))
            if not arquivos:
                return jsonify({'erro': 'Não foi possível baixar o áudio. O vídeo pode ser privado ou bloqueado.'}), 500

            arquivo_audio = arquivos[0]
            extensao = os.path.splitext(arquivo_audio)[1]  # ex: .m4a, .webm

            # PASSO 2: Enviar o áudio para a Groq Whisper transcrever
            cliente = Groq(api_key=GROQ_API_KEY)

            with open(arquivo_audio, 'rb') as f:
                resposta = cliente.audio.transcriptions.create(
                    file=(f'audio{extensao}', f),
                    model='whisper-large-v3',
                    language=idioma,
                    response_format='verbose_json',
                    timestamp_granularities=['segment'],
                )

            # PASSO 3: Formatar os segmentos para o frontend
            # A Groq pode retornar um objeto ou um dicionário — tratamos os dois casos
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


# ─── INICIALIZAÇÃO ────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print('')
    print('  TranscreveAí — Servidor rodando!')
    print('  Acesse o dashboard: abra o arquivo index.html no navegador')
    print('  Para parar: pressione Ctrl+C')
    print('')
    porta = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=porta)
