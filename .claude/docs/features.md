# Features

## F1 — Reuniões em pasta
Cada reunião é uma pasta `meetings/AAAA-MM-DD_HHMM/` com `meta.json`, `notes.md`,
`transcript.md`, `ata.md`, `mic.wav`, `system.wav`.

- [ ] Criar reunião gera a pasta e `meta.json` (`title`, `lang`, `started_at`).
- [ ] Listar reuniões em ordem decrescente de data.
- [ ] Abrir uma reunião antiga mostra notas, transcrição e ata.
- [ ] Duas reuniões no mesmo minuto não colidem (sufixo `-2`).

## F2 — Gravar e parar
- [ ] Botão **Gravar** inicia a captura; botão **Parar** encerra. Não há auto-stop.
- [ ] Título opcional e idioma (`pt` padrão, `en`) escolhidos antes de gravar.
- [ ] Indicador de tempo e de nível de áudio das duas trilhas enquanto grava.
- [ ] Só uma gravação por vez; tentar iniciar outra retorna erro claro.

## F3 — Duas trilhas de áudio
- [ ] `mic.wav` contém só o microfone; `system.wav` contém só o áudio do sistema
      (loopback do dispositivo de saída padrão).
- [ ] Funciona com Meet (navegador), Zoom e Teams sem configuração por app.

## F4 — Transcrição local
- [ ] A cada ~30 s, cada trilha nova é transcrita pelo whisper.cpp no idioma escolhido.
- [ ] Segmentos rotulados **Eu** / **Outros**, intercalados por tempo, aparecem na página
      durante a reunião.
- [ ] Ao parar, os blocos restantes são transcritos antes da ata.
- [ ] Trechos de silêncio não geram texto inventado ("Legendas pela comunidade…").

## F5 — Anotações
- [ ] Área de texto livre durante e depois da reunião, salva automaticamente em
      `notes.md` (sem botão salvar).
- [ ] Indicação discreta de "salvo".

## F6 — Resumo e conversa com a reunião (DeepSeek)
Decisão do CEO (2026-10-26): o app resume as ideias por tópico e a pessoa conversa com
ele para perguntar, citar ou reformular — no lugar de uma ata com seções fixas.

- [ ] Ao terminar a transcrição, gera `ata.md`: um `##` por tópico discutido, com as ideias,
      números e quem defendeu o quê, e no fim "Próximos passos" (responsável: tarefa, prazo).
- [ ] Anotações são opcionais; quando existem, os pontos delas ganham mais espaço.
- [ ] Escrito no idioma da reunião.
- [ ] Caixa de mensagem por reunião: pergunta específica recebe resposta curta com o
      horário `[hh:mm:ss]` dos trechos; pedido de mudança reescreve o resumo e diz o que mudou.
- [ ] Cada resposta do chat tem "Incluir no resumo".
- [ ] "Desfazer" volta o resumo à versão anterior (todas as versões ficam guardadas).
- [ ] Conversa salva em `chat.json`; ao reabrir a reunião, ela continua.
- [ ] Sem chave ou erro de rede: mensagem clara, transcrição e conversa preservadas.

## F7 — Aviso de reunião
- [ ] Com a página aberta, quando Zoom, Teams ou um navegador passa a usar o microfone,
      aparece um banner (e notificação do sistema, se permitida) com **Gravar**.
- [ ] Nunca inicia gravação sozinho.
- [ ] Não repete o aviso para a mesma sessão de microfone.
