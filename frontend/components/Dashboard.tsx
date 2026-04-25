'use client';
import { useEffect, useState } from 'react';
import { apiFetch, fonteInfo, fmtData } from '@/lib/api';
import type { Transcricao, FonteFiltro } from '@/lib/types';

interface Props {
  filtro: FonteFiltro;
  onAbrirNota: (id: number) => void;
  onNova: () => void;
}

export default function Dashboard({ filtro, onAbrirNota, onNova }: Props) {
  const [items, setItems]         = useState<Transcricao[]>([]);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    setCarregando(true);
    apiFetch('/api/transcricoes')
      .then(r => r.json())
      .then((data: Transcricao[]) => {
        setItems(filtro ? data.filter(t => t.fonte.includes(filtro)) : data);
      })
      .finally(() => setCarregando(false));
  }, [filtro]);

  const titulo = filtro === 'youtube' ? 'YouTube'
               : filtro === 'arquivo' ? 'Meus arquivos'
               : filtro === 'plaud'   ? 'Plaud'
               : 'Todas as notas';

  return (
    <div className="flex-1 overflow-y-auto scroll-thin p-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold text-gray-900">{titulo}</h2>
          <button onClick={onNova}
            className="flex items-center gap-2 bg-brand hover:bg-brand-dark text-white px-4 py-2 rounded-xl text-sm font-medium transition-colors">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Nova transcrição
          </button>
        </div>

        {carregando ? (
          <div className="text-center py-8 text-gray-400 text-sm">Carregando...</div>
        ) : items.length === 0 ? (
          <div className="text-center py-16 text-gray-400">
            <svg className="w-12 h-12 mx-auto mb-3 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <p className="font-medium">Nenhuma nota ainda</p>
            <p className="text-sm mt-1">Crie sua primeira transcrição</p>
          </div>
        ) : (
          <div className="grid gap-3">
            {items.map(t => {
              const b = fonteInfo(t.fonte);
              return (
                <div key={t.id} onClick={() => onAbrirNota(t.id)}
                  className="bg-white rounded-xl border border-gray-100 p-4 cursor-pointer hover:shadow-md hover:border-brand transition-all fade-in">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className={`fonte-badge ${b.cls}`}>{b.label}</span>
                        <span className="text-xs text-gray-400">{fmtData(t.created_at)}</span>
                      </div>
                      <h3 className="font-semibold text-gray-900 text-sm truncate">{t.titulo}</h3>
                    </div>
                    <svg className="w-4 h-4 text-gray-300 flex-shrink-0 mt-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
