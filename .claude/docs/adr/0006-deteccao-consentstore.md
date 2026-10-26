# ADR-0006: Detecção de reunião via ConsentStore do Windows

**Date**: 2026-10-26
**Status**: accepted
**Deciders**: Claude

## Context
O another note-taking app usa um módulo nativo em Rust (`MicActivityTrackerV2`) e um executável de UI
Automation para detectar reuniões. O Windows já registra quais apps estão usando o
microfone em
`HKCU\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone`.

## Decision
`detect.py` lê essa chave com `winreg` a cada poll de `/api/status` (1 s), fora do lock da sessão. Entradas com `LastUsedTimeStop == 0`
estão com o mic aberto; se o executável for Zoom, Teams ou um navegador, a página avisa.

## Alternatives Considered

### Lista de processos / títulos de janela
- **Pros**: identifica o Meet pelo título da aba.
- **Cons**: processo aberto não é reunião; títulos variam.
- **Why not**: uso do microfone é o sinal mais fiel de "reunião começou".

### UI Automation (como o another note-taking app)
- **Pros**: precisão alta.
- **Cons**: código nativo frágil por plataforma.
- **Why not**: complexidade desproporcional.

## Consequences
### Positive
- Zero dependências, poucas linhas.
### Negative
- Navegador usando o microfone não significa necessariamente Meet: falso positivo
  aceitável, porque é só um aviso.
### Risks
- O formato da chave mudar numa atualização do Windows; o teste do parser denuncia.
