# Plano do Projeto — TranscreveAí

## Objetivo
Criar um dashboard simples em HTML que permite transcrever vídeos do YouTube
colando o link, usando apenas APIs gratuitas e sem autenticação.

---

## Fase 1 — MVP (Concluída ✅)
- [x] Estrutura HTML com Tailwind CSS via CDN
- [x] Extração de video ID de qualquer formato de URL do YouTube
- [x] Busca de título e thumbnail via YouTube oEmbed (sem API key)
- [x] Busca de legendas via YouTube Timedtext API + proxy CORS
- [x] Seleção automática de idioma com fallback para inglês
- [x] Exibição da transcrição com timestamps clicáveis
- [x] Toggle para mostrar/ocultar timestamps
- [x] Botão "Copiar tudo" para área de transferência
- [x] Download da transcrição como arquivo .txt
- [x] Estados visuais de loading (carregando) e erro

---

## Fase 2 — Melhorias futuras (planejado)
- [ ] Modo escuro
- [ ] Campo de busca dentro da transcrição
- [ ] Exportar como .srt (formato padrão de legendas)
- [ ] Histórico das últimas transcrições (salvo no navegador)
- [ ] Detectar idioma automaticamente sem o usuário precisar escolher
- [ ] Resumo automático com IA (ex: integração com API gratuita)

---

## Decisões técnicas

### Por que HTML puro e não React/Vue?
Para máxima simplicidade. Não precisa instalar nada — basta abrir o arquivo no navegador.

### Por que precisamos de um proxy CORS?
O navegador tem uma proteção de segurança chamada CORS que bloqueia chamadas diretas
a outros sites. O proxy age como um "carteiro intermediário": o site pede ao carteiro,
o carteiro busca a informação no YouTube, e traz de volta para o site.

### Por que oEmbed para informações do vídeo?
É a única API pública do YouTube que aceita chamadas diretas do navegador sem precisar
de conta ou chave de acesso.

### Por que usar a API timedtext e não a YouTube Data API?
A YouTube Data API exige cadastro e chave de acesso. O endpoint `timedtext` é uma API
interna do YouTube usada pelo próprio player — funciona sem autenticação para vídeos
com legendas públicas.

---

## Estrutura do arquivo index.html

```
index.html
├── <head>         → configurações, Tailwind CSS
├── <header>       → logo e título do app
├── <main>
│   ├── Card de input    → campo de URL + seletor de idioma + botão
│   ├── Card de loading  → spinner animado durante a busca
│   ├── Card de erro     → mensagem amigável se algo der errado
│   └── Card de resultado
│       ├── Info do vídeo (thumbnail + título + canal)
│       └── Transcrição (com timestamps, copiar, baixar)
└── <script>       → toda a lógica JavaScript
```
