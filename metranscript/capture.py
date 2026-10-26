import logging
import queue
import threading
import time
import wave
from array import array
from pathlib import Path

import pyaudiowpatch as pyaudio

PAD_AFTER = 0.2
log = logging.getLogger("metranscript")


class Track:
    def __init__(self, path: Path, rate: int, channels: int) -> None:
        self.rate, self.channels = rate, channels
        self.frames = 0
        self.level = 0.0
        self.lock = threading.Lock()
        self.wav = wave.open(str(path), "wb")
        self.wav.setnchannels(channels)
        self.wav.setsampwidth(2)
        self.wav.setframerate(rate)

    def _write(self, data: bytes) -> None:
        self.wav.writeframes(data)
        self.frames += len(data) // (2 * self.channels)

    def write(self, data: bytes) -> None:
        with self.lock:
            self._write(data)
        self.level = max(map(abs, array("h", data)[::16]), default=0) / 32768

    def pad_to(self, seconds: float) -> None:
        # WASAPI loopback delivers nothing while the system is silent; padding keeps both tracks on the same clock.
        with self.lock:
            missing = int(seconds * self.rate) - self.frames
            if missing > self.rate * PAD_AFTER:
                self._write(bytes(missing * 2 * self.channels))
                self.level = 0.0

    def close(self) -> None:
        with self.lock:
            self.wav.close()


def convert_channels(data: bytes, src: int, dst: int) -> bytes:
    if src == dst:
        return data
    mono = array("h", data)[0::src]
    if dst == 1:
        return mono.tobytes()
    out = array("h", bytes(2 * len(mono) * dst))
    for c in range(dst):
        out[c::dst] = mono
    return out.tobytes()


def _wasapi_devices(pa) -> tuple[list[dict], list[dict], dict]:
    wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
    devices = [pa.get_device_info_by_index(i) for i in range(pa.get_device_count())]
    devices = [d for d in devices if d["hostApi"] == wasapi["index"]]
    mics = [d for d in devices if d["maxInputChannels"] > 0 and not d.get("isLoopbackDevice")]
    loopbacks = [d for d in devices if d.get("isLoopbackDevice")]
    return mics, loopbacks, wasapi


def _speaker_name(loopback: dict) -> str:
    return loopback["name"].removesuffix(" [Loopback]")


def list_devices() -> dict:
    """Current WASAPI microphones and speakers (by name), defaults first-class flagged."""
    pa = pyaudio.PyAudio()
    try:
        mics, loopbacks, wasapi = _wasapi_devices(pa)
        default_mic = pa.get_device_info_by_index(wasapi["defaultInputDevice"])["name"]
        default_out = _speaker_name(pa.get_default_wasapi_loopback())
        return {
            "mics": [{"name": d["name"], "default": d["name"] == default_mic} for d in mics],
            "speakers": [{"name": _speaker_name(d), "default": _speaker_name(d) == default_out} for d in loopbacks],
        }
    finally:
        pa.terminate()


