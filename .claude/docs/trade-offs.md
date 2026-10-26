# Trade-offs e riscos

| Escolha | Ganho | Custo | Quando revisar |
|---|---|---|---|
| Whisper local em blocos de 30 s | Grátis, privado, offline | Texto aparece com ~30 s de atraso; não é palavra a palavra | Se o atraso atrapalhar: blocos menores (mais CPU/GPU) |
| whisper.cpp Vulkan na AMD (build local) | ~4× o CPU, chamada de vídeo fica lisa | Build local com cmake + Vulkan SDK + Build Tools; atualizar exige recompilar | Se o driver/GPU falhar: binário CPU oficial via `ATA_WHISPER` |
| DeepSeek para resumo e conversa | Barato, bom em pt/en | Título, notas, transcrição e conversa saem da máquina | Reunião sigilosa: marcar "Reunião sigilosa" antes de gravar e não usar resumo/conversa |
| Resumo no Gmail via senha de app | Automático, zero dependência, liga/desliga no `.env` | Senha de app dá acesso amplo à conta; resumo e transcrição também ficam no Google | Se o Google bloquear senhas de app ou se quiser escopo mínimo: Gmail API (OAuth) |
| Fontes do Google Fonts | Tipografia própria sem arquivos no repo | A página avisa o Google (IP) ao abrir | Se incomodar: servir as fontes localmente |
| Duas trilhas sem echo cancellation | Simples; "Eu vs. Outros" confiável de fone | Com caixa de som, a fala dos outros duplica em "Eu" | Se passar a usar caixa de som |
| Detecção pelo uso do microfone | Poucas linhas, sem código nativo | Navegador usando mic (ex.: um áudio no WhatsApp Web) também avisa | Se o falso positivo incomodar: checar título da janela |
| Aviso só com a página aberta | Sem bandeja nem auto-start | Esquecer a página aberta = sem aviso | Se esquecer com frequência: atalho na pasta Inicializar |
| Pasta por reunião, sem banco | Arquivos legíveis, backup trivial | Sem busca no app | Quando busca virar necessidade |
| Áudio apagado após a transcrição | Disco não cresce (só texto, poucos KB por reunião) | Não dá para retranscrever nem ouvir de novo | Se o Whisper errar demais: guardar em Opus (~15 MB/h) via ffmpeg |
| `http.server` da stdlib | Zero dependência | Sem extras (rotas, validação) | Nunca para este escopo |
| Parar só no botão | Previsível | Esquecer de parar grava por horas | Se acontecer: auto-stop quando o app solta o mic |
