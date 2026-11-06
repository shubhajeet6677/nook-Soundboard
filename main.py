#!/usr/bin/env python3
"""Ambient Soundboard (Lo-Fi / Focus Generator) for Nook.

Tile: Single toggle button to pause/play favorite soundscape.
Page: Unified mixer console with independent volume sliders, custom tracks
      from device, presets, and sleep timer.
"""

import os
import sys

# Ensure stdout carries UTF-8 JSON protocol only
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import shutil
import threading
import time

import nook
from audio import SoundboardAudio

app = nook.Plugin()

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SOUNDS_DIR = os.path.join(ROOT_DIR, "sounds")
audio = SoundboardAudio(SOUNDS_DIR)

AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".aac", ".m4a", ".wma"}

# Ambient layers with Lo-Fi and Noise swapped
LAYERS = [
    {"id": "rain", "name": "Rain", "icon": "cloud-rain"},
    {"id": "thunder", "name": "Thunder", "icon": "cloud-lightning"},
    {"id": "fire", "name": "Campfire", "icon": "fire"},
    {"id": "cafe", "name": "Cafe", "icon": "coffee"},
    {"id": "lofi", "name": "Lo-Fi Beats", "icon": "disc"},
    {"id": "noise", "name": "White Noise", "icon": "wave-sine"},
    {"id": "wind", "name": "Wind & Waves", "icon": "wind"},
    {"id": "birds", "name": "Forest Birds", "icon": "tree"},
]
LAYER_MAP = {l["id"]: l for l in LAYERS}

PRESETS = [
    {
        "name": "Rainy Cabin",
        "icon": "cloud-rain",
        "color": "blue",
        "volumes": {"rain": 70, "thunder": 30, "fire": 25, "cafe": 0, "lofi": 0, "noise": 0, "wind": 15, "birds": 0},
    },
    {
        "name": "Cozy Cafe",
        "icon": "coffee",
        "color": "orange",
        "volumes": {"rain": 20, "thunder": 0, "fire": 0, "cafe": 65, "lofi": 40, "noise": 0, "wind": 0, "birds": 0},
    },
    {
        "name": "Deep Focus",
        "icon": "brain",
        "color": "purple",
        "volumes": {"rain": 40, "thunder": 0, "fire": 0, "cafe": 0, "lofi": 0, "noise": 55, "wind": 20, "birds": 0},
    },
    {
        "name": "Campfire Night",
        "icon": "fire",
        "color": "orange",
        "volumes": {"rain": 0, "thunder": 0, "fire": 75, "cafe": 0, "lofi": 0, "noise": 0, "wind": 30, "birds": 15},
    },
    {
        "name": "Lo-Fi Study",
        "icon": "disc",
        "color": "pink",
        "volumes": {"rain": 15, "thunder": 0, "fire": 0, "cafe": 25, "lofi": 70, "noise": 15, "wind": 0, "birds": 0},
    },
    {
        "name": "Forest Haven",
        "icon": "tree",
        "color": "green",
        "volumes": {"rain": 25, "thunder": 0, "fire": 0, "cafe": 0, "lofi": 0, "noise": 0, "wind": 35, "birds": 60},
    },
]

TIMER_OPTIONS = ["Off", "15m", "30m", "45m", "60m"]
TIMER_MINUTES = [0, 15, 30, 45, 60]

# --- State Management ---
saved_state = app.load("state", {})
preset_idx = saved_state.get("preset_idx", 0)
if preset_idx >= len(PRESETS):
    preset_idx = 0

is_custom = saved_state.get("is_custom", False)
volumes = saved_state.get("volumes", dict(PRESETS[preset_idx]["volumes"]))
for l in LAYERS:
    if l["id"] not in volumes:
        volumes[l["id"]] = 0

master_volume = saved_state.get("master_volume", 80)
variations_enabled = saved_state.get("variations_enabled", True)
is_playing = False

sleep_timer_seconds = 0
sleep_timer_end = None
timer_chip_idx = 0

custom_sounds = app.load("custom_sounds", [])

# Apply initial layer volumes to audio engine
for lid, vol in volumes.items():
    audio.set_layer_volume(lid, vol / 100.0)

for s in list(custom_sounds):
    sid = s["id"]
    svol = s.get("vol", 50)
    stype = s.get("type", "file")
    if stype == "folder":
        cur_file = s.get("current_track", "")
        if os.path.isfile(cur_file):
            if audio.load_track(sid, cur_file, loop=False):
                audio.set_layer_volume(sid, svol / 100.0)
    else:
        spath = s.get("path", "")
        if os.path.isfile(spath):
            if audio.load_track(sid, spath, loop=True):
                audio.set_layer_volume(sid, svol / 100.0)

