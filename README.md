# MeTranscript

Personal meeting notes for Windows. Records Meet, Zoom and Teams without a bot, transcribes on your
computer (whisper.cpp on the GPU) and, at the end, DeepSeek summarizes the ideas by topic. Then you
chat with the meeting: ask something specific, add something to the summary or rephrase it.

Only the DeepSeek API is paid. Audio, transcripts and summaries stay in `meetings/`, in Markdown.

## Requirements

- Windows 10/11, always wearing headphones in meetings (the app doesn't remove echo).
- Python 3.13 and ffmpeg on the `PATH` (`winget install Gyan.FFmpeg`).
- A [DeepSeek](https://platform.deepseek.com/) API key.
- For an AMD/Intel/NVIDIA GPU via Vulkan: CMake, Vulkan SDK and VS 2022 Build Tools (C++).

## Installation

```powershell
python -m pip install -r requirements.txt
```

### DeepSeek key

Create `.env` at the root (it's already in `.gitignore`):

```
DEEPSEEK_API_KEY=sk-...
```

### Summary in your Gmail (optional)

1. Turn on 2-Step Verification in your Google Account.
2. Create an app password at https://myaccount.google.com/apppasswords (name: "MeTranscript").
3. Add to `.env`:

```
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

Each new summary arrives in your inbox (body = summary, attachment = transcript). Private meetings
are never sent. To turn it off, delete both lines; to revoke access, remove the app password
in your Google Account.

### Calendar reminders (optional)

MeTranscript can remind you 30 and 2 minutes before every meeting in your Google Calendar that has a
Meet, Zoom or Teams link; the 2-minute reminder has a **Record** button.

1. In Google Calendar, open **Settings → your calendar → Integrate calendar**.
2. Copy **Secret address in iCal format** and add it to `.env` (comma-separate several calendars):

```
GOOGLE_CALENDAR_ICS=https://calendar.google.com/calendar/ical/.../basic.ics
```

Reminders only fire while MeTranscript is running: turn on **Run in background and start with
Windows** in the sidebar (and use **Quit MeTranscript** to stop it). Treat the secret address like a
password; if it leaks, reset it in the same Google Calendar screen.

### Models (`models/` folder)

```powershell
curl.exe -L -o models/ggml-large-v3-turbo-q5_0.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin
curl.exe -L -o models/ggml-silero-v5.1.2.bin https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin
```

### whisper.cpp with Vulkan (recommended, keeps the video call smooth)

There's no official Vulkan binary for Windows, so build it once:

```powershell
winget install Kitware.CMake KhronosGroup.VulkanSDK
winget install Microsoft.VisualStudio.2022.BuildTools --override "--quiet --wait --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
# open a new terminal to load VULKAN_SDK
git clone --depth 1 --branch v1.9.5 https://github.com/ggml-org/whisper.cpp bin/whisper-src
cmake -S bin/whisper-src -B bin/whisper-src/build -G "Visual Studio 17 2022" -A x64 -DGGML_VULKAN=ON -DWHISPER_SDL2=OFF
cmake --build bin/whisper-src/build --config Release -j 10 --target whisper-cli whisper-vad-speech-segments
mkdir bin/vulkan; copy bin/whisper-src/build/bin/Release/*.exe, bin/whisper-src/build/bin/Release/*.dll bin/vulkan/
```

No GPU: download `whisper-blas-bin-x64.zip` from
[release b5454](https://github.com/ggml-org/whisper.cpp/releases), extract it into `bin/` and use
`$env:ATA_WHISPER = "bin/Release/whisper-cli.exe"`. It works, but uses much more CPU.

## Usage

```powershell
python -m metranscript.server
```

Open http://127.0.0.1:8765 and keep the tab open.

1. When Zoom, Teams or the browser starts using the microphone, the "Record this meeting" alert
   appears. Or click the record button.
2. Choose the language (Portuguese or English). Check **Private meeting: don't send to AI or email**
   to keep it away from DeepSeek and Gmail.
3. Take notes during the meeting if you like (optional). The transcript appears every ~30 s.
4. Click the square to stop. The topic summary is ready in seconds and, if Gmail is
   configured, arrives in your inbox.
5. Chat in the side panel: questions, "Add to summary", tweaks and **Undo**.

Each meeting lives in `meetings/YYYY-MM-DD_HHMM/` (`notes.md`, `transcript.md`, `summary.md`,
`chat.json`). The audio (`mic.wav`, `system.wav`) only exists during recording and is deleted when
transcription finishes; if it fails, the audio stays in the folder.

## Configuration

| Variable | Default |
|---|---|
| `DEEPSEEK_API_KEY` | — |
| `ATA_WHISPER` | `bin/vulkan/whisper-cli.exe` |
| `ATA_MODEL` | `models/ggml-large-v3-turbo-q5_0.bin` |
| `ATA_VAD` | `models/ggml-silero-v5.1.2.bin` |
| `ATA_THREADS` | `4` |
| `ATA_PORT` | `8765` |
| `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` | — (enables sending the summary by email) |

## Development

```powershell
python -m unittest
```

Project documentation, decisions (ADRs), backlog and standards in [`.claude/docs/`](.claude/docs/README.md).
