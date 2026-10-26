# ADR-0005: Two tracks — microphone and WASAPI loopback

**Date**: 2026-10-26
**Status**: accepted
**Deciders**: CEO, Claude

## Context
another note-taking app captures the microphone and system audio separately, which tells apart what was
said by the user and what was said by others. The CEO always wears headphones, so there is no
system echo in the microphone.

## Decision
PyAudioWPatch opens the default microphone and the WASAPI loopback of the default output device,
recording `mic.wav` and `system.wav` in the native format. Conversion to 16 kHz mono is left
to ffmpeg at transcription time.

## Alternatives Considered

### A single mixed track
- **Pros**: simpler.
- **Cons**: loses who spoke.
- **Why not**: "Me vs. Others" is essential to attribute decisions and tasks.

### A bot joining the meeting
- **Pros**: per-participant separation.
- **Cons**: intrusive, depends on each platform.
- **Why not**: anti-goal.

## Consequences
### Positive
- Works the same for Meet, Zoom and Teams.
### Negative
- Without headphones, other people's voices leak into "Me" (no echo cancellation).
### Risks
- Switching the output device mid-meeting interrupts the loopback. Accepted:
  restarting the recording fixes it.