audio.set_master_volume(master_volume / 100.0)
audio.set_variations(variations_enabled)


def save_state():
    app.save(
        "state",
        {
            "preset_idx": preset_idx,
            "is_custom": is_custom,
            "volumes": volumes,
            "master_volume": master_volume,
            "variations_enabled": variations_enabled,
        },
    )
    app.save("custom_sounds", custom_sounds)


def get_current_soundscape_name():
    if is_custom:
        return "Custom Mix"
    return PRESETS[preset_idx]["name"]


def count_active_layers():
    preset_active = sum(1 for v in volumes.values() if v > 0)
    custom_active = sum(1 for s in custom_sounds if s.get("vol", 0) > 0)
    return preset_active + custom_active


def format_timer_remaining():
    if not sleep_timer_end:
        return ""
    rem = max(0, int(sleep_timer_end - time.time()))
    mins = rem // 60
    secs = rem % 60
    return f"{mins:02d}:{secs:02d}"


# --- Custom Sound Management ---

def add_custom_sound(src_path):
    if not os.path.isfile(src_path):
        return
    ext = os.path.splitext(src_path)[1].lower()
    if ext not in AUDIO_EXTS:
        return

    custom_dir = os.path.join(app.data_dir, "custom_sounds")
    os.makedirs(custom_dir, exist_ok=True)

    sound_id = f"c_{int(time.time() * 1000) % 1000000}_{len(custom_sounds) + 1}"
    base_name = os.path.splitext(os.path.basename(src_path))[0]
    clean_name = base_name.replace("_", " ").replace("-", " ").strip()
    if len(clean_name) > 18:
        clean_name = clean_name[:18].strip() + "…"
    clean_name = clean_name.title() if clean_name.islower() else clean_name

    dest_filename = f"{sound_id}{ext}"
    dest_path = os.path.join(custom_dir, dest_filename)
    try:
        shutil.copy2(src_path, dest_path)
    except Exception as e:
        sys.stderr.write(f"Copy error: {e}\n")
        dest_path = src_path

    if audio.load_track(sound_id, dest_path, loop=True):
        item = {
            "id": sound_id,
            "type": "file",
            "name": clean_name,
            "path": dest_path,
            "vol": 50,
        }
        custom_sounds.append(item)
        audio.set_layer_volume(sound_id, 0.5)
        save_state()
        _register_custom_sound_handlers(sound_id)
        draw()
    else:
        app.log(f"Cannot load {clean_name}. Install pygame-ce for compressed formats.", "error")


def add_custom_folder(folder_path):
    if not os.path.isdir(folder_path):
        return
    audio_files = []
    for root, _, files in os.walk(folder_path):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in AUDIO_EXTS:
                audio_files.append(os.path.join(root, f))

    if not audio_files:
        app.log("No audio files found in selected folder", "warning")
        return

    import random
    first_track = random.choice(audio_files)
    sound_id = f"cf_{int(time.time() * 1000) % 1000000}_{len(custom_sounds) + 1}"
    base_name = os.path.basename(folder_path.rstrip("\\/"))
    clean_name = base_name.replace("_", " ").replace("-", " ").strip()
    if len(clean_name) > 18:
        clean_name = clean_name[:18].strip() + "…"
    clean_name = clean_name.title() if clean_name.islower() else clean_name

    track_name = os.path.basename(first_track)

    if audio.load_track(sound_id, first_track, loop=False):
        item = {
            "id": sound_id,
            "type": "folder",
            "name": clean_name,
            "folder_path": folder_path,
            "files": audio_files,
            "current_track": first_track,
            "current_track_name": track_name,
            "vol": 50,
        }
        custom_sounds.append(item)
        audio.set_layer_volume(sound_id, 0.5)
        save_state()
        _register_custom_sound_handlers(sound_id)
        draw()
    else:
        app.log(f"Failed to play tracks in {clean_name}", "error")


