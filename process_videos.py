"""
process_videos.py  --  command-line batch tool (for power users).

Processes every video in a source folder and writes branded copies to an
output folder.  Shares all ffmpeg logic with the GUI via core.py.

Usage:
    python process_videos.py                     # SourceVids -> ModifiedVids
    python process_videos.py IN OUT              # custom folders
    python process_videos.py IN OUT --trim-start 5 --trim-end 3
    python process_videos.py IN OUT --no-branding --trim-start 5

By default it prepends/appends the bundled branding assets (assets/).
Requires ffmpeg/ffprobe (bundled copies in ./ffmpeg are used if present,
otherwise whatever is on PATH).
"""

import argparse
import os
import sys

import core


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepend/append WGU branding to videos, with optional "
                    "trimming of old branding.")
    parser.add_argument("source", nargs="?", default="SourceVids",
                       help="folder of source videos (default: SourceVids)")
    parser.add_argument("output", nargs="?", default="ModifiedVids",
                       help="output folder (default: ModifiedVids)")
    parser.add_argument("--prepend", default=core.default_asset(
        core.DEFAULT_PREPEND_ASSET) or core.DEFAULT_PREPEND_ASSET,
        help="intro image (default: bundled asset)")
    parser.add_argument("--append", default=core.default_asset(
        core.DEFAULT_APPEND_ASSET) or core.DEFAULT_APPEND_ASSET,
        help="outro image (default: bundled asset)")
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
        for asset in (args.prepend, args.append):
            if not os.path.isfile(asset):
                print(f"Error: branding image '{asset}' not found.")
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
                prepend_asset=args.prepend,
                append_asset=args.append,
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
