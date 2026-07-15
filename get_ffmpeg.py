"""
get_ffmpeg.py

Download ffmpeg.exe and ffprobe.exe into the ./ffmpeg folder so the app can
bundle them.  The binaries are ~100 MB each and are intentionally NOT stored
in git -- run this once after cloning, before building the .exe.

    python get_ffmpeg.py

Downloads the "release-essentials" build from gyan.dev (Windows).
"""

import io
import os
import sys
import urllib.request
import zipfile

URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
DEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ffmpeg")
WANTED = ("ffmpeg.exe", "ffprobe.exe")


def main() -> None:
    os.makedirs(DEST, exist_ok=True)

    if all(os.path.isfile(os.path.join(DEST, w)) for w in WANTED):
        print("ffmpeg.exe and ffprobe.exe already present in ./ffmpeg — done.")
        return

    print(f"Downloading ffmpeg from:\n  {URL}\n(this is ~100 MB, please wait) …")
    try:
        with urllib.request.urlopen(URL) as resp:
            data = resp.read()
    except Exception as exc:
        print(f"\nDownload failed: {exc}")
        print("You can download it manually from https://www.gyan.dev/ffmpeg/"
              "builds/ and copy bin\\ffmpeg.exe and bin\\ffprobe.exe into the "
              "'ffmpeg' folder.")
        sys.exit(1)

    print("Extracting …")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            base = os.path.basename(name)
            if base in WANTED and name.endswith("/bin/" + base):
                out = os.path.join(DEST, base)
                with open(out, "wb") as f:
                    f.write(z.read(name))
                print(f"  wrote {out} ({os.path.getsize(out):,} bytes)")

    missing = [w for w in WANTED if not os.path.isfile(os.path.join(DEST, w))]
    if missing:
        print(f"WARNING: could not find {missing} in the archive.")
        sys.exit(1)
    print("Done. You can now build with:  python -m PyInstaller "
          "WGUVideoBrander.spec --noconfirm")


if __name__ == "__main__":
    main()
