'use client';
import { useEffect, useRef, useState } from 'react';
import { apiFetch, fonteInfo, fmtTempo, fmtData } from '@/lib/api';
import type { Transcricao, Segmento, MensagemChat } from '@/lib/types';

interface Props {
  id: number;
  onDeletar: () => void;
  onToast: (msg: string) => void;
}

export default function NotaView({ id, onDeletar, onToast }: Props) {
  const [nota, setNota]         = useState<Transcricao | null>(null);
  const [msgs, setMsgs]         = useState<MensagemChat[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [enviando, setEnviando] = useState(false);
  const chatRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    apiFetch(`/api/transcricoes/${id}`)
      .then(r => r.json())
      .then(setNota);
    apiFetch(`/api/transcricoes/${id}/chat`)
      .then(r => r.json())
      .then(setMsgs);
  }, [id]);

  useEffect(() => {
    if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight;
  }, [msgs]);

  function copiar() {
    if (!nota) return;
    const segs: Segmento[] = JSON.parse(nota.segmentos);
    navigator.clipboard.writeText(segs.map(s => `[${fmtTempo(s.inicio)}] ${s.texto}`).join('\n'));
    onToast('Copiado!');
  }

  function baixar() {
    if (!nota) return;
    const segs: Segmento[] = JSON.parse(nota.segmentos);
    const txt  = segs.map(s => `[${fmtTempo(s.inicio)}] ${s.texto}`).join('\n');
    const a    = document.createElement('a');
    a.href     = URL.createObjectURL(new Blob([txt], { type: 'text/plain' }));
    a.download = `${nota.titulo}.txt`;
    a.click();
  }

  async function deletar() {
    if (!confirm('Deletar esta transcrição? Esta ação não pode ser desfeita.')) return;
    await apiFetch(`/api/transcricoes/${id}`, { method: 'DELETE' });
    onDeletar();
    onToast('Transcrição deletada.');
  }

  async function enviarChat() {
    const msg = chatInput.trim();
    if (!msg) return;
    setChatInput('');
    setMsgs(prev => [...prev, { papel: 'user', conteudo: msg }]);
    setEnviando(true);
    try {
      const r = await apiFetch(`/api/transcricoes/${id}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mensagem: msg }),
      });
      const d = await r.json();
      setMsgs(prev => [...prev, { papel: 'assistant', conteudo: d.resposta || ('⚠️ ' + (d.erro || 'Erro')) }]);
    } catch {
      setMsgs(prev => [...prev, { papel: 'assistant', conteudo: '⚠️ Erro de conexão.' }]);
    } finally {
      setEnviando(false);
    }
  }

  if (!nota) return <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">Carregando...</div>;

  const b    = fonteInfo(nota.fonte);
  const segs: Segmento[] = JSON.parse(nota.segmentos);

  return (
    <div className="flex-1 overflow-hidden flex">
      {/* Transcrição */}
      <div className="flex-1 overflow-y-auto scroll-thin p-6">
        <div className="max-w-2xl mx-auto">
          <div className="flex items-start justify-between mb-5 gap-4">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2">
                <span className={`fonte-badge ${b.cls}`}>{b.label}</span>
                <span className="text-xs text-gray-400">{fmtData(nota.created_at)}</span>
              </div>
              <h2 className="text-xl font-bold text-gray-900">{nota.titulo}</h2>
            </div>
            <div className="flex gap-2 flex-shrink-0">
              <button onClick={copiar} title="Copiar"
                className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500 transition-colors">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
              </button>
              <button onClick={baixar} title="Baixar .txt"
                className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500 transition-colors">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
              </button>
              <button onClick={deletar} title="Deletar"
                className="p-2 rounded-lg border border-red-100 hover:bg-red-50 text-red-400 transition-colors">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          </div>

          <div className="space-y-1 text-gray-800 text-sm leading-relaxed">
            {segs.map((s, i) => (
              <div key={i} className="flex gap-3 py-1.5 border-b border-gray-50 last:border-0 hover:bg-gray-50 rounded-lg px-2 -mx-2 transition-colors">
                <span className="text-xs text-gray-400 font-mono pt-0.5 w-10 flex-shrink-0">{fmtTempo(s.inicio)}</span>
                <span className="text-gray-800 leading-relaxed">{s.texto}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Chat */}
      <div className="w-80 border-l border-gray-100 flex flex-col bg-white">
        <div className="p-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-brand rounded-lg flex items-center justify-center">
              <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
              </svg>
            </div>
            <span className="text-sm font-semibold text-gray-900">Chat com IA</span>
          </div>
          <p className="text-xs text-gray-400 mt-1">Pergunte sobre este conteúdo</p>
        </div>

        <div ref={chatRef} className="flex-1 overflow-y-auto scroll-thin p-3 space-y-3">
          {msgs.length === 0 ? (
            <p className="text-center text-xs text-gray-400 py-4">Faça perguntas sobre a transcrição ou peça um resumo.</p>
          ) : (
            msgs.map((m, i) => (
              <div key={i} className={`fade-in flex ${m.papel === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[85%] text-xs px-3 py-2 ${m.papel === 'user' ? 'chat-bubble-user' : 'chat-bubble-ai'}`}>
                  {m.conteudo.split('\n').map((l, j) => <span key={j}>{l}{j < m.conteudo.split('\n').length - 1 && <br />}</span>)}
                </div>
              </div>
            ))
          )}
          {enviando && (
            <div className="flex justify-start">
              <div className="chat-bubble-ai max-w-[85%] text-xs px-3 py-2 text-gray-400">IA pensando...</div>
            </div>
          )}
        </div>

        <div className="p-3 border-t border-gray-100">
          <div className="flex gap-2">
            <input value={chatInput} onChange={e => setChatInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && enviarChat()}
              type="text" placeholder="Pergunte algo..."
              className="flex-1 border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand" />
            <button onClick={enviarChat} disabled={enviando}
              className="p-2 bg-brand hover:bg-brand-dark disabled:opacity-60 text-white rounded-xl transition-colors">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
