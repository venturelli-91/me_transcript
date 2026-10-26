# Trade-offs and risks

| Choice | Gain | Cost | When to revisit |
|---|---|---|---|
| Local Whisper in 30 s chunks | Free, private, offline | Text appears with a ~30 s delay; not word by word | If the delay gets in the way: smaller chunks (more CPU/GPU) |
| whisper.cpp Vulkan on AMD (local build) | ~4× faster than CPU, video call stays smooth | Local build with cmake + Vulkan SDK + Build Tools; updating requires a rebuild | If the driver/GPU fails: official CPU binary via `ATA_WHISPER` |
| DeepSeek for summary and chat | Cheap, good in pt/en | Title, notes, transcript and chat leave the machine | Sensitive meeting: check "Private meeting" before recording and don't use summary/chat |
| Summary to Gmail via app password | Automatic, zero dependencies, on/off in `.env` | An app password grants broad account access; summary and transcript also live at Google | If Google blocks app passwords or minimal scope is wanted: Gmail API (OAuth) |
| Google Fonts | Custom typography without font files in the repo | The page notifies Google (IP) when opened | If it bothers: serve the fonts locally |
| Two tracks without echo cancellation | Simple; "Me vs. Others" is reliable with headphones | With speakers, other people's speech is duplicated in "Me" | If speakers start being used |
| Detection via microphone usage | Few lines, no native code | A browser using the mic (e.g. a voice message on WhatsApp Web) also triggers the alert | If the false positive bothers: check the window title |
| Alert only with the page open | No tray icon or auto-start | Forgetting to keep the page open = no alert | If it's forgotten often: shortcut in the Startup folder |
| Folder per meeting, no database | Readable files, trivial backup | No search in the app | When search becomes a need |
| Audio deleted after transcription | Disk doesn't grow (text only, a few KB per meeting) | Can't re-transcribe or listen again | If Whisper makes too many mistakes: keep Opus (~15 MB/h) via ffmpeg |
| stdlib `http.server` | Zero dependencies | No extras (routing, validation) | Never, for this scope |
| Stop only via the button | Predictable | Forgetting to stop records for hours | If it happens: auto-stop when the app releases the mic |
