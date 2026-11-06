# Ambient Soundboard (Lo-Fi / Focus Generator)

A native ambient audio mixer tile and soundscape player for [Nook](https://github.com/getnook/nook), the floating notch for Windows.

![Ambient Soundboard](https://img.shields.io/badge/Nook-Plugin-7C5CFF)
![Platform](https://img.shields.io/badge/Platform-Windows-blue)
![Python](https://img.shields.io/badge/Python-3.8+-green)

---

## Features

### 🎛️ Tile
- **Preset Thumbnail Badges**: The **Wide** tile displays an authentic visual preset thumbnail badge (e.g. 🔥 campfire flame, 🌧️ rain cloud, ☕ coffee cup, 🧠 focus brain, 💿 lo-fi disc, 🌲 forest tree) alongside the play/pause button and title.
- **Adaptive Layouts**:
  - **Small (44×44)**: Clean, high-contrast play/pause button with sleep countdown indicator.
  - **Wide (104×36)**: Preset thumbnail, soundscape title, layer count, playback state, and sleep countdown.
  - **Large (104×104)**: Mini ambient deck displaying preset badge, active soundscape, layer icons, volume, and sleep timer.
- **Accent Gradient**: Lights up with your Windows / Nook accent color when active.
- **Pill Badge**: Shows a circular countdown ring badge when a sleep timer is running, or a headphones glyph during active playback.

### 🎧 Page (Sound Mixer Deck)
- **Soundscape Presets**:
  - 🌧️ **Rainy Cabin** (70% Rain + 30% Thunder + 25% Campfire + 15% Wind)
  - ☕ **Cozy Cafe** (65% Cafe Chatter + 40% Lo-Fi Beats + 20% Rain)
  - 🧠 **Deep Focus** (55% White Noise + 40% Rain + 20% Wind)
  - 🔥 **Campfire Night** (75% Campfire + 30% Night Wind + 15% Forest Birds)
  - 🎹 **Lo-Fi Study** (70% Lo-Fi Beats + 25% Cafe + 15% White Noise)
  - 🌲 **Forest Haven** (60% Forest Birds + 35% Breeze + 25% Rain)
- **📁 Custom Tracks & Folder Shuffle Playlists**:
  - **Single Files**: Click **"+ File"** or drag and drop any audio file (`.wav`, `.mp3`, `.ogg`, `.flac`) to loop a custom track.
  - **Folder Shuffle Playlists**: Click **"+ Folder (Shuffle)"** or drag and drop an entire local folder of songs/sounds. It plays tracks from the folder, automatically shuffles to another song when one ends, and includes a 1-click **Shuffle** (`shuffle`) button to skip manually.
  - **Independent Volume & Removal**: Each custom track and folder gets its own volume slider (0–100%) and removal button (`trash`).
- **8 Authentic 1-Minute Ambient Audio Layers**:
  - 🌧️ **Rain** (`rain.wav`): Full 60s outdoor rainfall loop
  - ⚡ **Thunder** (`thunder.wav`): Full 60s rolling thunderstorm loop
  - 🔥 **Campfire** (`fire.wav`): Full 60s wood hearth crackles
  - ☕ **Cafe** (`cafe.wav`): Full 60s cafe room atmosphere & gentle chatter
  - 💿 **Lo-Fi Beats** (`lofi.wav`): Full 60s authentic recorded chillhop study beat
  - 〰️ **White Noise** (`noise.wav`): Full 60s smooth focus noise
  - 💨 **Wind & Waves** (`wind.wav`): Full 60s ocean surf swells and coastal breeze
  - 🌳 **Forest Birds** (`birds.wav`): Full 60s woodland birdsong field recording
- **Master Volume**: Precise master level slider in the top bar.
- **Organic Random Variations**: Toggleable dynamic volume drift (±4% for Lo-Fi beat, ±15% for natural sounds) and sporadic accent swells (thunder rolls, wind gusts, crackle bursts) so ambient loops never feel static or repetitive.
- **Sleep Timer**: Preset durations (**Off**, **15m**, **30m**, **45m**, **60m**) with real-time countdown.
  - 🌧️ **Rain**: Soothing steady rainfall with Poisson-distributed droplet impacts
  - ⚡ **Thunder**: Deep rolling low-frequency thunder rumbles (30Hz–90Hz)
  - 🔥 **Campfire**: Warm hearth crackles, cedar pops, and embers
  - ☕ **Cafe**: Formant-filtered conversational murmur & delicate cup clinks
  - 〰️ **White Noise**: Smooth pink/brown focus noise for distraction blocking
  - 💿 **Lo-Fi Beats**: Mellow electric piano 7th/9th chord progression with vinyl crackle
  - 💨 **Wind & Waves**: 8-second periodic ocean surf swells & tree breeze
  - 🌳 **Forest Birds**: Morning woodland birdsong chirps & soft leaf rustle
- **Master Volume & Mute**: Precise master level slider with 1-click global mute.
- **Sleep Timer**:
  - Preset durations: **Off**, **15m**, **30m**, **45m**, **60m**.
  - Real-time countdown on the page and pill ring progress badge.
  - Automatically pauses playback and clears badge when timer reaches zero.

### 🔊 Dual Audio Engine
- **Zero-Dependency WaveOut Player**: Built-in Windows `ctypes.windll.winmm` PCM mixer. All 8 bundled ambient loops play out of the box with zero external packages installed.
- **Hardware-Accelerated Pygame Mixer**: Automatically activates if `pygame` or `pygame-ce` is installed for DirectSound hardware-accelerated playback and compressed custom formats (.mp3, .ogg, .flac).

---

## Installation

### In Nook:
1. Clone or copy this repository into your Nook plugins directory:
   ```powershell
   git clone https://github.com/username/nook-soundboard.git "$env:APPDATA\Nook\plugins\nook-soundboard"
   ```
2. Enable **Plugin dev mode** in Nook Settings (or set `NOOK_PLUGIN_DEV=1`).
3. Ambient Soundboard will immediately appear in your tile catalog and play out of the box!
4. *(Optional)* Install `pygame-ce` if you want to import compressed custom audio tracks (.mp3, .ogg):
   ```powershell
   pip install pygame-ce
   ```

---

## File Structure

```
nook-soundboard/
├── plugin.toml       # Manifest defining id, name, icon, size, page size
├── main.py           # Protocol loop, UI views (tile + page), event dispatch
├── audio.py          # Multi-track audio mixer (Pygame + WaveOut fallback)
├── nook.py           # Standard Nook protocol helper
└── sounds/           # Authentic recorded ambient audio files
```

---

## Verification

To validate the plugin against the Nook protocol:
```bash
python <path-to-nook-skill>/scripts/check_plugin.py .
```
