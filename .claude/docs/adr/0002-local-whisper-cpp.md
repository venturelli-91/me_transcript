# ADR-0002: Local transcription with whisper.cpp (Vulkan)

**Date**: 2026-10-26
**Status**: accepted
**Deciders**: CEO, Claude

## Context
another note-taking app transcribes in the cloud (Deepgram nova-3 via WebSocket). The CEO will only pay for
DeepSeek, which doesn't do speech-to-text. The machine has an AMD RX 5700 (no CUDA),
an i7-8700 and 16 GB of RAM.

## Decision
whisper.cpp (`whisper-cli`) called as a subprocess, Vulkan backend on the AMD GPU, model
`ggml-large-v3-turbo`, fixed language per meeting (`-l pt|en`), in ~30 s chunks.

## Alternatives Considered

### faster-whisper
- **Pros**: Python API, fast.
- **Cons**: GPU only with CUDA (NVIDIA).
- **Why not**: on the RX 5700 it would run on CPU only.

### Deepgram / AssemblyAI
- **Pros**: real time, high quality.
- **Cons**: paid per minute.
- **Why not**: violates the cost constraint.

### Automatic language detection
- **Pros**: zero clicks.
- **Cons**: fails on short or silent chunks and switches language mid-meeting.
- **Why not**: a per-meeting selector is more reliable.

## Measurements (2026-10-26, i7-8700, CPU+BLAS build b5454, `large-v3-turbo-q5_0`, 8 threads)
- ~8.5 s of encoder time per 30 s window with speech; model load 0.6 s.
- Silero VAD as a gatekeeper (`whisper-vad-speech-segments`): a noise-only window is discarded in < 1 s, with no made-up text.
- The `--vad` built into `whisper-cli` was rejected: it shifts the timestamp of speech that follows a pause by up to ~9 s.
- Subprocesses run at `BELOW_NORMAL_PRIORITY_CLASS` so the video call gets CPU priority.
- pt-BR quality: exact transcription of names, deadlines and times in a 34 s test.
- The CPU could handle it, but was busy ~60% of the time during the meeting. The CEO asked for the smoothest
  possible video call, so whisper.cpp v1.9.5 was built with `GGML_VULKAN=ON` (CMake + Vulkan SDK
  1.4.363 + VS 2022 Build Tools, installed with CEO approval).
- Vulkan on the RX 5700: encoder 1.6 s per 30 s window, 34 s of speech in 5.2 s (≈4× the CPU), CPU almost idle.
- Whisper stamps the first sentence at 0 s when the window opens in silence: the speech start from the VAD
  is passed as `-ot`, keeping timestamps absolute.

## Consequences
### Positive
- Free, private, offline.
### Negative
- Transcription with a ~30 s delay, not word by word. (Superseded by DEV-0059: the audio is now transcribed once, after the call, in the same windows.)
### Risks
- There is no official Vulkan binary for Windows: the build is local (`bin/whisper-src`, gitignored), and the README
  documents how to redo it. Plan B: the official CPU+BLAS binary (`ATA_WHISPER=bin/Release/whisper-cli.exe`).
