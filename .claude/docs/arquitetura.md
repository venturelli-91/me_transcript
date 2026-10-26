# Arquitetura

## Visão geral

```
 navegador (web/index.html)
      │  polling /api/status (1 s), fetch JSON
      ▼
 server.py ──── store.py ──── meetings/<id>/  (arquivos)
      │
      ├── capture.py   PyAudioWPatch: mic + loopback  → mic.wav, system.wav
      ├── transcribe.py thread: blocos 30 s → ffmpeg → whisper-cli → segmentos
      ├── enhance.py    urllib → DeepSeek → resumo (ata.md) e conversa (chat.json)
      ├── detect.py     winreg ConsentStore → app de reunião usando o mic?
      └── mail.py       smtplib (Gmail, senha de app) → resumo para o próprio e-mail
```

Um processo Python, sem framework. `server.py` é o único ponto que conhece todos os
módulos; os demais não se importam entre si (exceto `transcribe` lendo os WAVs que
`capture` escreve, via caminho de arquivo).

## Módulos

| Módulo | Responsabilidade | Depende de |
|---|---|---|
| `store.py` | Criar/listar/ler/salvar reunião; formato de `transcript.md` | stdlib |
| `capture.py` | Abrir mic e loopback, gravar WAV nativo, expor nível de áudio | PyAudioWPatch |
| `transcribe.py` | Ler blocos novos dos WAVs, converter, transcrever, intercalar Eu/Outros | ffmpeg, whisper-cli |
| `enhance.py` | Montar mensagens com `prompt.md` e chamar a DeepSeek | stdlib (`urllib`) |
| `detect.py` | Ler o registro e dizer qual app de reunião está com o mic aberto | stdlib (`winreg`) |
| `server.py` | HTTP, estado da sessão de gravação, orquestração | todos acima |

## Estado da sessão
Um único objeto `Session` em `server.py`, protegido por `threading.Lock`:
`phase` ∈ `idle | recording | transcribing | enhancing | done | error`, `meeting_id`,
`started_at`, `segments`, `levels`, `error`.

ponytail: uma sessão global — o app é de uma pessoa, uma reunião por vez.

## Fluxo de uma reunião
1. `POST /api/start` → `store.create()` → `capture.start()` → `transcribe` inicia thread.
2. A thread de transcrição, a cada 30 s, pega o trecho novo de cada WAV
   (`ffmpeg -ss/-t` → 16 kHz mono) e passa pelo VAD Silero (`whisper-vad-speech-segments`); com ≥ 0,5 s de voz, roda
   `whisper-cli -l <lang> -ot <início da voz> -oj` na janela (GPU via Vulkan), em prioridade
   baixa do Windows. Os segmentos com
   tempo absoluto vão para `Session.segments` e para `transcript.md`.
3. `POST /api/stop` → `capture.stop()` → transcreve o resto → `phase = enhancing` →
   `enhance.summarize()` → `ata.md` → `phase = done`. Falha na transcrição ou no resumo →
   `phase = error` com mensagem; nada salvo é apagado. Reunião sigilosa pula o resumo.
4. Na reunião aberta, cada mensagem do chat chama `enhance.chat()` (JSON mode): a resposta vai
   para `chat.json`; se veio `summary`, a versão anterior vai para `ata-history.json` e o novo
   texto para `ata.md`. "Desfazer" restaura a última versão do histórico.

## Contrato da API (JSON, 127.0.0.1 apenas)

| Método e rota | Corpo | Resposta |
|---|---|---|
| `GET /` | — | `web/index.html` |
| `GET /api/status` | — | `{phase, meeting_id, elapsed, levels:{mic,system}, segments:[...], detected, error}` |
| `GET /api/meetings` | — | `[{id, title, started_at, has_ata}]` |
| `GET /api/meetings/<id>` | — | `{id, title, lang, private, started_at, ended_at, notes, transcript, ata, chat, can_undo}` |
| `POST /api/start` | `{title?, lang: "pt"\|"en", private?: bool}` | `{id}` · `409` se já gravando |
| `POST /api/stop` | — | `{}` (processamento segue em background) |
| `PUT /api/meetings/<id>/notes` | `{notes}` | `{}` |
| `POST /api/meetings/<id>/ata` | — | reunião atualizada (gera o resumo de novo; síncrono) |
| `POST /api/meetings/<id>/chat` | `{message}` (1–4000 caracteres) | reunião atualizada |
| `POST /api/meetings/<id>/undo` | — | reunião atualizada · `409` sem versão anterior |
| `POST /api/meetings/<id>/email` | — | reunião atualizada · `409` se sigilosa, sem resumo ou falha de envio |

Toda escrita exige `Host` local e `Content-Type: application/json` (bloqueia DNS rebinding e
POST de outros sites).

Segmento: `{"t": 83.2, "who": "Eu" | "Outros", "text": "..."}` (`t` em segundos desde o início).

## Formatos em disco
- `meta.json`: `{"title", "lang", "private", "started_at", "ended_at", "emailed_at"?, "email_error"?}`
  (ISO 8601 local). O `GET` da reunião acrescenta `email_configured`.
- `chat.json`: `[{"role": "user"|"assistant", "content", "changed_summary"?}]`.
- `ata-history.json`: versões anteriores do resumo (pilha para "Desfazer").
- Escritas são atômicas (`.tmp` + `os.replace`) sob um lock global.
- `transcript.md`: uma linha por segmento — `[00:01:23] **Outros:** texto`.
- `notes.md`, `ata.md`: Markdown livre.
- `mic.wav`, `system.wav`: PCM 16-bit no formato nativo do dispositivo, só durante a gravação.
  Apagados quando a transcrição termina com sucesso (~1,4 GB/h economizados); mantidos se ela falhar.

## Configuração
| Variável | Padrão |
|---|---|
| `DEEPSEEK_API_KEY` | — (obrigatória para resumo e conversa; lida do ambiente ou de `.env`) |
| `ATA_WHISPER` | `bin/vulkan/whisper-cli.exe` (build Vulkan local) |
| `ATA_THREADS` | `4` |
| `ATA_MODEL` | `models/ggml-large-v3-turbo-q5_0.bin` |
| `ATA_VAD` | `models/ggml-silero-v5.1.2.bin` |
| `ATA_PORT` | `8765` |
| `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` | — (opcionais; ligam o envio do resumo por e-mail) |

`ata/settings.py` (`env()`) lê variáveis do ambiente e, na falta, do `.env`.
