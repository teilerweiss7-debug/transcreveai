'use client';
import { useRef, useState } from 'react';
import { apiFetch } from '@/lib/api';

interface Props {
  onSucesso: (id: number) => void;
}

type FonteAba = 'youtube' | 'arquivo' | 'plaud';

export default function NovaTranscricao({ onSucesso }: Props) {
  const [aba, setAba]           = useState<FonteAba>('youtube');
  const [ytUrl, setYtUrl]       = useState('');
  const [ytIdioma, setYtIdioma] = useState('pt');
  const [arqIdioma, setArqIdioma] = useState('pt');
  const [plaudIdioma, setPlaudIdioma] = useState('pt');
  const [arqNome, setArqNome]   = useState('');
  const [plaudNome, setPlaudNome] = useState('');
  const [progresso, setProgresso] = useState('');
  const [erro, setErro]         = useState('');
  const [carregando, setCarregando] = useState(false);

  const arqRef   = useRef<HTMLInputElement>(null);
  const plaudRef = useRef<HTMLInputElement>(null);

  function iniciar(msg: string) {
    setErro(''); setProgresso(msg); setCarregando(true);
  }

  function finalizar() {
    setProgresso(''); setCarregando(false);
  }

  async function transcreverYoutube() {
    if (!ytUrl.trim()) { setErro('Cole o link do vídeo.'); return; }
    iniciar('Buscando transcrição...');
    const timer = setTimeout(() => setProgresso('Transcrevendo com IA... (pode demorar alguns minutos)'), 5000);
    try {
      const r = await apiFetch('/api/transcrever/youtube', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: ytUrl.trim(), idioma: ytIdioma }),
      });
      const d = await r.json();
      clearTimeout(timer);
      if (d.sucesso) { setYtUrl(''); onSucesso(d.id); }
      else setErro(d.erro || 'Erro desconhecido.');
    } catch {
      clearTimeout(timer);
      setErro('Erro de conexão.');
    } finally { finalizar(); }
  }

  async function transcreverArquivo() {
    const file = arqRef.current?.files?.[0];
    if (!file) { setErro('Selecione um arquivo.'); return; }
    iniciar('Enviando e transcrevendo...');
    const form = new FormData();
    form.append('arquivo', file); form.append('idioma', arqIdioma); form.append('fonte', 'arquivo');
    try {
      const r = await apiFetch('/api/transcrever/arquivo', { method: 'POST', body: form });
      const d = await r.json();
      if (d.sucesso) { if (arqRef.current) arqRef.current.value = ''; setArqNome(''); onSucesso(d.id); }
      else setErro(d.erro || 'Erro desconhecido.');
    } catch { setErro('Erro de conexão.'); }
    finally { finalizar(); }
  }

  async function transcreverPlaud() {
    const file = plaudRef.current?.files?.[0];
    if (!file) { setErro('Selecione um arquivo do Plaud.'); return; }
    iniciar('Transcrevendo gravação Plaud...');
    const form = new FormData();
    form.append('arquivo', file); form.append('idioma', plaudIdioma); form.append('fonte', 'plaud');
    try {
      const r = await apiFetch('/api/transcrever/arquivo', { method: 'POST', body: form });
      const d = await r.json();
      if (d.sucesso) { if (plaudRef.current) plaudRef.current.value = ''; setPlaudNome(''); onSucesso(d.id); }
      else setErro(d.erro || 'Erro desconhecido.');
    } catch { setErro('Erro de conexão.'); }
    finally { finalizar(); }
  }

  const selectCls = 'border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand';
  const idiomaOpts = (
    <>
      <option value="pt">Português</option>
      <option value="en">Inglês</option>
      <option value="es">Espanhol</option>
    </>
  );

  return (
    <div className="flex-1 overflow-y-auto scroll-thin p-8">
      <div className="max-w-2xl mx-auto">
        <h2 className="text-xl font-bold text-gray-900 mb-6">Nova transcrição</h2>

        {/* Abas de fonte */}
        <div className="flex gap-2 mb-6">
          {([
            { key: 'youtube', label: 'YouTube', icon: <path d="M23.5 6.2a3 3 0 00-2.1-2.1C19.5 3.6 12 3.6 12 3.6s-7.5 0-9.4.5a3 3 0 00-2.1 2.1C0 8.1 0 12 0 12s0 3.9.5 5.8a3 3 0 002.1 2.1c1.9.5 9.4.5 9.4.5s7.5 0 9.4-.5a3 3 0 002.1-2.1C24 15.9 24 12 24 12s0-3.9-.5-5.8zM9.75 15.5v-7l6.25 3.5-6.25 3.5z" />, fill: true },
            { key: 'arquivo', label: 'Arquivo', icon: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />, fill: false },
            { key: 'plaud',   label: 'Plaud',   icon: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />, fill: false },
          ] as const).map(({ key, label, icon, fill }) => (
            <button key={key} onClick={() => { setAba(key); setErro(''); }}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium border-2 transition-all ${aba === key ? 'border-brand bg-indigo-50 text-brand' : 'border-gray-200 text-gray-500 hover:border-gray-300'}`}>
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill={fill ? 'currentColor' : 'none'} stroke={fill ? undefined : 'currentColor'}>{icon}</svg>
              {label}
            </button>
          ))}
        </div>

        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">

          {/* YouTube */}
          {aba === 'youtube' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Link do vídeo</label>
              <input value={ytUrl} onChange={e => setYtUrl(e.target.value)} type="url"
                placeholder="https://youtube.com/watch?v=..."
                className="w-full border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-brand focus:border-transparent mb-4" />
              <div className="flex items-center gap-3 mb-5">
                <label className="text-sm font-medium text-gray-700">Idioma:</label>
                <select value={ytIdioma} onChange={e => setYtIdioma(e.target.value)} className={selectCls}>
                  {idiomaOpts}
                  <option value="fr">Francês</option>
                  <option value="de">Alemão</option>
                </select>
              </div>
              <button onClick={transcreverYoutube} disabled={carregando}
                className="w-full bg-brand hover:bg-brand-dark disabled:opacity-60 text-white py-3 rounded-xl font-medium transition-colors">
                Transcrever vídeo
              </button>
            </div>
          )}

          {/* Arquivo */}
          {aba === 'arquivo' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Arquivo de áudio ou vídeo</label>
              <div onClick={() => arqRef.current?.click()}
                className="border-2 border-dashed border-gray-200 rounded-xl p-8 text-center cursor-pointer hover:border-brand hover:bg-indigo-50 transition-all mb-4">
                <svg className="w-10 h-10 mx-auto mb-2 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                <p className="text-sm text-gray-500">{arqNome || 'Clique para selecionar'}</p>
                <p className="text-xs text-gray-400 mt-1">MP3, MP4, M4A, WAV, OGG, WEBM — até 500 MB</p>
              </div>
              <input ref={arqRef} type="file" accept=".mp3,.mp4,.m4a,.wav,.ogg,.webm,.mov,.mkv,.flac,.aac,.opus"
                className="hidden" onChange={e => setArqNome(e.target.files?.[0]?.name || '')} />
              <div className="flex items-center gap-3 mb-5">
                <label className="text-sm font-medium text-gray-700">Idioma:</label>
                <select value={arqIdioma} onChange={e => setArqIdioma(e.target.value)} className={selectCls}>{idiomaOpts}</select>
              </div>
              <button onClick={transcreverArquivo} disabled={carregando}
                className="w-full bg-brand hover:bg-brand-dark disabled:opacity-60 text-white py-3 rounded-xl font-medium transition-colors">
                Transcrever arquivo
              </button>
            </div>
          )}

          {/* Plaud */}
          {aba === 'plaud' && (
            <div>
              <div className="flex items-start gap-3 p-4 bg-green-50 border border-green-200 rounded-xl mb-5">
                <svg className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div className="text-sm text-green-800">
                  <p className="font-semibold mb-1">Como conectar o Plaud</p>
                  <p>Use o upload manual abaixo ou configure o webhook automático nas <strong>Configurações</strong>.</p>
                </div>
              </div>
              <p className="text-sm font-medium text-gray-700 mb-2">Upload manual de gravação Plaud</p>
              <div onClick={() => plaudRef.current?.click()}
                className="border-2 border-dashed border-gray-200 rounded-xl p-8 text-center cursor-pointer hover:border-green-400 hover:bg-green-50 transition-all mb-4">
                <svg className="w-10 h-10 mx-auto mb-2 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                </svg>
                <p className="text-sm text-gray-500">{plaudNome || 'Selecionar gravação Plaud'}</p>
                <p className="text-xs text-gray-400 mt-1">M4A, MP3, WAV — áudio da reunião</p>
              </div>
              <input ref={plaudRef} type="file" accept=".mp3,.m4a,.wav,.ogg,.aac,.opus"
                className="hidden" onChange={e => setPlaudNome(e.target.files?.[0]?.name || '')} />
              <div className="flex items-center gap-3 mb-5">
                <label className="text-sm font-medium text-gray-700">Idioma:</label>
                <select value={plaudIdioma} onChange={e => setPlaudIdioma(e.target.value)} className={selectCls}>{idiomaOpts}</select>
              </div>
              <button onClick={transcreverPlaud} disabled={carregando}
                className="w-full bg-green-600 hover:bg-green-700 disabled:opacity-60 text-white py-3 rounded-xl font-medium transition-colors">
                Transcrever gravação Plaud
              </button>
            </div>
          )}

          {progresso && (
            <div className="mt-4 text-center">
              <div className="inline-flex items-center gap-2 text-brand">
                <svg className="w-5 h-5 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeDasharray="40 20" />
                </svg>
                <span className="text-sm font-medium">{progresso}</span>
              </div>
            </div>
          )}

          {erro && (
            <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">{erro}</div>
          )}
        </div>
      </div>
    </div>
  );
}
