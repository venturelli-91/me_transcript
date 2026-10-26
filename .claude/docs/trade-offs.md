# Trade-offs e riscos

| Escolha | Ganho | Custo | Quando revisar |
|---|---|---|---|
| Whisper local em blocos de 30 s | Grátis, privado, offline | Texto aparece com ~30 s de atraso; não é palavra a palavra | Se o atraso atrapalhar: blocos menores (mais CPU/GPU) |
| whisper.cpp Vulkan na AMD (build local) | ~4× o CPU, chamada de vídeo fica lisa | Build local com cmake + Vulkan SDK + Build Tools; atualizar exige recompilar | Se o driver/GPU falhar: binário CPU oficial via `ATA_WHISPER` |
| DeepSeek para a ata | Barato, bom em pt/en | Notas e transcrição saem da máquina | Reunião sigilosa: não gerar ata (a transcrição continua local) |
| Duas trilhas sem echo cancellation | Simples; "Eu vs. Outros" confiável de fone | Com caixa de som, a fala dos outros duplica em "Eu" | Se passar a usar caixa de som |
| Detecção pelo uso do microfone | Poucas linhas, sem código nativo | Navegador usando mic (ex.: um áudio no WhatsApp Web) também avisa | Se o falso positivo incomodar: checar título da janela |
| Aviso só com a página aberta | Sem bandeja nem auto-start | Esquecer a página aberta = sem aviso | Se esquecer com frequência: atalho na pasta Inicializar |
| Pasta por reunião, sem banco | Arquivos legíveis, backup trivial | Sem busca no app | Quando busca virar necessidade |
| WAV guardado | Permite retranscrever | ~0,7 GB/h por trilha (48 kHz estéreo), ~1,4 GB/h por reunião | Apagar WAV após ata, ou converter para Opus |
| `http.server` da stdlib | Zero dependência | Sem extras (rotas, validação) | Nunca para este escopo |
| Parar só no botão | Previsível | Esquecer de parar grava por horas | Se acontecer: auto-stop quando o app solta o mic |
