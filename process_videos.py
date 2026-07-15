"""
process_videos.py  --  command-line batch tool (for power users).

Processes every video in a source folder and writes branded copies to an
output folder.  Shares all ffmpeg/rendering logic with the GUI via core.py.

Usage:
    python process_videos.py                       # SourceVids -> ModifiedVids
    python process_videos.py IN OUT                # custom folders
    python process_videos.py IN OUT --course-title "C949 - Data Structures"
    python process_videos.py IN OUT --video-title "Overview" --course-title "C949"
    python process_videos.py IN OUT --trim-start 5 --trim-end 3
    python process_videos.py IN OUT --no-branding --trim-start 5

By default it renders the WGU title-slide intro (drawing the given titles onto
it) and appends the WGU outro.  In batch mode the same titles are applied to
every video; use the GUI for per-video titles.  Requires ffmpeg/ffprobe
(bundled copies in ./ffmpeg are used if present, otherwise PATH).
"""

import argparse
import os
import sys

import core


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add WGU branding (title-slide intro + outro) to videos, "
                    "with optional trimming of old branding.")
    parser.add_argument("source", nargs="?", default="SourceVids",
                       help="folder of source videos (default: SourceVids)")
    parser.add_argument("output", nargs="?", default="ModifiedVids",
                       help="output folder (default: ModifiedVids)")
    parser.add_argument("--video-title", default="",
                       help="video title drawn on every intro (optional)")
    parser.add_argument("--course-title", default="",
                       help="course title drawn on every intro (optional)")
    parser.add_argument("--intro-template", default=core.intro_template_path(),
                       help="intro background image (default: bundled WGU slide)")
    parser.add_argument("--append", default=core.active_branding()[1]
                       or core.DEFAULT_APPEND_ASSET,
                       help="outro image (default: bundled WGU slide)")
    parser.add_argument("--no-branding", action="store_true",
                       help="do not add branding (trim only)")
    parser.add_argument("--trim-start", type=float, default=0.0,
                       help="seconds to remove from the start")
    parser.add_argument("--trim-end", type=float, default=0.0,
                       help="seconds to remove from the end")
    args = parser.parse_args()

    if not core.ffmpeg_available():
        print("Error: ffmpeg/ffprobe not found. Install ffmpeg or place "
              "ffmpeg.exe/ffprobe.exe in the 'ffmpeg' folder.")
        sys.exit(1)

    add_branding = not args.no_branding

    if not os.path.isdir(args.source):
        print(f"Error: source directory '{args.source}' not found.")
        sys.exit(1)

    if add_branding:
        if not os.path.isfile(args.intro_template):
            print(f"Error: intro template '{args.intro_template}' not found.")
            sys.exit(1)
        if not os.path.isfile(args.append):
            print(f"Error: outro image '{args.append}' not found.")
            sys.exit(1)

    videos = core.collect_videos([args.source])
    if not videos:
        print(f"No supported video files found in '{args.source}'.")
        print(f"Supported: {', '.join(core.VIDEO_EXTENSIONS)}")
        sys.exit(0)

    print(f"Found {len(videos)} video file(s) to process.\n")
    os.makedirs(args.output, exist_ok=True)

    ok = fail = skip = 0
    for i, video in enumerate(videos, 1):
        name = os.path.basename(video)
        out = os.path.join(args.output, name)
        print(f"[{i}/{len(videos)}] Processing: {name}")

        if os.path.isfile(out):
            print(f"  Skipping — output already exists: {out}\n")
            skip += 1
            continue

        try:
            core.process_video(
                video, out,
                add_branding=add_branding,
                intro_template=args.intro_template,
                append_asset=args.append,
                video_title=args.video_title,
                course_title=args.course_title,
                trim_start=args.trim_start,
                trim_end=args.trim_end,
                log=print,
            )
            print()
            ok += 1
        except core.ProcessError as exc:
            fail += 1
            print(f"  ERROR: {exc}\n")

    print("=" * 50)
    print(f"Done. {ok} succeeded, {fail} failed, {skip} skipped.")
    if ok:
        print(f"Modified videos are in '{args.output}'.")


if __name__ == "__main__":
    main()
