# ADR-0003: DeepSeek as the only paid service

**Date**: 2026-10-26
**Status**: accepted
**Deciders**: CEO

## Context
another note-taking app generates enhanced notes on its own server, with prompts that aren't in the
app. We need an LLM to turn notes + transcript into a meeting summary. The CEO can only
pay for DeepSeek.

## Decision
Call `https://api.deepseek.com/chat/completions` (OpenAI format, model
`deepseek-chat`) with the stdlib `urllib`, no SDK. The prompt lives in `ata/prompt.md`,
editable by the user.

## Alternatives Considered

### Local LLM (Ollama)
- **Pros**: free and offline.
- **Cons**: 8 GB of VRAM on the AMD limits quality; competes with Whisper for the GPU.
- **Why not**: summary quality is the product.

### `openai` SDK
- **Pros**: less code.
- **Cons**: a new dependency for a single POST.
- **Why not**: `urllib` does it in a few lines.

## Consequences
### Positive
- Low cost per meeting; the prompt is ours and evolves.
### Negative
- Notes and transcript leave the machine and go to DeepSeek.
### Risks
- Key leak: read from the environment/gitignored `.env`, never logged.
- Sensitive meeting data: a conscious user decision, recorded in `trade-offs.md`.
