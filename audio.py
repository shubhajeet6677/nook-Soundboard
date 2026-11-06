"""Multi-track ambient sound engine using Pygame Mixer with Windows WaveOut fallback."""

import os
import sys

# Suppress any third-party banners from stdout
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import ctypes
import random
import struct
import threading
import time
import wave

# Windows WaveOut types for fallback
winmm = None
if sys.platform == "win32":
    try:
        winmm = ctypes.windll.winmm
    except Exception:
        winmm = None


class _WAVEFORMATEX(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", ctypes.c_ushort),
        ("nChannels", ctypes.c_ushort),
        ("nSamplesPerSec", ctypes.c_ulong),
        ("nAvgBytesPerSec", ctypes.c_ulong),
        ("nBlockAlign", ctypes.c_ushort),
        ("wBitsPerSample", ctypes.c_ushort),
        ("cbSize", ctypes.c_ushort),
    ]


class _WAVEHDR(ctypes.Structure):
    pass


_WAVEHDR._fields_ = [
    ("lpData", ctypes.c_char_p),
    ("dwBufferLength", ctypes.c_ulong),
    ("dwBytesRecorded", ctypes.c_ulong),
    ("dwUser", ctypes.c_ulong),
    ("dwFlags", ctypes.c_ulong),
    ("dwLoops", ctypes.c_ulong),
    ("lpNext", ctypes.c_void_p),
    ("reserved", ctypes.c_ulong),
]

WHDR_DONE = 1


