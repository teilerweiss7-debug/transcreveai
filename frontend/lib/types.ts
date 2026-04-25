export interface Usuario {
  nome: string;
  email: string;
  plaud_webhook_url: string;
}

export interface Transcricao {
  id: number;
  titulo: string;
  fonte: string;
  segmentos: string;
  video_url?: string;
  filename?: string;
  created_at: string;
}

export interface Segmento {
  inicio: number;
  texto: string;
}

export interface MensagemChat {
  papel: 'user' | 'assistant';
  conteudo: string;
  created_at?: string;
}

export type Pagina = 'dashboard' | 'nova' | 'nota' | 'configuracoes';
export type FonteFiltro = 'youtube' | 'arquivo' | 'plaud' | null;