class Recorder:
    """All PortAudio work runs on one long-lived thread: WASAPI binds streams to the COM apartment of the
    thread that initialized it, so opening a stream later from another (HTTP) thread fails with -9999."""

    def __init__(self, folder: Path, mic: str | None = None, speakers: str | None = None) -> None:
        self.pa = None
        self.tracks: dict[str, Track] = {}
        self.streams: dict[str, object] = {}
        self.devices: dict[str, str] = {}
        self.warning: str | None = None
        self.t0 = time.monotonic()
        self.jobs: queue.Queue = queue.Queue()
        self.running = True
        threading.Thread(target=self._worker, daemon=True).start()
        self._call(lambda: self._setup(folder, mic, speakers))

    def _worker(self) -> None:
        while self.running:
            try:
                fn, done = self.jobs.get(timeout=0.5)
            except queue.Empty:
                try:
                    self._pad_and_check()
                except Exception:
                    log.exception("Audio housekeeping failed")
                continue
            try:
                done.put((fn(), None))
            except Exception as e:
                done.put((None, e))
        # Anything queued after stop must not leave its caller waiting forever.
        while not self.jobs.empty():
            self.jobs.get_nowait()[1].put((None, RuntimeError("The recording has already stopped.")))

    def _call(self, fn):
        if not self.running:
            raise RuntimeError("The recording has already stopped.")
        done: queue.Queue = queue.Queue()
        self.jobs.put((fn, done))
        try:
            result, error = done.get(timeout=30)
        except queue.Empty:
            raise RuntimeError("The audio device did not respond. Stop and start a new recording.") from None
        if error:
            raise error
        return result

    def _setup(self, folder: Path, mic: str | None, speakers: str | None) -> None:
        try:
            self.pa = pyaudio.PyAudio()
            mic_dev, out_dev = self._find("mic", mic), self._find("system", speakers)
            self.tracks["mic"] = Track(folder / "mic.wav", int(mic_dev["defaultSampleRate"]), self._channels(mic_dev))
            self.tracks["system"] = Track(folder / "system.wav", int(out_dev["defaultSampleRate"]), self._channels(out_dev))
            # ponytail: one clock for both tracks, stream open latency (~tens of ms) and device drift are not compensated
            self.t0 = time.monotonic()
            self._attach("mic", mic_dev)
            self._attach("system", out_dev)
        except Exception:
            self._shutdown()
            raise

    @staticmethod
    def _channels(device: dict) -> int:
        return min(2, device["maxInputChannels"])

    def _find(self, track: str, name: str | None) -> dict:
        mics, loopbacks, wasapi = _wasapi_devices(self.pa)
        if track == "mic":
            if not name:
                return self.pa.get_device_info_by_index(wasapi["defaultInputDevice"])
            found = [d for d in mics if d["name"] == name]
        else:
            if not name:
                return self.pa.get_default_wasapi_loopback()
            found = [d for d in loopbacks if _speaker_name(d) == name]
        if not found:
            # ponytail: PortAudio enumerates devices once per session, so one plugged in mid-recording shows up next time
            raise RuntimeError(f"Device not found: {name}. If you just plugged it in, start a new recording.")
        return found[0]

    def _attach(self, name: str, device: dict) -> None:
        track = self.tracks[name]
        if int(device["defaultSampleRate"]) != track.rate:
            raise RuntimeError(f"{device['name']} uses {int(device['defaultSampleRate']) / 1000:g} kHz and this "
                               f"recording uses {track.rate / 1000:g} kHz. Stop and start a new recording to use it.")
        src = self._channels(device)

        def callback(data, frame_count, time_info, status):
            track.write(convert_channels(data, src, track.channels))
            return None, pyaudio.paContinue

        try:
            stream = self.pa.open(format=pyaudio.paInt16, channels=src, rate=track.rate, input=True, start=False,
                                  input_device_index=device["index"], frames_per_buffer=1024, stream_callback=callback)
        except OSError as e:
            raise RuntimeError(f"Windows could not open {device['name']} ({e}).") from None
        # Stop the old device before the new one starts, so the two never write into the track at the same time.
        old = self.streams.get(name)
        if old is not None:
            self._close(old)
        track.pad_to(self.elapsed())
        try:
            stream.start_stream()
        except OSError as e:
            stream.close()
            raise RuntimeError(f"Windows could not start {device['name']} ({e}).") from None
        self.streams[name] = stream
        self.devices[name] = device["name"] if name == "mic" else _speaker_name(device)

    @staticmethod
    def _close(stream) -> None:
        try:
            stream.stop_stream()
        except OSError:
            pass
        stream.close()

    def switch(self, track: str, name: str) -> None:
        def run():
            self._attach(track, self._find(track, name))
            self.warning = None
        self._call(run)

    def _pad_and_check(self) -> None:
        now = self.elapsed()
        # Loopback delivers nothing in silence, so it is always padded; the mic only once its stream has died,
        # because padding a live but late mic would insert silence before its real audio.
        dead = [n for n, s in self.streams.items() if not s.is_active()]
        for name, track in self.tracks.items():
            if name == "system" or name in dead:
                track.pad_to(now)
        if dead:
            label = {"mic": "Microphone", "system": "Speakers"}
            self.warning = f"{label[dead[0]]} stopped ({self.devices[dead[0]]}). Pick another device to keep recording."

    def elapsed(self) -> float:
        return time.monotonic() - self.t0

    def levels(self) -> dict:
        return {name: t.level for name, t in self.tracks.items()}

    def _shutdown(self) -> float:
        end = self.elapsed()
        try:
            for s in self.streams.values():
                self._close(s)
        finally:
            for t in self.tracks.values():
                t.pad_to(end)
                t.close()
            if self.pa is not None:
                self.pa.terminate()
            self.running = False
        return end

    def stop(self) -> float:
        return self._call(self._shutdown)
