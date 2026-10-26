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

## Consequences
### Positive
- Grátis, privado, offline.
### Negative
- Transcrição com atraso de ~30 s, não palavra a palavra.
### Risks
- Não haver binário Vulkan pronto: compilar exige cmake + Vulkan SDK + VS Build Tools
  (aprovação do CEO). Plano B: build CPU com modelo `small`/`medium`.