def shuffle_custom_folder(sound_id):
    target = next((s for s in custom_sounds if s["id"] == sound_id and s.get("type") == "folder"), None)
    if not target:
        return
    files = target.get("files", [])
    if not files:
        return

    import random
    curr = target.get("current_track")
    cands = [f for f in files if f != curr] if len(files) > 1 else files
    next_track = random.choice(cands)
    target["current_track"] = next_track
    target["current_track_name"] = os.path.basename(next_track)

    audio.load_track(sound_id, next_track, loop=False)
    audio.set_layer_volume(sound_id, target.get("vol", 50) / 100.0)
    save_state()
    draw()


def remove_custom_sound(sound_id):
    global custom_sounds
    target = next((s for s in custom_sounds if s["id"] == sound_id), None)
    if target:
        audio.unload_track(sound_id)
        try:
            p = target.get("path", "")
            if os.path.isfile(p) and app.data_dir in p:
                os.remove(p)
        except Exception:
            pass
        custom_sounds = [s for s in custom_sounds if s["id"] != sound_id]
        save_state()
        draw()


# --- Drawing Views ---

def build_tile_view():
    size = app.tile_size or "wide"
    soundscape_name = get_current_soundscape_name()
    active_count = count_active_layers()
    rem_str = format_timer_remaining()

    play_btn = nook.button(
        "toggle_play",
        icon="pause" if is_playing else "play",
        primary=is_playing,
        tooltip="Pause soundscape" if is_playing else "Play soundscape",
    )

    if is_custom:
        current_icon = "faders"
        current_color = "accent"
    else:
        preset = PRESETS[preset_idx]
        current_icon = preset.get("icon", "headphones")
        current_color = preset.get("color", "accent")

    preset_thumb = nook.icon(
        current_icon,
        size=20,
        color=current_color if is_playing else "dim",
        fill=True,
        tooltip=soundscape_name,
    )

    if size == "small":
        if rem_str:
            return nook.column(
                [play_btn, nook.text(rem_str, size="small", color="accent")],
                gap=2,
                align="center",
                justify="center",
            )
        return nook.column([play_btn], align="center", justify="center")

    elif size == "large":
        active_icons = [
            nook.icon(l["icon"], size=16, color="accent")
            for l in LAYERS
            if volumes.get(l["id"], 0) > 0
        ]
        for s in custom_sounds:
            if s.get("vol", 0) > 0:
                s_icon = "folder" if s.get("type") == "folder" else "music-note"
                active_icons.append(nook.icon(s_icon, size=16, color="accent"))

        if not active_icons:
            active_icons = [nook.text("No active layers", size="small", color="dim")]

        status_text = (
            f"Sleep in {rem_str}"
            if rem_str
            else ("Playing" if is_playing else "Paused")
        )

        return nook.column(
            [
                nook.row(
                    [
                        nook.icon(current_icon, size=18, color=current_color if is_playing else "dim", fill=True),
                        nook.text("Soundboard", size="body", bold=True),
                        nook.spacer(),
                        play_btn,
                    ],
                    align="center",
                ),
                nook.text(soundscape_name, size="title", bold=True, color=current_color if is_playing else "text"),
                nook.row(active_icons[:5], gap=4, align="center"),
                nook.spacer(),
                nook.row(
                    [
                        nook.text(status_text, size="small", color="accent" if rem_str else "dim"),
                        nook.spacer(),
                        nook.text(f"{master_volume}% vol", size="small", color="dim"),
                    ],
                    align="center",
                ),
            ],
            gap=4,
        )

    # Default: "wide" (104 x 36)
    if rem_str:
        sub_text = f"Sleep in {rem_str}"
    elif is_playing:
        sub_text = f"Playing - {active_count} layers"
    else:
        sub_text = f"Paused - {active_count} layers"

    return nook.row(
        [
            play_btn,
            preset_thumb,
            nook.column(
                [
                    nook.text(soundscape_name, size="title"),
                    nook.text(sub_text, size="small", color="accent" if rem_str else "dim"),
                ],
                gap=0,
            ),
        ],
        align="center",
        gap=6,
    )


