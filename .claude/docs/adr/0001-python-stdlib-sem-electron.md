# ADR-0001: Python stdlib + página local em vez de Electron

**Date**: 2026-10-26
**Status**: accepted
**Deciders**: CEO, Claude

## Context
O another note-taking app é um app Electron (~250 MB) com módulos nativos em Rust e C++. O CEO pediu
algo simples, sem overengineering, que ele mesmo consiga manter. Áudio do Windows e
Whisper têm o melhor suporte em Python.

## Decision
Um processo Python usando a stdlib (`http.server`, `winreg`, `urllib`, `wave`,
`threading`) servindo uma única página HTML em `127.0.0.1`.

## Alternatives Considered

### Electron
- **Pros**: mesma base do another note-taking app; `getDisplayMedia` dá loopback de graça.
- **Cons**: pesado, build e empacotamento complexos.
- **Why not**: o CEO vetou explicitamente.

### Tauri
- **Pros**: app leve e nativo.
- **Cons**: exige Rust e toolchain de build.
- **Why not**: complexidade de build sem ganho para um usuário só.

### Next.js local
- **Pros**: stack habitual do CEO.
- **Cons**: captura de áudio nativa e subprocessos ficam piores em Node; build desnecessário.
- **Why not**: a parte difícil (áudio/whisper) é melhor em Python.

## Consequences
### Positive
- Uma dependência Python (PyAudioWPatch); roda com `python -m ata.server`.
### Negative
- A página precisa estar aberta para ver o aviso de reunião.
### Risks
- Exposição na rede: mitigado escutando só em `127.0.0.1`.
