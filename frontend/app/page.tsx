'use client';
import { useState, useEffect } from 'react';
import { apiFetch } from '@/lib/api';
import AuthPage from '@/components/AuthPage';
import AppShell from '@/components/AppShell';
import type { Usuario } from '@/lib/types';

export default function Home() {
  const [usuario, setUsuario]     = useState<Usuario | null>(null);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    apiFetch('/api/auth/eu')
      .then(r => r.json())
      .then(d => { if (d.autenticado) setUsuario(d); })
      .catch(() => {})
      .finally(() => setCarregando(false));
  }, []);

  if (carregando) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-indigo-50 to-white">
        <svg className="w-8 h-8 text-brand animate-spin" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeDasharray="40 20" />
        </svg>
      </div>
    );
  }

  if (!usuario) {
    return <AuthPage onLogin={setUsuario} />;
  }

  return <AppShell usuario={usuario} onLogout={() => setUsuario(null)} />;
}
