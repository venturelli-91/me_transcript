# Privacidade

O MeTranscript é uma ferramenta pessoal que roda no seu próprio computador. Esta página diz o que ele guarda, o que
ele envia para fora e o que é responsabilidade sua. O README traz as mesmas informações de forma resumida.

## O que ele guarda, e onde

Tudo fica em arquivos simples, na pasta do projeto, no seu computador:

| Onde | O quê |
|---|---|
| `meetings/<data>/` | O áudio (comprimido, veja abaixo), a transcrição, as suas notas, o resumo, o chat e o `meta.json` (título, idioma, horários e quando você confirmou que avisou os participantes) |
| `.env` | As suas chaves (DeepSeek e a chave secreta do seu cliente Google) em texto simples |
| `google-accounts.json` | As contas Google que você conectou: o endereço em texto simples e o login criptografado, de modo que só o seu usuário do Windows consegue lê-lo |
| `sensitive-terms.txt` | Os nomes que você pediu para ocultar |

Nada é enviado para lugar nenhum automaticamente, e o app não tem análise de uso nem telemetria. A página que ele mostra só
fala com `127.0.0.1`.

## O que ele envia para fora

| Para | O quê | Quando |
|---|---|---|
| DeepSeek | A transcrição, as suas notas e o chat, depois que contatos, valores, documentos, chaves e os seus termos protegidos são trocados por códigos | Só quando um resumo é gerado ou você usa o chat |
| Gmail (o seu próprio endereço) | O resumo, com os nomes reais. A transcrição não é enviada | Só se você entrou com o Google |
| Google Agenda | O título, o horário, o link e a sua resposta dos eventos das próximas 24 horas, de cada conta que você conectou. Somente leitura | Só se você entrou com o Google |

O áudio nunca é enviado para lugar nenhum: ele é transcrito no seu computador. A máscara de proteção tem limites (ela só
oculta o que combina com os seus padrões ou com a sua lista), então não conte com ela para segredos que ela não reconhece.

## Por quanto tempo ele guarda as coisas

- O áudio comprimido fica **30 dias**, para você poder transcrever de novo, e depois é apagado. Em Configurações → **Retenção** você pode
  mudar o número de dias, ou colocar **0** para apagar o áudio assim que a transcrição ficar pronta.
- As reuniões inteiras (notas, transcrição, resumo e chat) ficam até você apagá-las, a menos que você defina
  **Excluir reuniões inteiras após (dias)** em Configurações. A verificação roda quando o app inicia e a cada seis horas.
- Você pode apagar uma reunião a qualquer momento pela página dela. Apagar a pasta do projeto remove tudo.

## O consentimento é responsabilidade sua

O MeTranscript não usa bot, e as outras pessoas da chamada não são avisadas pelo programa de que estão sendo
gravadas. Gravar uma conversa sem o consentimento das pessoas é restrito ou ilegal em muitos lugares.

Para ajudar você a lembrar, o app:

- pede que você confirme **"Avisei os participantes de que esta reunião está sendo gravada"** antes de toda gravação,
  e guarda o horário dessa confirmação no `meta.json` da reunião;
- oferece o botão **Copiar um aviso de gravação**, com uma mensagem curta em dois idiomas para colar no chat da reunião.

Isso é um lembrete e um registro, não uma proteção jurídica: a caixa só diz que você avisou. As regras mudam
de país para país e de estado para estado, então confira as que valem para você. Isto não é aconselhamento jurídico.

## Os seus dados

Como tudo é arquivo, você pode abrir, copiar, mover ou apagar qualquer coisa por conta própria. Para revogar o acesso às
integrações opcionais, use **Desconectar** em Configurações (isso também avisa o Google para cancelar o login) ou remova o MeTranscript em
myaccount.google.com/permissions.
