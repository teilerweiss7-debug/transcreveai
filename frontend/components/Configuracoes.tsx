'use client';
import type { Usuario } from '@/lib/types';

interface Props {
  usuario: Usuario;
  onLogout: () => void;
  onToast: (msg: string) => void;
}

export default function Configuracoes({ usuario, onLogout, onToast }: Props) {
  function copiarWebhook() {
    navigator.clipboard.writeText(usuario.plaud_webhook_url || '');
    onToast('URL copiada!');
  }

  return (
    <div className="flex-1 overflow-y-auto scroll-thin p-8">
      <div className="max-w-2xl mx-auto">
        <h2 className="text-xl font-bold text-gray-900 mb-6">Configurações</h2>

        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6 mb-5">
          <h3 className="font-semibold text-gray-800 mb-4">Minha conta</h3>
          <div className="space-y-2 text-sm">
            <div className="flex items-center gap-2 text-gray-600">
              <span className="font-medium w-14">Nome:</span>
              <span className="text-gray-900">{usuario.nome}</span>
            </div>
            <div className="flex items-center gap-2 text-gray-600">
              <span className="font-medium w-14">E-mail:</span>
              <span className="text-gray-900">{usuario.email}</span>
            </div>
          </div>
          <button onClick={onLogout} className="mt-4 text-sm text-red-500 hover:text-red-700 font-medium transition-colors">
            Sair da conta
          </button>
        </div>

        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 bg-green-100 rounded-xl flex items-center justify-center">
              <svg className="w-4 h-4 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
              </svg>
            </div>
            <div>
              <h3 className="font-semibold text-gray-800">Sincronização automática com Plaud</h3>
              <p className="text-xs text-gray-400">Suas gravações chegam aqui automaticamente</p>
            </div>
          </div>

          <div className="p-3 bg-gray-50 rounded-xl mb-4">
            <p className="text-xs text-gray-500 mb-1.5 font-medium">Sua URL de webhook pessoal:</p>
            <div className="flex items-center gap-2">
              <code className="flex-1 text-xs text-gray-800 bg-white border border-gray-200 rounded-lg px-3 py-2 break-all font-mono">
                {usuario.plaud_webhook_url || 'Não disponível'}
              </code>
              <button onClick={copiarWebhook}
                className="flex-shrink-0 p-2 border border-gray-200 rounded-lg hover:bg-gray-100 transition-colors" title="Copiar">
                <svg className="w-3.5 h-3.5 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
              </button>
            </div>
          </div>

          <div className="text-sm space-y-2">
            <p className="font-medium text-gray-800">Como configurar no Plaud:</p>
            <ol className="list-decimal list-inside space-y-1 text-gray-600 text-xs">
              <li>Abra o app Plaud no celular</li>
              <li>Vá em <strong>Configurações → Integrações → Webhook</strong></li>
              <li>Cole a URL acima no campo de webhook</li>
              <li>Quando terminar uma gravação, ela aparece aqui automaticamente</li>
            </ol>
            <div className="text-xs text-yellow-700 bg-yellow-50 border border-yellow-200 rounded-lg p-3 mt-3">
              ⚠️ O suporte a webhook pode variar conforme a versão do app Plaud. Se não encontrar essa opção, use o <strong>upload manual</strong>.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
