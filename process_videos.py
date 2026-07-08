"""
process_videos.py

For every video file found in ./SourceVids, this script:
  1. Converts ./PrependAsset.png into a 5-second video clip.
  2. Prepends that clip to the source video.
  3. Converts ./AppendAsset.png into a 5-second video clip.
  4. Appends that clip to the end of the source video.
  5. Writes the result (same filename) to ./ModifiedVids.

Requirements: Python 3.6+ and ffmpeg/ffprobe available on PATH.
"""

import glob
import json
import os
import subprocess
import sys
import tempfile


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SOURCE_DIR = "SourceVids"
OUTPUT_DIR = "ModifiedVids"
PREPEND_ASSET = "PrependAsset.png"
APPEND_ASSET = "AppendAsset.png"
CLIP_DURATION = 5  # seconds

VIDEO_EXTENSIONS = (
    ".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".m4v",
    ".MP4", ".AVI", ".MOV", ".MKV", ".WMV", ".FLV", ".M4V",
)


# ---------------------------------------------------------------------------
# ffprobe helpers
# ---------------------------------------------------------------------------

def get_video_info(video_path: str) -> dict:
    """Return parsed ffprobe JSON for *video_path*."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
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
            num, den = fps_str.split("/")
            den = int(den)
            return float(num) / den if den else 25.0
    return 25.0


# ---------------------------------------------------------------------------
# ffmpeg helpers
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
    Convert a static PNG image into an H.264 video clip.

    The image is scaled (with letterboxing/pillarboxing if needed) to match
    *width* x *height* and held for *duration* seconds at *fps*.
    A silent AAC track is added when *include_audio* is True so the clip
    can be concatenated with videos that have audio.
    """
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        "format=yuv420p"
    )

    cmd = ["ffmpeg", "-y", "-loop", "1", "-framerate", str(fps), "-i", image_path]

    if include_audio:
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]

    cmd += [
        "-t", str(duration),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
    ]

    if include_audio:
        cmd += ["-c:a", "aac", "-shortest"]

    cmd.append(output_path)

    subprocess.run(cmd, check=True, capture_output=True)


def concatenate_videos(
    video_paths: list,
    output_path: str,
    with_audio: bool,
) -> None:
    """
    Concatenate *video_paths* in order using ffmpeg's concat filter.

    When *with_audio* is True, audio streams are merged as well.
    """
    inputs = []
    for path in video_paths:
        inputs += ["-i", path]

    n = len(video_paths)

    if with_audio:
        filter_inputs = "".join(f"[{i}:v][{i}:a]" for i in range(n))
        filter_complex = f"{filter_inputs}concat=n={n}:v=1:a=1[outv][outa]"
        cmd = (
            ["ffmpeg", "-y"]
            + inputs
            + [
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-map", "[outa]",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac",
                output_path,
            ]
        )
    else:
        filter_inputs = "".join(f"[{i}:v]" for i in range(n))
        filter_complex = f"{filter_inputs}concat=n={n}:v=1:a=0[outv]"
        cmd = (
            ["ffmpeg", "-y"]
            + inputs
            + [
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                output_path,
            ]
        )

    subprocess.run(cmd, check=True, capture_output=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # --- Validate required assets ----------------------------------------
    for asset in (PREPEND_ASSET, APPEND_ASSET):
        if not os.path.isfile(asset):
            print(f"Error: required asset '{asset}' not found in the current directory.")
            sys.exit(1)

    if not os.path.isdir(SOURCE_DIR):
        print(f"Error: source directory '{SOURCE_DIR}' not found.")
        sys.exit(1)

    # --- Discover video files ---------------------------------------------
    video_files = [
        f
        for f in glob.glob(os.path.join(SOURCE_DIR, "*"))
        if os.path.splitext(f)[1] in VIDEO_EXTENSIONS
    ]

    if not video_files:
        print(f"No supported video files found in '{SOURCE_DIR}/'.")
        print(f"Supported extensions: {', '.join(sorted(set(VIDEO_EXTENSIONS)))}")
        sys.exit(0)

    print(f"Found {len(video_files)} video file(s) to process.\n")

    # --- Create output directory ------------------------------------------
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # --- Process each video -----------------------------------------------
    success_count = 0
    error_count = 0

    for video_path in sorted(video_files):
        filename = os.path.basename(video_path)
        output_path = os.path.join(OUTPUT_DIR, filename)

        print(f"[{success_count + error_count + 1}/{len(video_files)}] Processing: {filename}")

        try:
            info = get_video_info(video_path)
            width, height = get_video_dimensions(info)
            fps = get_video_fps(info)
            audio = has_audio_stream(info)

            print(f"  Resolution : {width}x{height}")
            print(f"  Frame rate : {fps:.3f} fps")
            print(f"  Audio      : {'yes' if audio else 'no'}")

            with tempfile.TemporaryDirectory() as tmpdir:
                prepend_clip = os.path.join(tmpdir, "prepend.mp4")
                append_clip = os.path.join(tmpdir, "append.mp4")

                print(f"  Creating {CLIP_DURATION}s prepend clip from '{PREPEND_ASSET}' …")
                create_image_clip(
                    PREPEND_ASSET, prepend_clip, width, height, fps,
                    duration=CLIP_DURATION, include_audio=audio,
                )

                print(f"  Creating {CLIP_DURATION}s append clip from '{APPEND_ASSET}' …")
                create_image_clip(
                    APPEND_ASSET, append_clip, width, height, fps,
                    duration=CLIP_DURATION, include_audio=audio,
                )

                print("  Concatenating clips …")
                concatenate_videos(
                    [prepend_clip, video_path, append_clip],
                    output_path,
                    with_audio=audio,
                )

            print(f"  Saved → {output_path}\n")
            success_count += 1

        except subprocess.CalledProcessError as exc:
            error_count += 1
            print(f"  ERROR processing '{filename}'.")
            stderr = exc.stderr.decode(errors="replace") if exc.stderr else ""
            if stderr:
                # Show only the last few lines to keep output readable
                last_lines = stderr.strip().splitlines()[-5:]
                print("  ffmpeg output (last lines):\n    " + "\n    ".join(last_lines))
            print()

    # --- Summary ----------------------------------------------------------
    print("=" * 50)
    print(f"Done. {success_count} succeeded, {error_count} failed.")
    if success_count:
        print(f"Modified videos are in './{OUTPUT_DIR}/'.")


if __name__ == "__main__":
    main()
