'use client';
import { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '@/lib/api';
import Dashboard from './Dashboard';
import NovaTranscricao from './NovaTranscricao';
import NotaView from './NotaView';
import Configuracoes from './Configuracoes';
import type { Usuario, Pagina, FonteFiltro } from '@/lib/types';

interface Props {
  usuario: Usuario;
  onLogout: () => void;
}

export default function AppShell({ usuario, onLogout }: Props) {
  const [pagina, setPagina]       = useState<Pagina>('dashboard');
  const [filtro, setFiltro]       = useState<FonteFiltro>(null);
  const [notaId, setNotaId]       = useState<number | null>(null);
  const [toast, setToast]         = useState('');
  const [toastVisible, setToastVisible] = useState(false);

  function mostrarToast(msg: string) {
    setToast(msg);
    setToastVisible(true);
    setTimeout(() => setToastVisible(false), 3000);
  }

  function navegar(p: Pagina, novoFiltro: FonteFiltro = null) {
    setPagina(p);
    setFiltro(novoFiltro);
  }

  function abrirNota(id: number) {
    setNotaId(id);
    navegar('nota');
  }

  async function fazerLogout() {
    await apiFetch('/api/auth/sair', { method: 'POST' });
    onLogout();
  }

  type NavItem = {
    id: string;
    label: string;
    onClick: () => void;
    icon: React.ReactNode;
    active: boolean;
  };

  const navItems: NavItem[] = [
    {
      id: 'dashboard',
      label: 'Todas as notas',
      onClick: () => navegar('dashboard'),
      active: pagina === 'dashboard' && filtro === null,
      icon: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7h18M3 12h18M3 17h18" />,
    },
    {
      id: 'nova',
      label: 'Nova transcrição',
      onClick: () => navegar('nova'),
      active: pagina === 'nova',
      icon: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />,
    },
  ];

  const fonteItems = [
    { key: 'youtube' as const, label: 'YouTube', cor: 'text-red-500', icon: <path d="M23.5 6.2a3 3 0 00-2.1-2.1C19.5 3.6 12 3.6 12 3.6s-7.5 0-9.4.5a3 3 0 00-2.1 2.1C0 8.1 0 12 0 12s0 3.9.5 5.8a3 3 0 002.1 2.1c1.9.5 9.4.5 9.4.5s7.5 0 9.4-.5a3 3 0 002.1-2.1C24 15.9 24 12 24 12s0-3.9-.5-5.8zM9.75 15.5v-7l6.25 3.5-6.25 3.5z" />, fill: true },
    { key: 'arquivo' as const, label: 'Meus arquivos', cor: 'text-blue-500', icon: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />, fill: false },
    { key: 'plaud' as const, label: 'Plaud', cor: 'text-green-500', icon: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />, fill: false },
  ];

  const btnCls = (ativo: boolean) =>
    `w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm font-medium mb-1 transition-all ${ativo ? 'bg-indigo-50 text-brand' : 'text-gray-600 hover:bg-gray-50'}`;

  const inicial = usuario.nome[0]?.toUpperCase() || '?';

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="sidebar bg-white border-r border-gray-100 flex flex-col h-full">
        <div className="p-5 border-b border-gray-100">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 bg-brand rounded-lg flex items-center justify-center">
              <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <span className="font-bold text-gray-900 text-sm">Transcreve IA</span>
          </div>
        </div>

        <nav className="p-3 flex-1 overflow-y-auto scroll-thin">
          {navItems.map(item => (
            <button key={item.id} onClick={item.onClick} className={btnCls(item.active)}>
              <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">{item.icon}</svg>
              {item.label}
            </button>
          ))}

          <div className="mt-4 mb-2 px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">Fontes</div>

          {fonteItems.map(f => (
            <button key={f.key} onClick={() => { navegar('dashboard', f.key); }}
              className={btnCls(pagina === 'dashboard' && filtro === f.key)}>
              <svg className={`w-4 h-4 flex-shrink-0 ${f.cor}`} viewBox="0 0 24 24"
                fill={f.fill ? 'currentColor' : 'none'}
                stroke={f.fill ? undefined : 'currentColor'}>{f.icon}</svg>
              {f.label}
            </button>
          ))}

          <div className="mt-4 mb-2 px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">Conta</div>

          <button onClick={() => navegar('configuracoes')} className={btnCls(pagina === 'configuracoes')}>
            <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <circle cx="12" cy="12" r="3" strokeWidth={2} />
            </svg>
            Configurações
          </button>
        </nav>

        <div className="p-3 border-t border-gray-100">
          <div className="flex items-center gap-2 px-3 py-2">
            <div className="w-7 h-7 bg-indigo-100 rounded-full flex items-center justify-center">
              <span className="text-brand text-xs font-bold">{inicial}</span>
            </div>
            <span className="text-sm text-gray-700 flex-1 truncate font-medium">{usuario.nome}</span>
            <button onClick={fazerLogout} title="Sair" className="text-gray-400 hover:text-red-500 transition-colors">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
            </button>
          </div>
        </div>
      </aside>

      {/* Conteúdo principal */}
      <main className="flex-1 overflow-hidden flex flex-col">
        {pagina === 'dashboard' && (
          <Dashboard filtro={filtro} onAbrirNota={abrirNota} onNova={() => navegar('nova')} />
        )}
        {pagina === 'nova' && (
          <NovaTranscricao onSucesso={(id) => { mostrarToast('Transcrição concluída!'); abrirNota(id); }} />
        )}
        {pagina === 'nota' && notaId !== null && (
          <NotaView key={notaId} id={notaId} onDeletar={() => navegar('dashboard')} onToast={mostrarToast} />
        )}
        {pagina === 'configuracoes' && (
          <Configuracoes usuario={usuario} onLogout={fazerLogout} onToast={mostrarToast} />
        )}
      </main>

      {/* Toast */}
      {toastVisible && (
        <div className="fade-in fixed bottom-6 right-6 bg-gray-900 text-white text-sm px-4 py-3 rounded-xl shadow-lg z-50">
          {toast}
        </div>
      )}
    </div>
  );
}
