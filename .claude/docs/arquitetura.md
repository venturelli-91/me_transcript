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
      ├── enhance.py    urllib → DeepSeek → ata.md
      └── detect.py     winreg ConsentStore → app de reunião usando o mic?
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
3. `POST /api/stop` → `capture.stop()` → transcreve o resto → `enhance.generate()` →
   `ata.md` → `phase = done`.

## Contrato da API (JSON, 127.0.0.1 apenas)

| Método e rota | Corpo | Resposta |
|---|---|---|
| `GET /` | — | `web/index.html` |
| `GET /api/status` | — | `{phase, meeting_id, elapsed, levels:{mic,system}, segments:[...], detected, error}` |
| `GET /api/meetings` | — | `[{id, title, started_at, has_ata}]` |
| `GET /api/meetings/<id>` | — | `{id, title, lang, started_at, notes, transcript, ata}` |
| `POST /api/start` | `{title?, lang: "pt"\|"en"}` | `{id}` · `409` se já gravando |
| `POST /api/stop` | — | `{}` (processamento segue em background) |
| `PUT /api/meetings/<id>/notes` | `{notes}` | `{}` |
| `POST /api/meetings/<id>/ata` | — | `{}` (gera de novo em background) |

Segmento: `{"t": 83.2, "who": "Eu" | "Outros", "text": "..."}` (`t` em segundos desde o início).

## Formatos em disco
- `meta.json`: `{"title", "lang", "started_at", "ended_at"}` (ISO 8601 local).
- `transcript.md`: uma linha por segmento — `[00:01:23] **Outros:** texto`.
- `notes.md`, `ata.md`: Markdown livre.
- `mic.wav`, `system.wav`: PCM 16-bit no formato nativo do dispositivo.

## Configuração
| Variável | Padrão |
|---|---|
| `DEEPSEEK_API_KEY` | — (obrigatória para a ata; lida do ambiente ou de `.env`) |
| `ATA_WHISPER` | `bin/vulkan/whisper-cli.exe` (build Vulkan local) |
| `ATA_THREADS` | `4` |
| `ATA_MODEL` | `models/ggml-large-v3-turbo-q5_0.bin` |
| `ATA_VAD` | `models/ggml-silero-v5.1.2.bin` |
| `ATA_PORT` | `8765` |
