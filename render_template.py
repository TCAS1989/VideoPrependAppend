"""
render_template.py  --  regenerate the branding images from the WGU .pptx.

Slide 2 (the title slide, with its text boxes left EMPTY) becomes
assets/intro_template.png -- the app draws each video's Video Title / Course
Title onto it at run time.  Slide 4 (the end slide) becomes
assets/AppendAsset.png -- the static outro.

Run this only when the WGU PowerPoint template changes:

    python render_template.py ["path\\to\\template.pptx"]

Requires Microsoft PowerPoint installed (used via COM automation) and pywin32.
This is a BUILD-TIME tool; end users never run it -- the app ships the
already-rendered PNGs.
"""

import os
import shutil
import sys

DEFAULT_PPTX = "template/WGU Video Template - Instructor Resources.pptx"
INTRO_SLIDE = 2      # title slide (Video Title + Course Title placeholders)
OUTRO_SLIDE = 4      # end slide (static)
WIDTH, HEIGHT = 1920, 1080


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    pptx = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, DEFAULT_PPTX)
    pptx = os.path.abspath(pptx)
    if not os.path.isfile(pptx):
        print(f"Error: PowerPoint template not found:\n  {pptx}")
        print("Pass the path as an argument, or place it at "
              f"{DEFAULT_PPTX}.")
        sys.exit(1)

    try:
        import win32com.client as win32
    except ImportError:
        print("Error: pywin32 is required. Install it with:\n"
              "  python -m pip install pywin32")
        sys.exit(1)

    assets = os.path.join(here, "assets")
    os.makedirs(assets, exist_ok=True)
    intro_out = os.path.join(assets, "intro_template.png")
    outro_out = os.path.join(assets, "AppendAsset.png")

    # Work on a copy so we never touch the original (and it may be open).
    tmp = os.path.join(os.environ.get("TEMP", here), "_wgu_render_copy.pptx")
    shutil.copyfile(pptx, tmp)

    print("Opening PowerPoint…")
    app = win32.Dispatch("PowerPoint.Application")
    app.Visible = True
    pres = app.Presentations.Open(tmp, ReadOnly=True, Untitled=False,
                                  WithWindow=False)
    try:
        n = pres.Slides.Count
        if n < max(INTRO_SLIDE, OUTRO_SLIDE):
            print(f"Error: template has only {n} slides; expected at least "
                  f"{max(INTRO_SLIDE, OUTRO_SLIDE)}.")
            sys.exit(1)
        print(f"Exporting slide {INTRO_SLIDE} -> {intro_out}")
        pres.Slides(INTRO_SLIDE).Export(intro_out, "PNG", WIDTH, HEIGHT)
        print(f"Exporting slide {OUTRO_SLIDE} -> {outro_out}")
        pres.Slides(OUTRO_SLIDE).Export(outro_out, "PNG", WIDTH, HEIGHT)
    finally:
        pres.Close()
    try:
        os.remove(tmp)
    except OSError:
        pass

    print("\nDone. If the title/subtitle position, font, or size changed in the "
          "template, update the INTRO_* constants in core.py to match.")


if __name__ == "__main__":
    main()
