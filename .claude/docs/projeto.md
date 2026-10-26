# Projeto

## Por quê
O CEO usa o another note-taking app diariamente para anotar reuniões. O another note-taking app só aceita e-mail
corporativo, e o bloqueio é feito no servidor deles — não há como contornar. A solução é
ter uma ferramenta própria, pessoal, sem conta e sem dependência de terceiros além do LLM.

## Usuário
Uma pessoa: o CEO, no próprio desktop Windows, sempre de fone, em reuniões no Google Meet,
Zoom e Microsoft Teams, em português ou inglês.

## O que é
Um programa local (Python) com uma página no navegador (`127.0.0.1:8765`):

1. Avisa quando um app de reunião começa a usar o microfone — ou você inicia no botão.
2. Grava duas trilhas: **Eu** (microfone) e **Outros** (áudio do sistema).
3. Transcreve em blocos durante a reunião, localmente, com whisper.cpp.
4. Você escreve anotações curtas enquanto conversa.
5. Ao parar, a DeepSeek usa suas anotações como esqueleto e a transcrição como fonte para
   gerar a **ata**.

## Objetivos
- Substituir o another note-taking app no uso diário do CEO para Meet, Zoom e Teams.
- Custo recorrente: só a API da DeepSeek.
- Tudo armazenado localmente, em Markdown legível fora do app.

## Não-objetivos (por ora)
Chat com reuniões, múltiplos templates, agenda, compartilhamento, sync em nuvem,
identificação de cada participante, transcrição palavra a palavra ao vivo, busca, login,
instalador.

## Anti-objetivos (seria fracasso mesmo funcionando)
- Pagar qualquer serviço além da DeepSeek.
- Virar um projeto pesado (Electron, framework web, banco de dados).
- Entrar na reunião como bot.
- Ser uma cópia do another note-taking app — nome, design e fluxo são próprios.
- Gravar sem o usuário mandar.