def build_page_view():
    active_count = count_active_layers()
    rem_str = format_timer_remaining()

    # 1. Clean Top Header Bar
    header_card = nook.card(
        [
            nook.row(
                [
                    nook.icon("headphones", size=18, color="accent"),
                    nook.text("Ambient Soundboard", size="title", bold=True),
                    nook.spacer(),
                    nook.text(f"Master {master_volume}%", size="small", color="dim", mono=True),
                    nook.slider("master_volume", value=master_volume, min=0, max=100, step=5, width=130),
                ],
                align="center",
                gap=8,
            ),
        ],
        padding=8,
    )

    # 2. Presets Selector Row
    preset_names = [p["name"] for p in PRESETS]
    if is_custom:
        preset_names.append("Custom")
        selected_preset = len(PRESETS)
    else:
        selected_preset = preset_idx

    presets_card = nook.card(
        [
            nook.chips("preset_chips", options=preset_names, selected=selected_preset),
        ],
        padding=6,
    )

    # 3. Main Ambient Sound Layers Grid (Consistent 2-column cells, width=180 sliders)
    layer_cells = []
    for l in LAYERS:
        lid = l["id"]
        vol = volumes.get(lid, 0)
        is_active = vol > 0

        layer_cells.append(
            nook.card(
                [
                    nook.row(
                        [
                            nook.icon(l["icon"], size=16, color="accent" if is_active else "dim"),
                            nook.text(l["name"], size="body", bold=is_active),
                            nook.spacer(),
                            nook.text(f"{vol}%", size="small", color="accent" if is_active else "dim", mono=True),
                        ],
                        align="center",
                    ),
                    nook.slider(f"layer:{lid}", value=vol, min=0, max=100, step=5, width=180),
                ],
                padding=6,
                gap=3,
            )
        )

    mixer_card = nook.card(
        [
            nook.row(
                [
                    nook.icon("faders", size=16, color="accent"),
                    nook.text("Sound Layers", size="body", bold=True),
                    nook.spacer(),
                    nook.toggle(
                        "toggle_variations",
                        value=variations_enabled,
                        label="Variations",
                        tooltip="Subtle organic volume variations over time",
                    ),
                    nook.spacer(size=8),
                    nook.text(f"{active_count} active", size="small", color="dim"),
                ],
                align="center",
            ),
            nook.grid(columns=2, children=layer_cells, gap=6),
        ],
        padding=8,
        gap=6,
    )

    # 4. Custom Tracks Section
    custom_cells = []
    for s in custom_sounds:
        svol = s.get("vol", 0)
        is_active = svol > 0
        stype = s.get("type", "file")

        if stype == "folder":
            cur_name = s.get("current_track_name", "Track")
            if len(cur_name) > 16:
                cur_name = cur_name[:14] + "…"
            track_count = len(s.get("files", []))
            custom_cells.append(
                nook.card(
                    [
                        nook.row(
                            [
                                nook.icon("folder", size=16, color="accent" if is_active else "dim"),
                                nook.column(
                                    [
                                        nook.text(s["name"], size="body", bold=is_active),
                                        nook.text(f"♪ {cur_name} ({track_count})", size="small", color="dim"),
                                    ],
                                    gap=0,
                                ),
                                nook.spacer(),
                                nook.text(f"{svol}%", size="small", color="accent" if is_active else "dim", mono=True),
                                nook.button(f"shuffle_sound:{s['id']}", icon="shuffle", tooltip="Shuffle to next track in folder"),
                                nook.button(f"del_sound:{s['id']}", icon="trash", tooltip=f"Remove folder {s['name']}"),
                            ],
                            align="center",
                            gap=4,
                        ),
                        nook.slider(f"layer:{s['id']}", value=svol, min=0, max=100, step=5, width=180),
                    ],
                    padding=6,
                    gap=3,
                )
            )
        else:
            custom_cells.append(
                nook.card(
                    [
                        nook.row(
                            [
                                nook.icon("music-note", size=16, color="accent" if is_active else "dim"),
                                nook.text(s["name"], size="body", bold=is_active),
                                nook.spacer(),
                                nook.text(f"{svol}%", size="small", color="accent" if is_active else "dim", mono=True),
                                nook.button(f"del_sound:{s['id']}", icon="trash", tooltip=f"Remove {s['name']}"),
                            ],
                            align="center",
                        ),
                        nook.slider(f"layer:{s['id']}", value=svol, min=0, max=100, step=5, width=180),
                    ],
                    padding=6,
                    gap=3,
                )
            )

    custom_children = [
        nook.row(
            [
                nook.icon("music-notes", size=16, color="accent"),
                nook.text("My Custom Tracks", size="body", bold=True),
                nook.spacer(),
                nook.button("browse_sound", label="+ File", icon="music-note", tooltip="Import single audio file from device"),
                nook.button("browse_folder", label="+ Folder (Shuffle)", icon="folder-plus", tooltip="Import a local folder of sounds to shuffle continuously"),
            ],
            align="center",
            gap=6,
        ),
    ]

    if custom_cells:
        custom_children.append(nook.grid(columns=2, children=custom_cells, gap=6))
    else:
        custom_children.append(
            nook.row(
                [
                    nook.icon("waveform", size=14, color="dim"),
                    nook.text("Drop audio files or folders, or click + File / + Folder (Shuffle)", size="small", color="dim"),
                ],
                align="center",
                gap=6,
            )
        )

    custom_card = nook.card(custom_children, padding=8, gap=6)

    # 5. Sleep Timer Card
    timer_status = f"Stopping in {rem_str}" if rem_str else "Inactive"
    timer_card = nook.card(
        [
            nook.row(
                [
                    nook.icon("timer", size=16, color="accent" if rem_str else "dim"),
                    nook.text("Sleep Timer", size="body", bold=True),
                    nook.text(f"- {timer_status}", size="small", color="accent" if rem_str else "dim"),
                    nook.spacer(),
                    nook.chips("timer_chips", options=TIMER_OPTIONS, selected=timer_chip_idx),
                ],
                align="center",
                gap=8,
            ),
        ],
        padding=8,
    )

    page_cards = [header_card]
    if not audio.is_pygame_active() and audio.get_loaded_track_count() == 0:
        page_cards.append(
            nook.card(
                [
                    nook.row(
                        [
                            nook.icon("warning", size=16, color="orange"),
                            nook.text("Pygame required for MP3/OGG audio. Run: pip install pygame-ce", size="small", color="orange"),
                        ],
                        align="center",
                        gap=6,
                    )
                ],
                padding=6,
            )
        )
    page_cards.extend([presets_card, mixer_card, custom_card, timer_card])

    page_view = nook.column(
        page_cards,
        gap=6,
        scroll=False,
    )

    return page_view, []


