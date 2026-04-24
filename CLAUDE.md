# TranscreveAí — Dashboard de Transcrição do YouTube

## O que é este projeto
Dashboard em HTML puro que permite transcrever vídeos do YouTube colando o link.
Usa a API de legendas do YouTube (gratuita, sem autenticação) + proxies CORS públicos.

## Stack
- HTML + CSS + JavaScript puro (sem frameworks, sem instalação)
- Tailwind CSS via CDN (estilização)
- YouTube oEmbed API (sem auth) — título e thumbnail do vídeo
- YouTube Timedtext API (sem auth) — legendas/transcrição
- CORS proxies: allorigins.win e corsproxy.io (intermediários para contornar bloqueio do navegador)

## Como funciona
1. Usuário cola link do YouTube
2. Sistema extrai o video ID do link
3. Busca título/thumbnail via oEmbed (sem problema de CORS)
4. Busca lista de idiomas disponíveis via `timedtext?type=list` (via proxy)
5. Busca transcrição no idioma selecionado (via proxy)
6. Exibe com timestamps, botão de copiar e download .txt

## Limitações conhecidas
- Só funciona com vídeos que tenham legendas ativadas (automáticas ou manuais)
- Depende de proxies CORS públicos — pode ter instabilidade eventual
- Não transcreve áudio puro — apenas recupera legendas já existentes no YouTube

## Arquivos do projeto
- `index.html` — único arquivo da aplicação (HTML + CSS + JS juntos)
- `plan.md` — planejamento e roadmap do projeto
- `CLAUDE.md` — este arquivo (instruções para o assistente)

## Regras para desenvolvimento
- Manter tudo em um único arquivo `index.html` para máxima simplicidade
- Não usar frameworks JS (React, Vue, etc.)
- Comentar o código em português
- Explicações para iniciantes em primeiro lugar
