# Ata

Notas de reunião pessoais para Windows. Grava Meet, Zoom e Teams sem bot, transcreve no seu
computador (whisper.cpp na GPU) e, no fim, a DeepSeek resume as ideias por tópico. Depois você
conversa com a reunião: pergunta algo específico, pede para incluir no resumo ou reformular.

Só a API da DeepSeek é paga. Áudio, transcrição e resumos ficam em `meetings/`, em Markdown.

## Requisitos

- Windows 10/11, sempre de fone nas reuniões (o app não remove eco).
- Python 3.13 e ffmpeg no `PATH` (`winget install Gyan.FFmpeg`).
- Uma chave da [DeepSeek](https://platform.deepseek.com/).
- Para a GPU AMD/Intel/NVIDIA via Vulkan: CMake, Vulkan SDK e VS 2022 Build Tools (C++).

## Instalação

```powershell
python -m pip install -r requirements.txt
```

### Chave da DeepSeek

Crie `.env` na raiz (já está no `.gitignore`):

```
DEEPSEEK_API_KEY=sk-...
```

### Modelos (pasta `models/`)

```powershell
curl.exe -L -o models/ggml-large-v3-turbo-q5_0.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin
curl.exe -L -o models/ggml-silero-v5.1.2.bin https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin
```

### whisper.cpp com Vulkan (recomendado, deixa a chamada de vídeo lisa)

Não há binário Vulkan oficial para Windows, então compile uma vez:

```powershell
winget install Kitware.CMake KhronosGroup.VulkanSDK
winget install Microsoft.VisualStudio.2022.BuildTools --override "--quiet --wait --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
# abra um terminal novo para carregar VULKAN_SDK
git clone --depth 1 --branch v1.9.5 https://github.com/ggml-org/whisper.cpp bin/whisper-src
cmake -S bin/whisper-src -B bin/whisper-src/build -G "Visual Studio 17 2022" -A x64 -DGGML_VULKAN=ON -DWHISPER_SDL2=OFF
cmake --build bin/whisper-src/build --config Release -j 10 --target whisper-cli whisper-vad-speech-segments
mkdir bin/vulkan; copy bin/whisper-src/build/bin/Release/*.exe, bin/whisper-src/build/bin/Release/*.dll bin/vulkan/
```

Sem GPU: baixe `whisper-blas-bin-x64.zip` da
[release b5454](https://github.com/ggml-org/whisper.cpp/releases), extraia em `bin/` e use
`$env:ATA_WHISPER = "bin/Release/whisper-cli.exe"`. Funciona, mas usa bem mais CPU.

## Uso

```powershell
python -m ata.server
```

Abra http://127.0.0.1:8765 e deixe a aba aberta.

1. Quando o Zoom, o Teams ou o navegador começar a usar o microfone, aparece o aviso
   "Gravar esta reunião". Ou clique no botão de gravar.
2. Escolha o idioma (Português ou English). Marque **Reunião sigilosa** para não enviar nada à IA.
3. Anote o que quiser durante a reunião (opcional). A transcrição aparece a cada ~30 s.
4. Clique no quadrado para parar. O resumo por tópico fica pronto em segundos.
5. Converse no painel ao lado: perguntas, "Incluir no resumo", ajustes e **Desfazer**.

Cada reunião fica em `meetings/AAAA-MM-DD_HHMM/` (`notes.md`, `transcript.md`, `ata.md`,
`chat.json`). O áudio (`mic.wav`, `system.wav`) só existe durante a gravação e é apagado quando a
transcrição termina; se ela falhar, o áudio fica na pasta.

## Configuração

| Variável | Padrão |
|---|---|
| `DEEPSEEK_API_KEY` | — |
| `ATA_WHISPER` | `bin/vulkan/whisper-cli.exe` |
| `ATA_MODEL` | `models/ggml-large-v3-turbo-q5_0.bin` |
| `ATA_VAD` | `models/ggml-silero-v5.1.2.bin` |
| `ATA_THREADS` | `4` |
| `ATA_PORT` | `8765` |

## Desenvolvimento

```powershell
python -m unittest
```

Documentação do projeto, decisões (ADRs), backlog e padrões em [`.claude/docs/`](.claude/docs/README.md).