def draw():
    app.tile(build_tile_view())
    page_view, page_actions = build_page_view()
    app.page(page_view, actions=page_actions)
    app.active(is_playing)


# --- Event Handlers ---

@app.on("toggle_play")
def handle_toggle_play(event):
    global is_playing
    is_playing = not is_playing
    audio.set_playing(is_playing)

    if is_playing:
        app.active(True)
        if sleep_timer_end and sleep_timer_seconds > 0:
            rem = max(0, sleep_timer_end - time.time())
            app.badge_ring(rem / sleep_timer_seconds, label=f"{int(rem // 60)}m")
        else:
            app.badge_glyph("headphones")
    else:
        app.active(False)
        app.clear_badge()

    draw()


@app.on("preset_chips")
def handle_preset_chips(event):
    global preset_idx, is_custom
    val = event.get("value", {})
    idx = val.get("index", 0) if isinstance(val, dict) else 0

    if idx < len(PRESETS):
        preset_idx = idx
        is_custom = False
        preset_vols = PRESETS[preset_idx]["volumes"]
        for lid in volumes:
            new_v = preset_vols.get(lid, 0)
            volumes[lid] = new_v
            audio.set_layer_volume(lid, new_v / 100.0)
        save_state()
        draw()


@app.on("toggle_variations")
def handle_toggle_variations(event):
    global variations_enabled
    val = event.get("value")
    if isinstance(val, dict):
        val = val.get("value", True)
    variations_enabled = bool(val)
    audio.set_variations(variations_enabled)
    save_state()
    draw()


def handle_layer_slider(layer_id, event):
    global is_custom
    raw_val = event.get("value", 0)
    vol = max(0, min(100, int(round(raw_val))))

    if layer_id in volumes:
        volumes[layer_id] = vol
        audio.set_layer_volume(layer_id, vol / 100.0)
        current_preset_vols = PRESETS[preset_idx]["volumes"]
        if volumes != current_preset_vols:
            is_custom = True
        else:
            is_custom = False
    else:
        for s in custom_sounds:
            if s["id"] == layer_id:
                s["vol"] = vol
                break
        audio.set_layer_volume(layer_id, vol / 100.0)

    save_state()
    draw()


for l in LAYERS:
    lid = l["id"]

    def _make_handler(target_id):
        return lambda e: handle_layer_slider(target_id, e)

    app.on(f"layer:{lid}")(_make_handler(lid))


def _register_custom_sound_handlers(sound_id):
    app.on(f"layer:{sound_id}")(lambda e, sid=sound_id: handle_layer_slider(sid, e))
    app.on(f"del_sound:{sound_id}")(lambda e, sid=sound_id: remove_custom_sound(sid))
    app.on(f"shuffle_sound:{sound_id}")(lambda e, sid=sound_id: shuffle_custom_folder(sid))


