# WGU Video Brander

Add WGU branding (a short intro + outro) to videos — and, when needed, trim
old branding off the start or end first.

There are two ways to use it:

- **The app (`WGUVideoBrander.exe`)** — a simple click-and-run window for
  everyone. **No Python, no command line, no ffmpeg install.** Just download,
  double-click, drag in your videos, and press **Start**.
- **The command-line tool (`process_videos.py`)** — for power users who want to
  batch-process folders or script the process.

Both share the same video engine (`core.py`), so the results are identical.

![The WGU Video Brander app: drag-and-drop area, branding and trim options, and a progress log](docs/screenshot.png)

---

## Download

Grab the latest **`WGUVideoBrander.zip`** from the
[**Releases**](../../releases) page, unzip it anywhere, and run
`WGUVideoBrander.exe`. Nothing else to install.

---

## For most people: using the app

1. Get the **`WGUVideoBrander`** folder (from your IT/admin, or build it —
   see below). Keep the folder together.
2. Double-click **`WGUVideoBrander.exe`**.
   - First launch may be a little slow, and Windows SmartScreen/antivirus may
     ask you to confirm an unrecognized app — click **More info → Run anyway**.
3. **Add your videos** one of two ways:
   - **Drag and drop** video files (or a whole folder) onto the drop area, or
   - Click **Add file(s)…** / **Add folder…**.
4. Choose what to do:
   - ☑ **Add WGU branding** — puts the WGU intro before and outro after each
     video (on by default).
   - ☐ **Trim old branding first** — turn this on only if the video already has
     old branding to remove. Enter how many **seconds to cut off the start**
     and/or **off the end**.
5. Press **Start**. Progress shows in the log at the bottom.
6. By default, finished videos are saved into a **`Branded`** folder next to
   each source video. (You can pick a different output folder in **Options**.)

### Advanced: custom branding images

The app ships with the WGU intro/outro built in. To use different images,
expand **Branding images (advanced)** in Options and choose your own intro and
outro image (PNG/JPG). These are shown full-screen for 5 seconds each.

### Supported video formats

`.mp4`, `.avi`, `.mov`, `.mkv`, `.wmv`, `.flv`, `.m4v`

---

## For power users: the command line

Requires **Python 3.6+**. ffmpeg is used from the bundled `ffmpeg/` folder if
present, otherwise from your system `PATH`.

```powershell
# Brand every video in SourceVids -> ModifiedVids (bundled WGU assets)
python process_videos.py

# Custom in/out folders
python process_videos.py "C:\clips" "C:\clips\out"

# Brand AND trim 5s off the start, 3s off the end
python process_videos.py "C:\clips" "C:\out" --trim-start 5 --trim-end 3

# Trim only, no branding
python process_videos.py "C:\clips" "C:\out" --no-branding --trim-start 5

# Use custom branding images
python process_videos.py --prepend intro.png --append outro.png
```

Run `python process_videos.py --help` for all options.

---

## Building the app (`.exe`) yourself

You only need to do this to (re)create the distributable app — for example
after dropping in the **real WGU branding images**.

### One-time setup

```powershell
# 1. Install build dependencies
python -m pip install -r requirements.txt

# 2. Download the ffmpeg binaries that get bundled (~100 MB each).
#    These are NOT stored in git.
python get_ffmpeg.py
```

### Put in the real branding images (optional)

Replace the placeholder images in **`assets/`** with the official WGU art,
keeping the same filenames:

```
assets\PrependAsset.png   <- shown at the START of every video
assets\AppendAsset.png    <- shown at the END of every video
```

Full-HD (1920×1080) PNGs work best; the app scales them to match each video.

### Build

```powershell
# Easiest: run everything at once
build.bat

# ...or manually:
python -m PyInstaller WGUVideoBrander.spec --noconfirm
```

The finished app appears in **`dist\WGUVideoBrander\`**. Zip that folder (or
share it as-is) and hand it to users — everything they need, including ffmpeg,
is inside.

---

## Project structure

```
VideoPrependAppend/
├── gui.py                  ← the desktop app (window, drag & drop)
├── core.py                 ← shared ffmpeg engine (trim + branding)
├── process_videos.py       ← command-line batch tool
├── get_ffmpeg.py           ← downloads ffmpeg for bundling
├── build.bat               ← one-click build script
├── WGUVideoBrander.spec    ← PyInstaller build recipe
├── requirements.txt
├── assets/                 ← default branding images (bundled into the app)
│   ├── PrependAsset.png
│   └── AppendAsset.png
├── ffmpeg/                 ← ffmpeg.exe / ffprobe.exe (fetched, not in git)
├── SourceVids/             ← optional: source videos for the CLI
└── ModifiedVids/           ← optional: CLI output
```

---

## How it works

- Each video is (optionally) **trimmed** and then gets a **5-second intro**
  prepended and a **5-second outro** appended, in a **single re-encode pass**
  (so trimming adds no extra quality loss).
- Everything is re-encoded to **H.264 / AAC** in an MP4 container. Source files
  are **never modified**.
- Branding images are scaled to each video's resolution with
  letterboxing/pillarboxing so nothing is distorted.
- If a source video has no audio, the intro/outro are silent to match, so the
  join stays clean.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Windows warns about an unrecognized app | Click **More info → Run anyway** (the app is unsigned). |
| App says ffmpeg was not found (from source) | Run `python get_ffmpeg.py`, or put `ffmpeg.exe`/`ffprobe.exe` in the `ffmpeg` folder. |
| "Trim amount is longer than the video" | Reduce the seconds you're trimming off the start/end. |
| Branding image not found | Expand **Branding images (advanced)** and pick valid image files, or rebuild after placing them in `assets/`. |
| Output looks wrong / no branding | Make sure at least one of **Add WGU branding** or **Trim** is turned on. |
