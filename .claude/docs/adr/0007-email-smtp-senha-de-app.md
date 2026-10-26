# ADR-0007: Resumo por e-mail via SMTP do Gmail com senha de app

**Date**: 2026-10-26
**Status**: accepted
**Deciders**: CEO, Claude

## Context
O CEO quer receber o resumo de cada reunião no próprio Gmail pessoal, automaticamente. Só
para ele mesmo; Drive e outros destinatários ficam fora por enquanto. O app é local, sem
servidor próprio e sem conta.

## Decision
`ata/mail.py` envia com `smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context())`
(stdlib; o contexto explícito é obrigatório porque o padrão do `smtplib` não verifica o
certificado do servidor — achado da revisão de segurança), autenticando com
`GMAIL_ADDRESS` + `GMAIL_APP_PASSWORD` do `.env`. Remetente e destinatário são o próprio
endereço. Corpo = resumo em Markdown (texto simples); anexo = `transcricao.md`. O envio
automático acontece uma vez por reunião (`emailed_at` no `meta.json`); reenvio só pelo botão.

## Alternatives Considered

### Gmail API com OAuth
- **Pros**: sem senha de app; escopo restrito a enviar.
- **Cons**: projeto no Google Cloud, tela de consentimento, fluxo OAuth local, refresh token
  para guardar, dependências do Google.
- **Why not**: muito mais peças para um único destinatário que é o próprio usuário.

### `mailto:` no navegador
- **Pros**: zero credencial.
- **Cons**: não é automático; limite de tamanho da URL; sem anexo.
- **Why not**: o CEO pediu envio automático.

## Consequences
### Positive
- Zero dependência nova; liga e desliga pelo `.env`.
- Falha de e-mail não afeta transcrição nem resumo (módulo ortogonal, status separado).
### Negative
- Senha de app dá acesso amplo à conta Gmail; fica só no `.env` local.
- Resumo e transcrição passam a existir também no Gmail (Google).
### Risks
- Google desativar senhas de app para contas pessoais: migrar para a Gmail API (OAuth).
- Senha vazada: revogar em Conta Google → Segurança → Senhas de app.
