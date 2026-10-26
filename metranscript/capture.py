import threading
import time
import wave
from array import array
from pathlib import Path

import pyaudiowpatch as pyaudio

PAD_AFTER = 0.2


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


class Recorder:
    def __init__(self, folder: Path) -> None:
        self.pa = pyaudio.PyAudio()
        self.tracks: dict[str, Track] = {}
        try:
            wasapi = self.pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            mic = self.pa.get_device_info_by_index(wasapi["defaultInputDevice"])
            loopback = self.pa.get_default_wasapi_loopback()
            self.tracks["mic"] = Track(folder / "mic.wav", int(mic["defaultSampleRate"]), mic["maxInputChannels"])
            self.tracks["system"] = Track(folder / "system.wav", int(loopback["defaultSampleRate"]),
                                          loopback["maxInputChannels"])
            # ponytail: one clock for both tracks, stream open latency (~tens of ms) and device drift are not compensated
            self.t0 = time.monotonic()
            self.streams = [self._open(mic, self.tracks["mic"]), self._open(loopback, self.tracks["system"])]
        except Exception:
            self.pa.terminate()
            for t in self.tracks.values():
                t.close()
            raise
        self.stopping = threading.Event()
        self.pad_thread = threading.Thread(target=self._pad_loop, daemon=True)
        self.pad_thread.start()

    def _open(self, device: dict, track: Track):
        def callback(data, frame_count, time_info, status):
            track.write(data)
            return None, pyaudio.paContinue

        return self.pa.open(
            format=pyaudio.paInt16,
            channels=track.channels,
            rate=track.rate,
            input=True,
            input_device_index=device["index"],
            frames_per_buffer=1024,
            stream_callback=callback,
        )

    def _pad_loop(self) -> None:
        while not self.stopping.wait(0.5):
            self.tracks["system"].pad_to(self.elapsed())

    def elapsed(self) -> float:
        return time.monotonic() - self.t0

    def levels(self) -> dict:
        return {name: t.level for name, t in self.tracks.items()}

    def stop(self) -> float:
        self.stopping.set()
        self.pad_thread.join()
        for s in self.streams:
            s.stop_stream()
            s.close()
        end = self.elapsed()
        for t in self.tracks.values():
            t.pad_to(end)
            t.close()
        self.pa.terminate()
        return end
