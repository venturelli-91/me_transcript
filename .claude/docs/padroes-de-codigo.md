# Padrões de código

## Princípios
- **Ladder do Ponytail**: precisa existir? → já existe aqui? → stdlib? → recurso nativo?
  → dependência já instalada? → uma linha? → só então o mínimo.
- Sem abstração especulativa: nada de interface com uma implementação, factory, plugin
  ou config para valor que não muda.
- Arquivos poucos e com responsabilidade clara (ver `arquitetura.md`).

## Python
- Python 3.13, PEP 8, type hints em funções públicas, `pathlib.Path` para caminhos.
- Funções pequenas; módulo expõe funções simples, classe só quando há estado real
  (ex.: gravação em andamento).
- Sem comentário que explica O QUE o código faz. Comentário só para PORQUÊ não óbvio.
- Atalho deliberado leva `# ponytail:` com o teto e o caminho de upgrade.
- Logs com `logging`, nunca `print` em código de produto. Nunca logar a chave da API.

## Erros e validação
- Validar na **fronteira de confiança**: corpo HTTP, resposta da DeepSeek, saída de
  subprocesso (ffmpeg, whisper-cli), registro do Windows.
- Dentro do código, confiar no invariante — sem try/except para estado impossível.
- Erro que impede a ata nunca apaga notas nem transcrição; vai para `Session.error` e
  aparece na UI.

## Frontend
- Um `index.html` com CSS e JS inline, sem framework e sem build.
- `fetch` + polling; sem WebSocket.
- Acessibilidade básica: rótulos, foco visível, contraste, `aria-live` no status.

## Testes
- `unittest` da stdlib, em `tests/test_<modulo>.py`. Rodar: `python -m unittest`.
- Testar lógica pura (store, merge Eu/Outros, parser do registro, montagem do prompt).
  Áudio e rede são validados manualmente/QA, não com mocks elaborados.

## Commits
- Um commit por ticket do `backlog.md`, atômico, em inglês:
  `DEV-0004: Add dual-track audio capture`.
- Rodapé `Co-Authored-By` quando gerado com Claude.
- Nunca commitar `meetings/`, `bin/`, `models/`, `.env`.

## Processo (softhouse)
Por ticket: dev do papel certo → `code-reviewer` (+ `ponytail:ponytail-review`) →
`qa-automation` → commit. Ninguém revisa a própria entrega.
