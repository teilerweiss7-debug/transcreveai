export const API = process.env.NEXT_PUBLIC_API_URL ?? '';

export async function apiFetch(path: string, opts?: RequestInit) {
  return fetch(`${API}${path}`, {
    credentials: 'include',
    ...opts,
  });
}

export function fonteInfo(fonte: string): { cls: string; label: string } {
  if (fonte.includes('youtube')) return { cls: 'fonte-youtube', label: 'YouTube' };
  if (fonte === 'plaud')         return { cls: 'fonte-plaud',   label: 'Plaud' };
  return                                { cls: 'fonte-arquivo', label: 'Arquivo' };
}

export function fmtTempo(s: number): string {
  const m   = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, '0')}`;
}

export function fmtData(raw: string): string {
  try {
    return new Date(raw).toLocaleDateString('pt-BR', {
      day: '2-digit', month: 'short', year: 'numeric',
    });
  } catch {
    return raw;
  }
}
