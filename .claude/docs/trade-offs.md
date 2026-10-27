# Trade-offs and risks

| Choice | Gain | Cost | When to revisit |
|---|---|---|---|
| A lost window is marked, not retried | The rest of the meeting is kept and the summary says the part is missing | That stretch has no text until you press Re-transcribe | If it happens often: retry the window once before giving up |
| Local Whisper once, after the call | Free, private, offline; nothing heavy runs during the call; the GPU is free for the batch | Wait after you stop (a progress bar shows it); no text during the meeting | If the delay gets in the way: smaller chunks (more CPU/GPU) |
| whisper.cpp Vulkan on AMD (local build) | ~4× faster than CPU, video call stays smooth | Local build with cmake + Vulkan SDK + Build Tools; updating requires a rebuild | If the driver/GPU fails: official CPU binary via `ATA_WHISPER` |
| DeepSeek for summary and chat | Cheap, good in pt/en | Title, notes, transcript and chat leave the machine | Sensitive meeting: check "Private meeting" before recording and don't use summary/chat |
| Summary to Gmail via app password | Automatic, zero dependencies, on/off in `.env` | An app password grants broad account access; summary and transcript also live at Google | If Google blocks app passwords or minimal scope is wanted: Gmail API (OAuth) |
| Calendar via secret iCal address | No OAuth, read-only, one line in `.env` | Changes show up within ~5 min; the address grants read access to the whole calendar | If instant updates matter: Google Calendar API (OAuth) |
| Background mode without tray icon | No extra dependencies | Quitting is done from the page | If it gets in the way: `pystray` tray icon |
| Consent checkbox and copyable notice | A clear reminder before every recording, a record of when you confirmed, and a message ready to paste in the chat | It is an attestation, not enforcement: nothing tells the other participants and nothing checks the claim; the notice must be pasted by hand | If it is needed: post to the call chat automatically (per-app integration) or play a spoken notice |
| Retention checked at start and every 6 h | Old audio and, if configured, old meetings go away even when the app runs for weeks | A meeting may live up to 6 h past its limit; deletion is permanent | If exact timing matters: check per request or on a timer closer to the cutoff |
| Two tracks, echo removed by text similarity | "Me vs. Others" works with speakers too: a "Me" line of 4+ words whose words are 70%+ found in the "Others" lines within 5 s is dropped (also when the echo is split into fragments) | Not real echo cancellation; a real "Me" line that repeats Others almost verbatim is lost; short echoes survive; an echo whose original is in the previous 30 s window is not caught | If it drops real speech or misses echo: tune `ECHO_SHARE`/`ECHO_GAP` or add acoustic cancellation |
| Detection via microphone usage + window title | Few lines, no native code; a browser only alerts when one of its own windows has a meeting word (whole word) in the title | A meeting in a background browser tab is not detected (only the active tab title is visible); native Zoom/Teams are unaffected | If it gets missed often: add UI Automation to read every tab |
| Alert only with the page open | No tray icon or auto-start | Forgetting to keep the page open = no alert | If it's forgotten often: shortcut in the Startup folder |
| Folder per meeting, no database | Readable files, trivial backup | No search in the app | When search becomes a need |
| Audio deleted after transcription | Disk doesn't grow (text only, a few KB per meeting) | Can't re-transcribe or listen again | If Whisper makes too many mistakes: keep Opus (~15 MB/h) via ffmpeg |
| stdlib `http.server` | Zero dependencies | No extras (routing, validation) | Never, for this scope |
| Stop only via the button | Predictable | Forgetting to stop records for hours | If it happens: auto-stop when the app releases the mic |
