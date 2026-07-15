"""
core.py

Shared video-processing logic for the WGU Video Brander.

Both the GUI (gui.py) and the command-line batch tool (process_videos.py)
import from this module so the ffmpeg behaviour is identical everywhere.

For a single video the pipeline can:
  1. (optional) Trim N seconds off the start and/or end  -- used to remove
     old branding that is already baked into the video.
  2. (optional) Prepend a branding image as a short clip.
  3. (optional) Append a branding image as a short clip.
  4. Write the result to the chosen output folder.

Trimming and branding happen in a SINGLE ffmpeg encode pass (the concat
filter re-encodes anyway, so trimming the source stream inside that graph
costs nothing extra and avoids a quality-reducing second encode).

Requires ffmpeg/ffprobe.  The binaries are located via find_ffmpeg():
bundled copies (next to the .exe or inside the PyInstaller bundle) are
preferred, falling back to whatever is on the system PATH.
"""

import json
import os
import shutil
import subprocess
import sys


# ---------------------------------------------------------------------------
# Configuration / constants
# ---------------------------------------------------------------------------

CLIP_DURATION = 5  # seconds each branding clip is shown

VIDEO_EXTENSIONS = (
    ".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".m4v",
)

# Default (baked-in) branding assets.  These live in ./assets and are bundled
# into the .exe.  Power users can override them at run time.
DEFAULT_PREPEND_ASSET = "PrependAsset.png"
DEFAULT_APPEND_ASSET = "AppendAsset.png"

# On Windows we don't want a console window to flash for every ffmpeg call
# when running from the GUI .exe.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


# ---------------------------------------------------------------------------
# Resource / binary location (works both from source and from PyInstaller)
# ---------------------------------------------------------------------------

def resource_dirs() -> list:
    """
    Directories to search for bundled resources, most-specific first.

    Covers all three run modes:
      - PyInstaller one-file: sys._MEIPASS (unpacked temp) AND the folder the
        .exe actually lives in (so users can drop an ffmpeg folder beside it).
      - PyInstaller one-dir: _internal (via _MEIPASS) and the exe folder.
      - From source: the folder containing this file.
    """
    dirs = []
    if getattr(sys, "frozen", False):
        # The .exe's own folder comes FIRST so drop-in overrides (an 'assets'
        # or 'ffmpeg' folder placed next to the app) take priority over the
        # copies baked into the bundle.
        dirs.append(os.path.dirname(sys.executable))
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            dirs.append(meipass)
    else:
        dirs.append(os.path.dirname(os.path.abspath(__file__)))
    # De-duplicate while preserving order.
    seen, out = set(), []
    for d in dirs:
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def app_dir() -> str:
    """Primary resource directory (first of resource_dirs())."""
    return resource_dirs()[0]


def resource_path(*parts: str) -> str:
    """
    Absolute path to a bundled resource.  Returns the first existing match
    across resource_dirs(); falls back to the primary dir if none exists.
    """
    for d in resource_dirs():
        cand = os.path.join(d, *parts)
        if os.path.exists(cand):
            return cand
    return os.path.join(resource_dirs()[0], *parts)


def _find_binary(name: str) -> str:
    """
    Locate an ffmpeg-family binary.

    Order of preference:
      1. Bundled copy in <app_dir>/ffmpeg/<name>[.exe]
      2. Bundled copy directly in <app_dir>/<name>[.exe]
      3. Whatever is found on PATH.
    Returns the resolved path (or just the bare name to defer to PATH).
    """
    exe = name + (".exe" if os.name == "nt" else "")
    candidates = [
        resource_path("ffmpeg", exe),
        resource_path(exe),
    ]
    for cand in candidates:
        if os.path.isfile(cand):
            return cand
    on_path = shutil.which(name)
    return on_path if on_path else name


FFMPEG = _find_binary("ffmpeg")
FFPROBE = _find_binary("ffprobe")


def ffmpeg_available() -> bool:
    """Return True if ffmpeg AND ffprobe can actually be run."""
    for binary in (FFMPEG, FFPROBE):
        try:
            subprocess.run(
                [binary, "-version"],
                capture_output=True, check=True,
                creationflags=_NO_WINDOW,
            )
        except (OSError, subprocess.CalledProcessError):
            return False
    return True


