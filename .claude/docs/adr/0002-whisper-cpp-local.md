# ADR-0002: Transcrição local com whisper.cpp (Vulkan)

**Date**: 2026-10-26
**Status**: accepted
**Deciders**: CEO, Claude

## Context
O another note-taking app transcreve na nuvem (Deepgram nova-3 via WebSocket). O CEO só aceita pagar a
DeepSeek, que não faz speech-to-text. A máquina tem uma AMD RX 5700 (sem CUDA),
i7-8700 e 16 GB de RAM.

## Decision
whisper.cpp (`whisper-cli`) chamado como subprocesso, backend Vulkan na GPU AMD, modelo
`ggml-large-v3-turbo`, idioma fixo por reunião (`-l pt|en`), em blocos de ~30 s.

## Alternatives Considered

### faster-whisper
- **Pros**: API Python, rápido.
- **Cons**: GPU só com CUDA (NVIDIA).
- **Why not**: na RX 5700 rodaria só em CPU.

### Deepgram / AssemblyAI
- **Pros**: tempo real, alta qualidade.
- **Cons**: pago por minuto.
- **Why not**: viola a restrição de custo.

### Detecção automática de idioma
- **Pros**: zero cliques.
- **Cons**: erra em blocos curtos ou silenciosos e alterna idioma no meio da reunião.
- **Why not**: um seletor por reunião é mais confiável.

## Medições (2026-10-26, i7-8700, build CPU+BLAS b5454, `large-v3-turbo-q5_0`, 8 threads)
- ~8,5 s de encoder por janela de 30 s com voz; carga do modelo 0,6 s.
- VAD Silero como porteiro (`whisper-vad-speech-segments`): janela só com ruído é descartada em < 1 s, sem texto inventado.
- O `--vad` embutido no `whisper-cli` foi descartado: desloca em até ~9 s o horário de falas que vêm depois de uma pausa.
- Subprocessos rodam em `BELOW_NORMAL_PRIORITY_CLASS` para a chamada de vídeo ter preferência no CPU.
- Qualidade em pt-BR: transcrição exata de nomes, prazos e horários num teste de 34 s.
- CPU dava conta, mas ocupava ~60% do tempo durante a reunião. O CEO pediu o mais liso possível na
  chamada de vídeo, então o whisper.cpp v1.9.5 foi compilado com `GGML_VULKAN=ON` (CMake + Vulkan SDK
  1.4.363 + VS 2022 Build Tools, instalados com aprovação do CEO).
- Vulkan na RX 5700: encoder 1,6 s por janela de 30 s, 34 s de fala em 5,2 s (≈4× o CPU), CPU quase livre.
- Whisper carimba a primeira frase em 0 s quando a janela abre em silêncio: o início da voz vindo do VAD
  é passado como `-ot`, mantendo horários absolutos.

## Consequences
### Positive
- Grátis, privado, offline.
### Negative
- Transcrição com atraso de ~30 s, não palavra a palavra.
### Risks
- Não há binário Vulkan oficial para Windows: o build é local (`bin/whisper-src`, gitignored), e o README
  documenta como refazê-lo. Plano B: o binário CPU+BLAS oficial (`ATA_WHISPER=bin/Release/whisper-cli.exe`).
