# VideoPrependAppend

Automatically prepends and appends a 5-second image clip to every video in a
folder.  
For each video in `./SourceVids`, the script:

1. Converts `PrependAsset.png` → 5-second video clip
2. Prepends that clip to the source video
3. Converts `AppendAsset.png` → 5-second video clip
4. Appends that clip to the end of the source video
5. Saves the combined video (same filename) to `./ModifiedVids`

---

## Requirements

| Requirement | Version |
|---|---|
| Python | 3.6 or later |
| ffmpeg / ffprobe | Any recent release |

> **No Python packages need to be installed** — the script only uses the
> standard library.  
> ffmpeg must be installed separately and available on your system `PATH`.

---

## 1 — Install ffmpeg (Windows)

### Option A — winget (Windows 10/11, recommended)

```powershell
winget install --id Gyan.FFmpeg -e
```

After installation, **close and reopen your terminal** so `PATH` is refreshed.

### Option B — Manual download

1. Go to <https://www.gyan.dev/ffmpeg/builds/> and download the latest
   **ffmpeg-release-essentials.zip**.
2. Extract the archive (e.g. to `C:\ffmpeg`).
3. Add `C:\ffmpeg\bin` to your system `PATH`:
   - Open **Start → "Edit the system environment variables"**.
   - Click **Environment Variables**.
   - Under **System variables**, select `Path` → **Edit** → **New**.
   - Type `C:\ffmpeg\bin` and click **OK** on all dialogs.
4. Open a **new** terminal and verify:

```powershell
ffmpeg -version
```

---

## 2 — Verify Python is installed

```powershell
python --version
```

If Python is not found, download the installer from <https://www.python.org/downloads/>  
and make sure **"Add Python to PATH"** is checked during installation.

---

## 3 — Set up the project

```powershell
# 1. Clone (or download) this repository
git clone https://github.com/TCAS1989/VideoPrependAppend.git
cd VideoPrependAppend

# 2. Place your image assets in the root of the project:
#      PrependAsset.png   ← shown at the START of every video
#      AppendAsset.png    ← shown at the END of every video

# 3. Copy your source videos into the SourceVids folder:
#      SourceVids\video1.mp4
#      SourceVids\clip2.mov
#      ...
```

### Supported video formats

`.mp4`, `.avi`, `.mov`, `.mkv`, `.wmv`, `.flv`, `.m4v`

---

## 4 — Run the script

```powershell
python process_videos.py
```

### Example output

```
Found 3 video file(s) to process.

[1/3] Processing: intro_clip.mp4
  Resolution : 1920x1080
  Frame rate : 29.970 fps
  Audio      : yes
  Creating 5s prepend clip from 'PrependAsset.png' …
  Creating 5s append clip from 'AppendAsset.png' …
  Concatenating clips …
  Saved → ModifiedVids\intro_clip.mp4

...

==================================================
Done. 3 succeeded, 0 failed.
Modified videos are in './ModifiedVids/'.
```

---

## Project structure

```
VideoPrependAppend/
├── process_videos.py     ← main script
├── PrependAsset.png      ← your prepend image (user-provided)
├── AppendAsset.png       ← your append image (user-provided)
├── SourceVids/           ← place source videos here
│   └── example.mp4
└── ModifiedVids/         ← processed videos are written here
    └── example.mp4
```

---

## Notes

- The script re-encodes all videos to **H.264 / AAC** (MP4 container).
  Original files in `SourceVids` are **never modified**.
- Image assets are scaled to match each video's resolution with
  letterboxing/pillarboxing to avoid distortion.
- If a source video has no audio track, the appended/prepended clips will
  also have no audio so the concat remains consistent.
- Processing time depends on the length and resolution of the source videos.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `'ffmpeg' is not recognized` | Ensure ffmpeg is installed and `C:\ffmpeg\bin` is in your PATH, then reopen your terminal. |
| `Error: required asset 'PrependAsset.png' not found` | Make sure `PrependAsset.png` is in the same folder as `process_videos.py`. |
| `No supported video files found in 'SourceVids/'` | Check that your videos are in the `SourceVids` folder and have a supported extension. |
| Output video has wrong resolution | The script matches each source video's resolution automatically — no action needed. |
