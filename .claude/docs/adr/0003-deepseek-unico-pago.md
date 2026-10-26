# ADR-0003: DeepSeek como único serviço pago

**Date**: 2026-10-26
**Status**: accepted
**Deciders**: CEO

## Context
O another note-taking app gera as notas melhoradas no próprio servidor, com prompts que não estão no
app. Precisamos de um LLM para transformar notas + transcrição em ata. O CEO só pode
pagar a DeepSeek.

## Decision
Chamar `https://api.deepseek.com/chat/completions` (formato OpenAI, modelo
`deepseek-chat`) com `urllib` da stdlib, sem SDK. O prompt fica em `ata/prompt.md`,
editável pelo usuário.

## Alternatives Considered

### LLM local (Ollama)
- **Pros**: grátis e offline.
- **Cons**: 8 GB de VRAM na AMD limita a qualidade; disputa a GPU com o Whisper.
- **Why not**: a qualidade da ata é o produto.

### SDK `openai`
- **Pros**: menos código.
- **Cons**: nova dependência para um único POST.
- **Why not**: `urllib` resolve em poucas linhas.

## Consequences
### Positive
- Custo baixo por reunião; o prompt é nosso e evolui.
### Negative
- Notas e transcrição saem da máquina para a DeepSeek.
### Risks
- Vazamento da chave: lida de ambiente/`.env` gitignored, nunca logada.
- Dados sensíveis de reunião: decisão consciente do usuário, registrada em `trade-offs.md`.