def default_asset(name: str) -> str:
    """
    Return the path to the default branding asset *name*.

    resource_path() searches the .exe's own folder before the bundled copy,
    so an admin can override the placeholders by dropping real images into an
    'assets' folder next to WGUVideoBrander.exe -- no rebuild required.
    Returns '' if not found anywhere.
    """
    p = resource_path("assets", name)
    return p if os.path.isfile(p) else ""


# ---------------------------------------------------------------------------
# Persistent settings (so chosen branding images stick between sessions)
# ---------------------------------------------------------------------------

def config_dir() -> str:
    """Per-user folder for storing settings."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    d = os.path.join(base, "WGUVideoBrander")
    return d


def _settings_path() -> str:
    return os.path.join(config_dir(), "settings.json")


def load_settings() -> dict:
    """Load persisted settings; return {} if none/unreadable."""
    try:
        with open(_settings_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(settings: dict) -> None:
    """Persist *settings* (best-effort; ignores write errors)."""
    try:
        os.makedirs(config_dir(), exist_ok=True)
        with open(_settings_path(), "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except OSError:
        pass


def active_branding() -> tuple:
    """
    Return (prepend_path, append_path) to use as the current branding.

    Preference: a saved custom image (if it still exists) -> the default
    (drop-in override next to the .exe, else the bundled placeholder).
    """
    settings = load_settings()
    result = []
    for key, default_name in (("prepend", DEFAULT_PREPEND_ASSET),
                             ("append", DEFAULT_APPEND_ASSET)):
        saved = settings.get(key)
        if saved and os.path.isfile(saved):
            result.append(saved)
        else:
            result.append(default_asset(default_name))
    return tuple(result)


# ---------------------------------------------------------------------------
# ffprobe helpers
# ---------------------------------------------------------------------------

def get_video_info(video_path: str) -> dict:
    """Return parsed ffprobe JSON for *video_path*."""
    cmd = [
        FFPROBE, "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        video_path,
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, check=True,
        creationflags=_NO_WINDOW,
    )
    return json.loads(result.stdout)


def has_audio_stream(info: dict) -> bool:
    """Return True if the video contains at least one audio stream."""
    return any(s.get("codec_type") == "audio" for s in info.get("streams", []))


def get_video_dimensions(info: dict) -> tuple:
    """Return (width, height) from the first video stream; default 1920x1080."""
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            return int(stream["width"]), int(stream["height"])
    return 1920, 1080


def get_video_fps(info: dict) -> float:
    """Return frames-per-second from the first video stream; default 25."""
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            fps_str = stream.get("r_frame_rate", "25/1")
            try:
                num, den = fps_str.split("/")
                num, den = int(num), int(den)
                if den != 0:
                    return float(num) / den
            except (ValueError, ZeroDivisionError):
                pass
    return 25.0


def get_duration(info: dict) -> float:
    """Return the container duration in seconds; 0.0 if unknown."""
    try:
        return float(info.get("format", {}).get("duration", 0.0))
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# ffmpeg building blocks
# ---------------------------------------------------------------------------

def create_image_clip(
    image_path: str,
    output_path: str,
    width: int,
    height: int,
    fps: float,
    duration: int = CLIP_DURATION,
    include_audio: bool = False,
) -> None:
    """
    Convert a static image into an H.264 video clip.

    The image is scaled (with letterboxing/pillarboxing if needed) to match
    *width* x *height* and held for *duration* seconds at *fps*.  A silent AAC
    track is added when *include_audio* is True so the clip can be
    concatenated with videos that have audio.
    """
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        "format=yuv420p"
    )

    cmd = [FFMPEG, "-y", "-loop", "1", "-framerate", str(fps), "-i", image_path]

    if include_audio:
        cmd += ["-f", "lavfi", "-i",
                "anullsrc=channel_layout=stereo:sample_rate=44100"]

    cmd += [
        "-t", str(duration),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
    ]

    if include_audio:
        cmd += ["-c:a", "aac", "-shortest"]

    cmd.append(output_path)

    subprocess.run(cmd, check=True, capture_output=True, creationflags=_NO_WINDOW)


def _trim_filter(stream: str, out_label: str, is_audio: bool,
                 trim_start: float, trim_end: float, duration: float) -> str:
    """
    Build a trim filter chain for one input stream.

    Returns an ffmpeg filter string like:
        [1:v]trim=start=3:end=57,setpts=PTS-STARTPTS,...[v1]
    *trim_start* seconds are removed from the front and *trim_end* seconds
    from the back (using *duration* to compute the end point).
    """
    trim_name = "atrim" if is_audio else "trim"
    parts = []
    args = []
    if trim_start > 0:
        args.append(f"start={trim_start}")
    if trim_end > 0 and duration > 0:
        end_point = max(trim_start, duration - trim_end)
        args.append(f"end={end_point}")
    if args:
        parts.append(f"{trim_name}=" + ":".join(args))
        parts.append("asetpts=PTS-STARTPTS" if is_audio else "setpts=PTS-STARTPTS")
    return f"[{stream}]" + ",".join(parts) if parts else f"[{stream}]"


def concatenate_videos(
    video_paths: list,
    output_path: str,
    with_audio: bool,
    trim_index: int = -1,
    trim_start: float = 0.0,
    trim_end: float = 0.0,
    duration: float = 0.0,
) -> None:
    """
    Concatenate *video_paths* in order using ffmpeg's concat filter.

    All video streams are normalised to yuv420p / SAR 1:1 and all audio
    streams to fltp / 44100 Hz / stereo before concatenation so the concat
    filter never sees mismatched parameters.

    If *trim_index* >= 0, the input at that position is trimmed by
    *trim_start* / *trim_end* seconds (using *duration*) as part of the SAME
    encode pass -- this is how "remove old branding" is applied to the source
    video without a separate re-encode.
    """
    inputs = []
    for path in video_paths:
        inputs += ["-i", path]

    n = len(video_paths)
    filter_parts = []

    for i in range(n):
        do_trim = (i == trim_index and (trim_start > 0 or trim_end > 0))
        # --- video ---
        if do_trim:
            head = _trim_filter(f"{i}:v", "", False, trim_start, trim_end, duration)
            filter_parts.append(f"{head},format=yuv420p,setsar=1[v{i}]")
        else:
            filter_parts.append(f"[{i}:v]format=yuv420p,setsar=1[v{i}]")
        # --- audio ---
        if with_audio:
            afmt = ("aformat=sample_fmts=fltp"
                    ":sample_rates=44100:channel_layouts=stereo")
            if do_trim:
                head = _trim_filter(f"{i}:a", "", True,
                                    trim_start, trim_end, duration)
                filter_parts.append(f"{head},{afmt}[a{i}]")
            else:
                filter_parts.append(f"[{i}:a]{afmt}[a{i}]")

    if with_audio:
        concat_in = "".join(f"[v{i}][a{i}]" for i in range(n))
        filter_parts.append(f"{concat_in}concat=n={n}:v=1:a=1[outv][outa]")
        maps = ["-map", "[outv]", "-map", "[outa]"]
        acodec = ["-c:a", "aac", "-ar", "44100", "-ac", "2"]
    else:
        concat_in = "".join(f"[v{i}]" for i in range(n))
        filter_parts.append(f"{concat_in}concat=n={n}:v=1:a=0[outv]")
        maps = ["-map", "[outv]"]
        acodec = []

    filter_complex = ";".join(filter_parts)
    cmd = (
        [FFMPEG, "-y"] + inputs
        + ["-filter_complex", filter_complex]
        + maps
        + ["-c:v", "libx264", "-preset", "fast", "-crf", "23"]
        + acodec
        + [output_path]
    )
    subprocess.run(cmd, check=True, capture_output=True, creationflags=_NO_WINDOW)


def trim_only(
    video_path: str,
    output_path: str,
    trim_start: float,
    trim_end: float,
    info: dict,
) -> None:
    """
    Trim a video without adding branding (single re-encode pass).

    Removes *trim_start* seconds from the front and *trim_end* from the back.
    """
    width, height = get_video_dimensions(info)
    fps = get_video_fps(info)
    audio = has_audio_stream(info)
    duration = get_duration(info)
    # Reuse the concat machinery with a single input that gets trimmed.
    concatenate_videos(
        [video_path], output_path, with_audio=audio,
        trim_index=0, trim_start=trim_start, trim_end=trim_end,
        duration=duration,
    )


# ---------------------------------------------------------------------------
# High-level: process one video
# ---------------------------------------------------------------------------

class ProcessError(Exception):
    """Raised when processing a single video fails, with a friendly message."""


def process_video(
    input_path: str,
    output_path: str,
    *,
    add_branding: bool = True,
    prepend_asset: str = "",
    append_asset: str = "",
    trim_start: float = 0.0,
    trim_end: float = 0.0,
    clip_duration: int = CLIP_DURATION,
    log=lambda msg: None,
    tempdir: str = None,
) -> None:
    """
    Process a single video: optional trim + optional branding.

    Parameters
    ----------
    input_path, output_path : source and destination file paths.
    add_branding : prepend/append the branding image clips.
    prepend_asset, append_asset : branding images (required if add_branding).
    trim_start, trim_end : seconds to cut from start / end (0 = no trim).
    clip_duration : length of each branding clip in seconds.
    log : callback taking a status string (for progress display).
    tempdir : where to write intermediate clips (defaults to output folder).

    Raises
    ------
    ProcessError on any failure, with a human-readable message.
    """
    import tempfile

    if not add_branding and trim_start <= 0 and trim_end <= 0:
        raise ProcessError(
            "Nothing to do: enable branding and/or set a trim amount."
        )

    try:
        info = get_video_info(input_path)
    except subprocess.CalledProcessError:
        raise ProcessError(f"Could not read video (is it a valid file?): "
                           f"{os.path.basename(input_path)}")

    width, height = get_video_dimensions(info)
    fps = get_video_fps(info)
    audio = has_audio_stream(info)
    duration = get_duration(info)

    log(f"  {width}x{height} @ {fps:.2f} fps, "
        f"audio: {'yes' if audio else 'no'}, "
        f"{duration:.1f}s")

    if (trim_start + trim_end) >= duration > 0:
        raise ProcessError(
            f"Trim amount ({trim_start + trim_end}s) is longer than the "
            f"video ({duration:.1f}s)."
        )

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    try:
        if not add_branding:
            # Trim-only path.
            log("  Trimming …")
            trim_only(input_path, output_path, trim_start, trim_end, info)
            log(f"  Saved -> {output_path}")
            return

        # Branding path (with optional trim folded into the concat pass).
        for asset, label in ((prepend_asset, "prepend"),
                             (append_asset, "append")):
            if not asset or not os.path.isfile(asset):
                raise ProcessError(f"Branding image not found: {asset}")

        base_tmp = tempdir or os.path.dirname(os.path.abspath(output_path))
        with tempfile.TemporaryDirectory(dir=base_tmp) as tmpdir:
            prepend_clip = os.path.join(tmpdir, "prepend.mp4")
            append_clip = os.path.join(tmpdir, "append.mp4")

            log(f"  Building {clip_duration}s intro/outro …")
            create_image_clip(prepend_asset, prepend_clip, width, height, fps,
                             duration=clip_duration, include_audio=audio)
            create_image_clip(append_asset, append_clip, width, height, fps,
                             duration=clip_duration, include_audio=audio)

            if trim_start > 0 or trim_end > 0:
                log(f"  Trimming (-{trim_start}s start, -{trim_end}s end) "
                    f"and adding branding …")
            else:
                log("  Adding branding …")

            # The source video is input index 1 (prepend=0, source=1, append=2).
            concatenate_videos(
                [prepend_clip, input_path, append_clip],
                output_path,
                with_audio=audio,
                trim_index=1,
                trim_start=trim_start,
                trim_end=trim_end,
                duration=duration,
            )

        log(f"  Saved -> {output_path}")

    except subprocess.CalledProcessError as exc:
        stderr = ""
        if exc.stderr:
            stderr = (exc.stderr.decode(errors="replace")
                      if isinstance(exc.stderr, bytes) else str(exc.stderr))
        tail = "\n    ".join(stderr.strip().splitlines()[-15:])
        raise ProcessError(
            f"ffmpeg failed on {os.path.basename(input_path)}.\n    {tail}"
        )


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------

def is_video_file(path: str) -> bool:
    """True if *path* is a file with a supported video extension."""
    return (os.path.isfile(path)
            and os.path.splitext(path)[1].lower() in VIDEO_EXTENSIONS)


def collect_videos(paths) -> list:
    """
    Expand a mix of file and folder *paths* into a de-duplicated, sorted list
    of video files.  Folders are searched one level deep (non-recursive) by
    default; pass individual files for anything else.
    """
    found = []
    seen = set()

    def add(p):
        ap = os.path.abspath(p)
        key = os.path.normcase(ap)
        if key not in seen and is_video_file(ap):
            seen.add(key)
            found.append(ap)

    for p in paths:
        if os.path.isdir(p):
            for name in sorted(os.listdir(p)):
                add(os.path.join(p, name))
        else:
            add(p)

    return sorted(found)
