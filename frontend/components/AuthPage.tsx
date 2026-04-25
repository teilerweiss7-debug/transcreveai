'use client';
import { useState } from 'react';
import { apiFetch } from '@/lib/api';
import type { Usuario } from '@/lib/types';

interface Props {
  onLogin: (u: Usuario) => void;
}

export default function AuthPage({ onLogin }: Props) {
  const [aba, setAba]     = useState<'entrar' | 'cadastrar'>('entrar');
  const [erro, setErro]   = useState('');
  const [carregando, setCarregando] = useState(false);

  const [email, setEmail] = useState('');
  const [senha, setSenha] = useState('');
  const [nome, setNome]   = useState('');

  async function fazerLogin() {
    setErro(''); setCarregando(true);
    try {
      const r = await apiFetch('/api/auth/entrar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, senha }),
      });
      const d = await r.json();
      if (d.sucesso) {
        const eu = await (await apiFetch('/api/auth/eu')).json();
        onLogin(eu);
      } else {
        setErro(d.erro || 'Erro ao entrar.');
      }
    } catch {
      setErro('Erro de conexão. Tente novamente.');
    } finally {
      setCarregando(false);
    }
  }

  async function fazerCadastro() {
    setErro(''); setCarregando(true);
    try {
      const r = await apiFetch('/api/auth/cadastrar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nome, email, senha }),
      });
      const d = await r.json();
      if (d.sucesso) {
        const eu = await (await apiFetch('/api/auth/eu')).json();
        onLogin(eu);
      } else {
        setErro(d.erro || 'Erro ao criar conta.');
      }
    } catch {
      setErro('Erro de conexão. Tente novamente.');
    } finally {
      setCarregando(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-gradient-to-br from-indigo-50 to-white">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="w-14 h-14 bg-brand rounded-2xl flex items-center justify-center mx-auto mb-3 shadow-lg">
            <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Transcreve IA</h1>
          <p className="text-gray-500 text-sm mt-1">Sua plataforma de aprendizado</p>
        </div>

        {/* Abas */}
        <div className="flex bg-gray-100 rounded-xl p-1 mb-6">
          {(['entrar', 'cadastrar'] as const).map(a => (
            <button key={a} onClick={() => { setAba(a); setErro(''); }}
              className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all ${aba === a ? 'bg-white shadow text-gray-900' : 'text-gray-500'}`}>
              {a === 'entrar' ? 'Entrar' : 'Criar conta'}
            </button>
          ))}
        </div>

        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 space-y-4">
          {aba === 'cadastrar' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Nome</label>
              <input value={nome} onChange={e => setNome(e.target.value)} type="text" placeholder="Seu nome"
                className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand focus:border-transparent" />
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">E-mail</label>
            <input value={email} onChange={e => setEmail(e.target.value)} type="email" placeholder="seu@email.com"
              className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand focus:border-transparent" />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Senha</label>
            <input value={senha} onChange={e => setSenha(e.target.value)} type="password"
              placeholder={aba === 'cadastrar' ? 'Mínimo 6 caracteres' : '••••••••'}
              onKeyDown={e => e.key === 'Enter' && (aba === 'entrar' ? fazerLogin() : fazerCadastro())}
              className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand focus:border-transparent" />
          </div>

          {erro && <p className="text-red-500 text-sm">{erro}</p>}

          <button onClick={aba === 'entrar' ? fazerLogin : fazerCadastro} disabled={carregando}
            className="w-full bg-brand hover:bg-brand-dark disabled:opacity-60 text-white py-2.5 rounded-xl font-medium transition-colors">
            {carregando ? 'Aguarde...' : aba === 'entrar' ? 'Entrar' : 'Criar conta'}
          </button>
        </div>
      </div>
    </div>
  );
}
