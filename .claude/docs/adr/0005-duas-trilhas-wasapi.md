# ADR-0005: Duas trilhas — microfone e loopback WASAPI

**Date**: 2026-10-26
**Status**: accepted
**Deciders**: CEO, Claude

## Context
O another note-taking app captura microfone e áudio do sistema separados, o que permite saber o que foi
dito pelo usuário e o que foi dito pelos outros. O CEO usa sempre fone, então não há eco
do sistema no microfone.

## Decision
PyAudioWPatch abre o microfone padrão e o loopback WASAPI do dispositivo de saída padrão,
gravando `mic.wav` e `system.wav` no formato nativo. A conversão para 16 kHz mono fica
com o ffmpeg na hora de transcrever.

## Alternatives Considered

### Uma trilha mixada
- **Pros**: mais simples.
- **Cons**: perde quem falou.
- **Why not**: "Eu vs. Outros" é essencial para atribuir decisões e tarefas.

### Bot entrando na reunião
- **Pros**: separação por participante.
- **Cons**: invasivo, depende de cada plataforma.
- **Why not**: anti-objetivo.

## Consequences
### Positive
- Funciona igual para Meet, Zoom e Teams.
### Negative
- Sem fone, a voz dos outros vaza para "Eu" (sem echo cancellation).
### Risks
- Trocar o dispositivo de saída no meio da reunião interrompe o loopback. Aceito:
  reiniciar a gravação resolve.
