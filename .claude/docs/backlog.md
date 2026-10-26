# Backlog

Um ticket = um commit atômico (`DEV-XXXX: ...`). Fluxo por ticket: dev → `code-reviewer`
(+ `ponytail:ponytail-review`) → `qa-automation` → commit. Máximo 5 ativos.

## DEV-0001 — Fundação e documentação · `gestor-conhecimento` / `tech-lead`
- [ ] `git init`, `.gitignore`, `CLAUDE.md` e `.claude/` da softhouse na raiz
- [ ] `.claude/docs/` completo (este índice)
- **Aceite:** docs revisáveis; `git status` limpo após commit.

## DEV-0002 — Reuniões em pasta (F1) · `dev-backend`
- **Escopo:** `ata/store.py` — `create`, `list_meetings`, `load`, `save_notes`,
  `append_segments`, `save_ata`, `finish`; formato de `transcript.md`.
- **Fora:** HTTP, áudio.
- **Testes:** `tests/test_store.py` (criação, colisão no mesmo minuto, listagem ordenada,
  ida e volta de segmentos).
- **Risco:** nomes de pasta inválidos no Windows — id gerado pelo app, título só no JSON.

## DEV-0003 — Servidor e página (F2, F5) · `dev-frontend`
- **Escopo:** `ata/server.py` com rotas de `arquitetura.md`; `ata/web/index.html` com
  gravar/parar, título, idioma, notas com autosave, lista de reuniões, status.
  Design próprio via `frontend-design`/`impeccable`.
- **Fora:** captura real (stub de sessão até DEV-0004).
- **Testes:** QA no navegador (Playwright) + heurísticas de Nielsen.
- **Risco:** perder notas — autosave com debounce e flush ao trocar de reunião.

## DEV-0004 — Captura em duas trilhas (F3) · `dev-backend`
- **Escopo:** `ata/capture.py` (PyAudioWPatch: mic padrão + loopback do output padrão →
  WAVs nativos; nível de pico para o medidor); ligar em `server.py`; `requirements.txt`.
- **Testes:** manual — vídeo tocando + fala; conferir WAVs separados.
- **Risco:** loopback não entrega frames em silêncio — escrever silêncio para manter o
  alinhamento de tempo entre trilhas.

## DEV-0005 — Transcrição local (F4) · `dev-backend`
- **Escopo:** obter whisper.cpp (Vulkan; plano B CPU) e modelo; `ata/transcribe.py`
  (blocos de 30 s via ffmpeg, `whisper-cli -l`, merge Eu/Outros, filtro de alucinação em
  silêncio); transcrição ao vivo na página.
- **Testes:** `tests/test_transcribe.py` (merge por tempo, parse da saída do whisper,
  filtro).
- **Risco:** compilar Vulkan exige cmake/SDK/Build Tools → **aprovação do CEO**.

## DEV-0006 — Resumo e conversa (F6) · `engenheiro-ia` + `engenheiro-prompt` · revisão `seguranca`
- **Escopo:** `ata/enhance.py` (urllib, `.env`, JSON mode no chat), `ata/prompt.md` (resumo
  por tópicos), `ata/chat.md` (perguntar/citar/reformular), `store` com `chat.json` e
  `ata-history.json`; rotas `POST /chat`, `POST /undo`; resumo gerado ao parar; painel de
  conversa, "Incluir no resumo" e "Desfazer" na página.
- **Testes:** `tests/test_enhance.py` (mensagens, parse do JSON, `.env`, erro HTTP sem vazar
  chave), `tests/test_store.py` (versões, desfazer, chat); 1 reunião real pt e 1 en.
- **Risco:** chave vazar em log/erro; prompt injection vinda da transcrição (prompts tratam o
  material como dado); conversa longa estourar contexto (últimas 20 mensagens).

## DEV-0007 — Aviso de reunião (F7) · `dev-backend`
- **Escopo:** `ata/detect.py` (winreg), campo `detected` no `/api/status`, banner +
  Notification na página.
- **Testes:** `tests/test_detect.py` (classificação de executáveis e de chaves).
- **Risco:** falso positivo de navegador — aceito (só aviso).

## DEV-0008 — README de uso · `gestor-conhecimento`
- **Escopo:** `README.md` na raiz — instalar dependências, whisper.cpp, modelo, chave,
  rodar, onde ficam as reuniões.
- **Aceite:** alguém segue o README do zero e grava uma reunião.

## DEV-0009 — Apagar o áudio após a transcrição · `dev-backend`
- **Escopo:** `store.delete_audio()` chamado em `_finalize` depois de `transcriber.finish()`.
- **Testes:** `tests/test_store.py` (apaga os WAVs, mantém o texto, idempotente).
- **Risco:** perder o áudio de uma reunião cuja transcrição falhou — por isso só apaga no sucesso.

## Pendências conhecidas (baixa severidade)
- "Incluir no resumo" aparece também em respostas sem conteúdo útil ("isso não foi falado",
  "já está no resumo"); clicar gasta uma chamada à toa. Ideia: a resposta do modelo indicar se é
  incluível.
- O rótulo "Resumo atualizado" continua na mensagem do chat depois de "Desfazer".
