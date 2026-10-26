# ADR-0004: Pasta de arquivos por reunião em vez de banco

**Date**: 2026-10-26
**Status**: accepted
**Deciders**: Claude

## Context
O another note-taking app usa SQLite criptografado com FTS5, tabelas de documentos/painéis e sync em
nuvem. Para um usuário só, com dezenas de reuniões por mês, o que importa é poder abrir,
ler e copiar as atas.

## Decision
`meetings/AAAA-MM-DD_HHMM/` com `meta.json`, `notes.md`, `transcript.md`, `ata.md` e os
WAVs. Listar = listar diretórios.

## Alternatives Considered

### SQLite
- **Pros**: busca e consultas.
- **Cons**: schema, migrações, arquivos ilegíveis fora do app.
- **Why not**: busca está fora do escopo; o sistema de arquivos já resolve.

## Consequences
### Positive
- Atas legíveis no Explorer, Obsidian ou VS Code; backup é copiar a pasta.
### Negative
- Sem busca no app.
### Risks
- Com milhares de reuniões a listagem fica lenta. Upgrade: índice único em JSON.