for s in custom_sounds:
    _register_custom_sound_handlers(s["id"])


@app.on("browse_sound")
def handle_browse_sound(event):
    def _open_dialog():
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            selected = filedialog.askopenfilename(
                title="Select Ambient Sound File",
                filetypes=[
                    ("Audio Files (*.wav, *.mp3, *.ogg, *.flac)", "*.wav;*.mp3;*.ogg;*.flac;*.m4a;*.wma;*.aac"),
                    ("All Files", "*.*"),
                ],
            )
            root.destroy()
            if selected:
                add_custom_sound(selected)
        except Exception as e:
            sys.stderr.write(f"Picker error: {e}\n")

    threading.Thread(target=_open_dialog, daemon=True).start()


@app.on("browse_folder")
def handle_browse_folder(event):
    def _open_folder_dialog():
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            selected = filedialog.askdirectory(title="Select Folder of Sounds to Shuffle")
            root.destroy()
            if selected:
                add_custom_folder(selected)
        except Exception as e:
            sys.stderr.write(f"Folder picker error: {e}\n")

    threading.Thread(target=_open_folder_dialog, daemon=True).start()


@app.on_message("files")
def handle_dropped_files(msg):
    paths = msg.get("paths", [])
    for p in paths:
        if os.path.isdir(p):
            add_custom_folder(p)
        elif os.path.isfile(p):
            add_custom_sound(p)


@app.on_message("event")
def handle_dynamic_event(msg):
    eid = msg.get("id", "")
    if eid.startswith("del_sound:"):
        sid = eid.split(":", 1)[1]
        remove_custom_sound(sid)
    elif eid.startswith("shuffle_sound:"):
        sid = eid.split(":", 1)[1]
        shuffle_custom_folder(sid)
    elif eid.startswith("layer:c_") or eid.startswith("layer:cf_"):
        sid = eid.split(":", 1)[1]
        handle_layer_slider(sid, msg)


@app.on("master_volume")
def handle_master_volume(event):
    global master_volume
    raw_val = event.get("value", 80)
    master_volume = max(0, min(100, int(round(raw_val))))
    audio.set_master_volume(master_volume / 100.0)
    save_state()
    draw()


@app.on("timer_chips")
def handle_timer_chips(event):
    global timer_chip_idx, sleep_timer_seconds, sleep_timer_end
    val = event.get("value", {})
    idx = val.get("index", 0) if isinstance(val, dict) else 0
    if idx < 0 or idx >= len(TIMER_MINUTES):
        idx = 0

    timer_chip_idx = idx
    mins = TIMER_MINUTES[idx]
    if mins > 0:
        sleep_timer_seconds = mins * 60
        sleep_timer_end = time.time() + sleep_timer_seconds
        if is_playing:
            app.badge_ring(1.0, label=f"{mins}m")
    else:
        sleep_timer_seconds = 0
        sleep_timer_end = None
        if is_playing:
            app.badge_glyph("headphones")
        else:
            app.clear_badge()

    draw()


@app.every(1.0)
def tick_sleep_timer():
    global is_playing, sleep_timer_seconds, sleep_timer_end, timer_chip_idx
    # Check folder tracks completion to auto-shuffle to next song
    if is_playing:
        for s in custom_sounds:
            if s.get("type") == "folder" and s.get("vol", 0) > 0:
                sid = s["id"]
                if not audio.is_channel_busy(sid):
                    shuffle_custom_folder(sid)

    if sleep_timer_end:
        rem = sleep_timer_end - time.time()
        if rem <= 0:
            is_playing = False
            audio.set_playing(False)
            sleep_timer_seconds = 0
            sleep_timer_end = None
            timer_chip_idx = 0
            app.active(False)
            app.clear_badge()
            draw()
        else:
            if is_playing and sleep_timer_seconds > 0:
                prog = max(0.0, min(1.0, rem / sleep_timer_seconds))
                mins_rem = int(rem // 60)
                app.badge_ring(prog, label=f"{mins_rem}m" if mins_rem > 0 else "<1m")
            if app.page_open or app.tile_size in ("wide", "large"):
                draw()


@app.on_message("layout")
def handle_layout(msg):
    draw()


@app.on_message("shutdown")
def handle_shutdown(msg):
    save_state()
    audio.stop()


# Initial draw
draw()

if __name__ == "__main__":
    app.run()