class WaveOutBackend:
    """Zero-dependency Windows PCM mixer fallback using waveOut."""

    def __init__(self, sample_rate=22050, chunk_size=2048):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.sounds = {}
        self.channels = {}
        self.master_vol = 1.0
        self.muted = False
        self.playing = False
        self.running = False
        self._lock = threading.Lock()
        self.h_waveout = None
        self._thread = None

    def start(self):
        if not winmm:
            return
        wfx = _WAVEFORMATEX()
        wfx.wFormatTag = 1
        wfx.nChannels = 1
        wfx.nSamplesPerSec = self.sample_rate
        wfx.wBitsPerSample = 16
        wfx.nBlockAlign = 2
        wfx.nAvgBytesPerSec = self.sample_rate * 2
        wfx.cbSize = 0

        self.h_waveout = ctypes.c_void_p()
        res = winmm.waveOutOpen(ctypes.byref(self.h_waveout), -1, ctypes.byref(wfx), 0, 0, 0)
        if res != 0:
            raise RuntimeError(f"waveOutOpen error: {res}")

        self.running = True
        self._thread = threading.Thread(target=self._mix_loop, daemon=True)
        self._thread.start()

    def load_track(self, name, filepath, loop=True):
        try:
            with wave.open(filepath, "rb") as wf:
                channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                if sampwidth != 2:
                    sys.stderr.write(f"[WaveOut] {filepath} must be 16-bit PCM WAV (got {sampwidth * 8}-bit)\n")
                    return False
                frames = wf.readframes(wf.getnframes())
                count = len(frames) // 2
                samples = struct.unpack("<" + "h" * count, frames)
                if channels == 2:
                    samples = [(samples[i] + samples[i + 1]) // 2 for i in range(0, len(samples) - 1, 2)]
                with self._lock:
                    self.sounds[name] = samples
                    self.channels[name] = {"pos": 0, "vol": 0.0, "loop": loop, "busy": True}
                return True
        except Exception as e:
            sys.stderr.write(f"[WaveOut] Failed to load {filepath} (only PCM WAV supported): {e}\n")
            return False

    def is_channel_busy(self, name):
        with self._lock:
            ch = self.channels.get(name)
            if ch:
                return ch.get("busy", False)
        return False

    def unload_track(self, name):
        with self._lock:
            if name in self.channels:
                del self.channels[name]
            if name in self.sounds:
                del self.sounds[name]

    def _mix_loop(self):
        NUM_BUFFERS = 3
        headers = []
        buffers = []
        for _ in range(NUM_BUFFERS):
            buf = ctypes.create_string_buffer(self.chunk_size * 2)
            hdr = _WAVEHDR()
            hdr.lpData = ctypes.cast(buf, ctypes.c_char_p)
            hdr.dwBufferLength = self.chunk_size * 2
            hdr.dwFlags = WHDR_DONE
            hdr.dwLoops = 0
            winmm.waveOutPrepareHeader(self.h_waveout, ctypes.byref(hdr), ctypes.sizeof(hdr))
            headers.append(hdr)
            buffers.append(buf)

        buf_idx = 0
        while self.running:
            hdr = headers[buf_idx]
            while (hdr.dwFlags & WHDR_DONE) == 0 and self.running:
                time.sleep(0.005)

            if not self.running:
                break

            with self._lock:
                is_playing = self.playing
                is_muted = self.muted
                master = 0.0 if is_muted else self.master_vol
                active = [
                    (name, ch["vol"], self.sounds[name])
                    for name, ch in self.channels.items()
                    if ch["vol"] > 0 and name in self.sounds
                ]

            mixed = [0] * self.chunk_size
            if is_playing and master > 0 and active:
                for name, vol, sound in active:
                    s_len = len(sound)
                    ch = self.channels[name]
                    if not ch.get("busy", True):
                        continue
                    pos = ch["pos"]
                    is_loop = ch.get("loop", True)
                    eff_vol = vol * master
                    for i in range(self.chunk_size):
                        idx = pos + i
                        if not is_loop and idx >= s_len:
                            ch["busy"] = False
                            break
                        mixed[i] += int(sound[idx % s_len] * eff_vol)
                    if is_loop:
                        ch["pos"] = (pos + self.chunk_size) % s_len
                    else:
                        ch["pos"] = pos + self.chunk_size
                        if ch["pos"] >= s_len:
                            ch["busy"] = False

            clamped = [max(-32767, min(32767, val)) for val in mixed]
            raw = struct.pack("<" + "h" * self.chunk_size, *clamped)
            ctypes.memmove(buffers[buf_idx], raw, self.chunk_size * 2)

            hdr.dwFlags &= ~WHDR_DONE
            winmm.waveOutWrite(self.h_waveout, ctypes.byref(hdr), ctypes.sizeof(hdr))
            buf_idx = (buf_idx + 1) % NUM_BUFFERS

        for hdr in headers:
            winmm.waveOutUnprepareHeader(self.h_waveout, ctypes.byref(hdr), ctypes.sizeof(hdr))
        winmm.waveOutClose(self.h_waveout)

    def set_layer_volume(self, name, vol):
        with self._lock:
            if name in self.channels:
                self.channels[name]["vol"] = max(0.0, min(1.0, vol))

    def set_master_volume(self, vol):
        with self._lock:
            self.master_vol = max(0.0, min(1.0, vol))

    def set_muted(self, muted):
        with self._lock:
            self.muted = bool(muted)

    def set_playing(self, playing):
        with self._lock:
            self.playing = bool(playing)

    def stop(self):
        self.running = False
        self.playing = False
        if self._thread:
            self._thread.join(timeout=0.1)


class PygameBackend:
    """Multi-channel audio mixer using pygame.mixer."""

    def __init__(self):
        import pygame

        os.environ["SDL_AUDIODRIVER"] = "directsound"
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
        pygame.mixer.set_num_channels(24)
        self.sounds = {}
        self.channels = {}
        self.layer_vols = {}
        self.master_vol = 1.0
        self.muted = False
        self.playing = False
        self._lock = threading.Lock()

    def start(self):
        pass

    def load_track(self, name, filepath, loop=True):
        import pygame

        try:
            with self._lock:
                if name in self.channels:
                    try:
                        self.channels[name].stop()
                    except Exception:
                        pass

                sound = pygame.mixer.Sound(filepath)
                channel = self.channels.get(name) or pygame.mixer.find_channel(True)
                if not channel:
                    pygame.mixer.set_num_channels(pygame.mixer.get_num_channels() + 4)
                    channel = pygame.mixer.find_channel(True)

                self.sounds[name] = sound
                self.channels[name] = channel
                if name not in self.layer_vols:
                    self.layer_vols[name] = 0.0

                channel.play(sound, loops=-1 if loop else 0)
                eff_vol = self.layer_vols[name] * (0.0 if self.muted else self.master_vol)
                channel.set_volume(eff_vol)
                if not self.playing:
                    channel.pause()
            return True
        except Exception as e:
            sys.stderr.write(f"[Pygame] Failed to load {filepath}: {e}\n")
            return False

    def is_channel_busy(self, name):
        with self._lock:
            ch = self.channels.get(name)
            if ch:
                return ch.get_busy()
        return False

    def unload_track(self, name):
        with self._lock:
            if name in self.channels:
                try:
                    self.channels[name].stop()
                except Exception:
                    pass
                del self.channels[name]
            if name in self.sounds:
                del self.sounds[name]
            if name in self.layer_vols:
                del self.layer_vols[name]

    def _update_channel_volumes(self):
        eff_master = 0.0 if self.muted else self.master_vol
        for name, ch in self.channels.items():
            vol = self.layer_vols.get(name, 0.0)
            ch.set_volume(vol * eff_master)

    def set_layer_volume(self, name, vol):
        with self._lock:
            self.layer_vols[name] = max(0.0, min(1.0, vol))
            self._update_channel_volumes()

    def set_master_volume(self, vol):
        with self._lock:
            self.master_vol = max(0.0, min(1.0, vol))
            self._update_channel_volumes()

    def set_muted(self, muted):
        with self._lock:
            self.muted = bool(muted)
            self._update_channel_volumes()

    def set_playing(self, playing):
        with self._lock:
            self.playing = bool(playing)
            for ch in self.channels.values():
                if self.playing:
                    ch.unpause()
                else:
                    ch.pause()

    def stop(self):
        import pygame

        self.playing = False
        pygame.mixer.stop()
        pygame.mixer.quit()


class SoundboardAudio:
    """Unified audio controller for Ambient Soundboard."""

    def __init__(self, sounds_dir):
        self.sounds_dir = sounds_dir
        self.backend = None
        self.layer_names = ["rain", "thunder", "fire", "cafe", "lofi", "noise", "wind", "birds"]
        self.playing = False
        self.master_volume = 0.8
        self.muted = False
        self.volumes = {name: 0.0 for name in self.layer_names}
        self.variations_enabled = True
        self._var_state = {}
        self._lock = threading.Lock()
        self._running_var = True

        try:
            self.backend = PygameBackend()
        except Exception as e:
            sys.stderr.write(f"Pygame backend unavailable ({e}), using WaveOut fallback\n")
            if winmm:
                self.backend = WaveOutBackend()
            else:
                self.backend = None

        if self.backend:
            for name in self.layer_names:
                p = self._find_sound_file(name)
                if p:
                    self.load_track(name, p)
            if hasattr(self.backend, "start"):
                self.backend.start()

        self._var_thread = threading.Thread(target=self._variation_loop, daemon=True)
        self._var_thread.start()

    def _find_sound_file(self, name):
        for ext in [".mp3", ".ogg", ".wav"]:
            cand = os.path.join(self.sounds_dir, f"{name}{ext}")
            if os.path.exists(cand):
                return cand
        return None

    def _variation_loop(self):
        while self._running_var:
            time.sleep(0.3)
            if not self.playing or not self.variations_enabled or not self.backend:
                continue

            now = time.time()
            with self._lock:
                names = list(self.volumes.keys())

            for name in names:
                base_vol = self.volumes.get(name, 0.0)
                if base_vol <= 0:
                    continue

                state = self._var_state.setdefault(
                    name,
                    {
                        "curr": 1.0,
                        "target": 1.0,
                        "next_target": 0.0,
                        "next_burst": now + random.uniform(15.0, 45.0),
                        "burst_end": 0.0,
                        "burst_mult": 1.0,
                    },
                )

                # Periodic drift target (lo-fi subtle ±4%, nature tracks ±15%)
                if now >= state["next_target"]:
                    drift = 0.04 if name == "lofi" else 0.15
                    state["target"] = random.uniform(1.0 - drift, 1.0 + drift)
                    state["next_target"] = now + random.uniform(4.0, 8.0)

                # Smoothly glide current factor toward target
                state["curr"] += (state["target"] - state["curr"]) * 0.08

                # Sporadic accent swells (thunder rumbles, wind gusts, fire crackles)
                if name in ("thunder", "wind", "fire"):
                    if now >= state["next_burst"]:
                        state["burst_mult"] = (
                            random.uniform(1.35, 1.6)
                            if name == "thunder"
                            else random.uniform(1.15, 1.3)
                        )
                        burst_len = random.uniform(4.0, 7.0)
                        state["burst_end"] = now + burst_len
                        state["next_burst"] = now + burst_len + random.uniform(25.0, 55.0)

                accent = state["burst_mult"] if now < state["burst_end"] else 1.0
                eff_vol = max(0.0, min(1.0, base_vol * state["curr"] * accent))
                self.backend.set_layer_volume(name, eff_vol)

    def load_track(self, name, filepath, loop=True):
        if self.backend:
            try:
                ok = self.backend.load_track(name, filepath, loop=loop)
                if ok:
                    with self._lock:
                        if name not in self.volumes:
                            self.volumes[name] = 0.0
                    return True
                else:
                    sys.stderr.write(f"[audio] Backend failed to load '{name}' from {filepath}\n")
                    return False
            except Exception as e:
                sys.stderr.write(f"[audio] Failed to load track '{name}' from {filepath}: {e}\n")
                return False
        return False

    def is_channel_busy(self, name):
        if self.backend and hasattr(self.backend, "is_channel_busy"):
            return self.backend.is_channel_busy(name)
        return False

    def is_pygame_active(self):
        return type(self.backend).__name__ == "PygameBackend"

    def get_loaded_track_count(self):
        if self.backend and hasattr(self.backend, "sounds"):
            return len(self.backend.sounds)
        return 0

    def unload_track(self, name):
        if self.backend:
            self.backend.unload_track(name)
        with self._lock:
            if name in self.volumes:
                del self.volumes[name]
            if name in self._var_state:
                del self._var_state[name]

    def set_playing(self, playing):
        self.playing = bool(playing)
        if self.backend:
            self.backend.set_playing(self.playing)

    def is_playing(self):
        return self.playing

    def set_layer_volume(self, name, vol):
        clamped = max(0.0, min(1.0, vol))
        with self._lock:
            self.volumes[name] = clamped
        if self.backend:
            mult = 1.0
            if self.variations_enabled and name in self._var_state:
                st = self._var_state[name]
                accent = st["burst_mult"] if time.time() < st["burst_end"] else 1.0
                mult = st["curr"] * accent
            self.backend.set_layer_volume(name, max(0.0, min(1.0, clamped * mult)))

    def set_variations(self, enabled):
        self.variations_enabled = bool(enabled)
        if self.backend:
            with self._lock:
                for name, vol in self.volumes.items():
                    if not self.variations_enabled:
                        self.backend.set_layer_volume(name, vol)

    def set_master_volume(self, vol):
        self.master_volume = max(0.0, min(1.0, vol))
        if self.backend:
            self.backend.set_master_volume(self.master_volume)

    def set_muted(self, muted):
        self.muted = bool(muted)
        if self.backend:
            self.backend.set_muted(self.muted)

    def stop(self):
        self._running_var = False
        self.playing = False
        if self._var_thread and self._var_thread.is_alive():
            self._var_thread.join(timeout=0.1)
        if self.backend:
            self.backend.stop()
