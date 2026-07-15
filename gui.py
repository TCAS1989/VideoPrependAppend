"""
gui.py  --  WGU Video Brander (desktop app)

A click-and-run window for non-technical staff:
  * Drag-and-drop video files or folders onto the drop area, OR use the
    Browse buttons.
  * "Add WGU branding" (on by default) prepends a WGU title slide (intro) and
    appends the WGU end slide (outro).
  * Per video you can set a Video Title and Course Title that are drawn onto
    the intro slide (both optional). A shared "Course title" box fills every
    row at once; edit any row to override it.
  * "Trim old branding first" (off by default) removes N seconds from the
    start and/or end -- used when a video already has old branding baked in.
  * Processing runs on a background thread so the window stays responsive.

The intro/outro artwork comes from the WGU PowerPoint template, pre-rendered
to images in assets/. Everything ffmpeg-related lives in core.py; ffmpeg is
bundled inside the .exe, so end users install nothing.
"""

import os
import queue
import threading
import traceback

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import core

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _DND = True
except Exception:  # pragma: no cover - drag/drop is optional
    _DND = False


APP_TITLE = "WGU Video Brander"

# WGU-ish palette
BG = "#0f2233"
PANEL = "#16324a"
ACCENT = "#0a7abf"
ACCENT_HOVER = "#0b8ad6"
TEXT = "#eaf1f7"
MUTED = "#9fb3c8"
DROP_IDLE = "#1d3e5a"
DROP_HOVER = "#24537a"
FIELD_BG = "#0a1826"


def _parse_drop(data: str) -> list:
    """Parse the space/brace-delimited path string tkinterdnd2 provides."""
    paths, token, in_brace = [], "", False
    for ch in data:
        if ch == "{":
            in_brace, token = True, ""
        elif ch == "}":
            in_brace = False
            paths.append(token)
            token = ""
        elif ch == " " and not in_brace:
            if token:
                paths.append(token)
                token = ""
        else:
            token += ch
    if token:
        paths.append(token)
    return [p for p in paths if p]


class BranderApp:
    def __init__(self, root):
        self.root = root
        root.title(APP_TITLE)
        root.geometry("800x860")
        root.minsize(720, 720)
        root.configure(bg=BG)

        # State ------------------------------------------------------------
        self.selected_paths = []            # files/folders the user added
        self.video_rows = {}                # path -> {vtitle, ctitle, dirty}
        self.shared_course = tk.StringVar()

        self.intro_template = tk.StringVar(value=core.intro_template_path())
        _, saved_outro = core.active_branding()
        self.outro_path = tk.StringVar(value=saved_outro)

        self.add_branding = tk.BooleanVar(value=True)
        self.do_trim = tk.BooleanVar(value=False)
        self.trim_start = tk.StringVar(value="5")
        self.trim_end = tk.StringVar(value="0")
        self.output_mode = tk.StringVar(value="beside")  # 'beside' or 'custom'
        self.custom_output = tk.StringVar(value="")

        self._log_queue = queue.Queue()
        self._worker = None

        self._build_ui()
        self.shared_course.trace_add("write", self._on_shared_course)
        self._poll_log()
        self._check_ffmpeg()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        pad = dict(padx=14, pady=5)

        tk.Label(self.root, text=APP_TITLE, bg=BG, fg=TEXT,
                 font=("Segoe UI Semibold", 20)).pack(
            anchor="w", padx=14, pady=(10, 0))
        tk.Label(self.root,
                 text="Add WGU branding to videos, set each video's title, and "
                      "optionally trim old branding off first.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(
            anchor="w", padx=14, pady=(0, 6))

        # --- Drop / select area ------------------------------------------
        self.drop = tk.Frame(self.root, bg=DROP_IDLE, height=90,
                             highlightbackground=ACCENT, highlightthickness=2)
        self.drop.pack(fill="x", **pad)
        self.drop.pack_propagate(False)
        dnd_hint = ("Drag videos or a folder here"
                    if _DND else "Use the buttons below to add videos")
        self.drop_label = tk.Label(self.drop, text=f"⬇  {dnd_hint}",
                                   bg=DROP_IDLE, fg=TEXT, font=("Segoe UI", 13))
        self.drop_label.pack(expand=True)
        self.drop_sub = tk.Label(self.drop, text="No videos added yet",
                                 bg=DROP_IDLE, fg=MUTED, font=("Segoe UI", 9))
        self.drop_sub.pack(pady=(0, 8))

        if _DND:
            for w in (self.drop, self.drop_label, self.drop_sub):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._on_drop)
                w.dnd_bind("<<DragEnter>>", lambda e: self._drop_color(DROP_HOVER))
                w.dnd_bind("<<DragLeave>>", lambda e: self._drop_color(DROP_IDLE))

        btns = tk.Frame(self.root, bg=BG)
        btns.pack(fill="x", padx=14)
        self._mkbtn(btns, "Add file(s)…", self._browse_files).pack(side="left")
        self._mkbtn(btns, "Add folder…", self._browse_folder).pack(
            side="left", padx=(8, 0))
        self._mkbtn(btns, "Clear", self._clear_paths, subtle=True).pack(
            side="right")

        # --- Per-video titles --------------------------------------------
        self._build_titles_panel(pad)

        # --- Options ------------------------------------------------------
        self._build_options(pad)

        # --- Action + progress -------------------------------------------
        action = tk.Frame(self.root, bg=BG)
        action.pack(fill="x", padx=14, pady=(2, 4))
        self.start_btn = self._mkbtn(action, "Start", self._start, big=True)
        self.start_btn.pack(side="left")
        self.progress = ttk.Progressbar(action, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=(12, 0))

        self.log = tk.Text(self.root, height=6, bg=FIELD_BG, fg=TEXT,
                          insertbackground=TEXT, font=("Consolas", 9),
                          bd=0, wrap="word")
        self.log.pack(fill="both", expand=True, padx=14, pady=(4, 12))
        self.log.configure(state="disabled")

        self._sync_enable()

    def _build_titles_panel(self, pad):
        frame = tk.LabelFrame(self.root, text=" Video titles ", bg=BG, fg=MUTED,
                             font=("Segoe UI", 10), bd=1, relief="groove")
        frame.pack(fill="both", expand=False, **pad)

        shared = tk.Frame(frame, bg=BG)
        shared.pack(fill="x", padx=10, pady=(8, 4))
        tk.Label(shared, text="Course title (all videos):", bg=BG, fg=TEXT,
                 font=("Segoe UI", 10)).pack(side="left")
        tk.Entry(shared, textvariable=self.shared_course, bg=FIELD_BG, fg=TEXT,
                 insertbackground=TEXT, relief="flat").pack(
            side="left", fill="x", expand=True, padx=(6, 0))
        tk.Label(frame,
                 text="Applies to every video below — edit any row to override "
                      "it. Titles are optional.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(
            anchor="w", padx=10)

        # Column headers
        hdr = tk.Frame(frame, bg=BG)
        hdr.pack(fill="x", padx=10, pady=(6, 0))
        tk.Label(hdr, text="File", bg=BG, fg=MUTED, font=("Segoe UI", 8, "bold"),
                 width=26, anchor="w").pack(side="left")
        tk.Label(hdr, text="Video title", bg=BG, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(
            side="left", fill="x", expand=True)
        tk.Label(hdr, text="Course title", bg=BG, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(
            side="left", fill="x", expand=True, padx=(6, 0))

        # Scrollable list of rows
        holder = tk.Frame(frame, bg=PANEL)
        holder.pack(fill="both", expand=True, padx=10, pady=(2, 10))
        self.rows_canvas = tk.Canvas(holder, bg=PANEL, height=150,
                                    highlightthickness=0)
        sb = ttk.Scrollbar(holder, orient="vertical",
                          command=self.rows_canvas.yview)
        self.rows_inner = tk.Frame(self.rows_canvas, bg=PANEL)
        self._rows_window = self.rows_canvas.create_window(
            (0, 0), window=self.rows_inner, anchor="nw")
        self.rows_canvas.configure(yscrollcommand=sb.set)
        self.rows_canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.rows_inner.bind(
            "<Configure>",
            lambda e: self.rows_canvas.configure(
                scrollregion=self.rows_canvas.bbox("all")))
        self.rows_canvas.bind(
            "<Configure>",
            lambda e: self.rows_canvas.itemconfigure(self._rows_window,
                                                     width=e.width))
        self.rows_canvas.bind(
            "<Enter>", lambda e: self.rows_canvas.bind_all(
                "<MouseWheel>", self._on_wheel))
        self.rows_canvas.bind(
            "<Leave>", lambda e: self.rows_canvas.unbind_all("<MouseWheel>"))

        self._empty_rows_label = tk.Label(
            self.rows_inner, text="Add videos above to set their titles.",
            bg=PANEL, fg=MUTED, font=("Segoe UI", 9))
        self._empty_rows_label.pack(pady=16)

    def _build_options(self, pad):
        opts = tk.LabelFrame(self.root, text=" Options ", bg=BG, fg=MUTED,
                            font=("Segoe UI", 10), bd=1, relief="groove")
        opts.pack(fill="x", **pad)

        tk.Checkbutton(
            opts, text="Add WGU branding (title-slide intro + WGU outro)",
            variable=self.add_branding, command=self._sync_enable,
            bg=BG, fg=TEXT, selectcolor=PANEL, activebackground=BG,
            activeforeground=TEXT, font=("Segoe UI", 10),
            anchor="w").pack(fill="x", padx=10, pady=(8, 2))

        trim_row = tk.Frame(opts, bg=BG)
        trim_row.pack(fill="x", padx=10, pady=(2, 8))
        tk.Checkbutton(
            trim_row, text="Trim old branding first —", variable=self.do_trim,
            command=self._sync_enable, bg=BG, fg=TEXT, selectcolor=PANEL,
            activebackground=BG, activeforeground=TEXT,
            font=("Segoe UI", 10)).pack(side="left")
        tk.Label(trim_row, text="seconds off start:", bg=BG, fg=MUTED,
                 font=("Segoe UI", 10)).pack(side="left", padx=(4, 4))
        self.e_start = tk.Entry(trim_row, textvariable=self.trim_start, width=5,
                               justify="center")
        self.e_start.pack(side="left")
        tk.Label(trim_row, text="off end:", bg=BG, fg=MUTED,
                 font=("Segoe UI", 10)).pack(side="left", padx=(10, 4))
        self.e_end = tk.Entry(trim_row, textvariable=self.trim_end, width=5,
                             justify="center")
        self.e_end.pack(side="left")

        # Advanced: template & outro image (collapsible)
        self.brand_open = tk.BooleanVar(value=False)
        self.brand_toggle = tk.Label(
            opts, text="▸ Advanced: intro template & outro image", bg=BG,
            fg=MUTED, font=("Segoe UI", 9, "underline"), cursor="hand2")
        self.brand_toggle.pack(anchor="w", padx=10, pady=(0, 2))
        self.brand_toggle.bind("<Button-1>", lambda e: self._toggle_brand())

        self.brand_panel = tk.Frame(opts, bg=BG)
        tk.Label(self.brand_panel,
                 text="The intro is the WGU title slide (your titles are drawn "
                      "on it); the outro is the WGU end slide. Change these only "
                      "to use a different template. Remembered next time.\nTip: "
                      "an admin can drop assets\\intro_template.png / "
                      "AppendAsset.png next to the app to change them for "
                      "everyone.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 8), justify="left").pack(
            anchor="w", pady=(0, 4))
        self._brand_row(self.brand_panel, "Intro template:", self.intro_template,
                       core.DEFAULT_INTRO_TEMPLATE)
        self._brand_row(self.brand_panel, "Outro image:", self.outro_path,
                       core.DEFAULT_APPEND_ASSET)

        outf = tk.Frame(opts, bg=BG)
        outf.pack(fill="x", padx=10, pady=(4, 10))
        tk.Radiobutton(
            outf, text="Save into a 'Branded' folder next to each video",
            variable=self.output_mode, value="beside", command=self._sync_enable,
            bg=BG, fg=TEXT, selectcolor=PANEL, activebackground=BG,
            activeforeground=TEXT, font=("Segoe UI", 9), anchor="w").pack(
            fill="x")
        cust = tk.Frame(outf, bg=BG)
        cust.pack(fill="x")
        tk.Radiobutton(
            cust, text="Save to:", variable=self.output_mode, value="custom",
            command=self._sync_enable, bg=BG, fg=TEXT, selectcolor=PANEL,
            activebackground=BG, activeforeground=TEXT,
            font=("Segoe UI", 9)).pack(side="left")
        self.e_out = tk.Entry(cust, textvariable=self.custom_output)
        self.e_out.pack(side="left", fill="x", expand=True, padx=(4, 4))
        self._mkbtn(cust, "…", self._browse_output, subtle=True).pack(
            side="left")

    def _brand_row(self, parent, label, var, default_name):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=2)
        tk.Label(row, text=label, bg=BG, fg=MUTED, width=14, anchor="w",
                 font=("Segoe UI", 9)).pack(side="left")
        tk.Entry(row, textvariable=var).pack(
            side="left", fill="x", expand=True, padx=(0, 4))
        self._mkbtn(row, "Choose…", lambda: self._browse_image(var),
                   subtle=True).pack(side="left")
        self._mkbtn(row, "Default",
                   lambda: self._reset_image(var, default_name),
                   subtle=True).pack(side="left", padx=(4, 0))

    def _mkbtn(self, parent, text, cmd, subtle=False, big=False):
        bg = PANEL if subtle else ACCENT
        font = ("Segoe UI Semibold", 12 if big else 10)
        return tk.Button(parent, text=text, command=cmd, bg=bg, fg=TEXT,
                        activebackground=ACCENT_HOVER, activeforeground=TEXT,
                        relief="flat", font=font, cursor="hand2",
                        padx=16 if big else 10, pady=8 if big else 4, bd=0)

    # ---------------------------------------------------------- title rows
    def _on_wheel(self, event):
        self.rows_canvas.yview_scroll(int(-event.delta / 120), "units")

    def _on_shared_course(self, *_):
        val = self.shared_course.get()
        for r in self.video_rows.values():
            if not r["dirty"]:
                r["ctitle"].set(val)

    def _rebuild_video_rows(self):
        for w in self.rows_inner.winfo_children():
            w.destroy()
        vids = core.collect_videos(self.selected_paths)

        # Preserve any titles already typed for videos that are still present.
        new_rows = {}
        for v in vids:
            prev = self.video_rows.get(v)
            if prev:
                new_rows[v] = prev
            else:
                new_rows[v] = {
                    "vtitle": tk.StringVar(),
                    "ctitle": tk.StringVar(value=self.shared_course.get()),
                    "dirty": False,
                }
        self.video_rows = new_rows

        if not vids:
            self._empty_rows_label = tk.Label(
                self.rows_inner, text="Add videos above to set their titles.",
                bg=PANEL, fg=MUTED, font=("Segoe UI", 9))
            self._empty_rows_label.pack(pady=16)
            return

        for v in vids:
            r = self.video_rows[v]
            row = tk.Frame(self.rows_inner, bg=PANEL)
            row.pack(fill="x", pady=1, padx=2)
            name = os.path.basename(v)
            disp = name if len(name) <= 30 else name[:27] + "…"
            tk.Label(row, text=disp, bg=PANEL, fg=TEXT, width=26, anchor="w",
                     font=("Segoe UI", 9)).pack(side="left")
            tk.Entry(row, textvariable=r["vtitle"], bg=FIELD_BG, fg=TEXT,
                     insertbackground=TEXT, relief="flat").pack(
                side="left", fill="x", expand=True)
            ce = tk.Entry(row, textvariable=r["ctitle"], bg=FIELD_BG, fg=TEXT,
                         insertbackground=TEXT, relief="flat")
            ce.pack(side="left", fill="x", expand=True, padx=(6, 0))
            ce.bind("<KeyRelease>",
                   lambda e, rr=r: rr.__setitem__("dirty", True))

    # -------------------------------------------------------------- events
    def _drop_color(self, color):
        for w in (self.drop, self.drop_label, self.drop_sub):
            w.configure(bg=color)

    def _toggle_brand(self):
        if self.brand_open.get():
            self.brand_panel.pack_forget()
            self.brand_toggle.configure(
                text="▸ Advanced: intro template & outro image")
        else:
            self.brand_panel.pack(fill="x", padx=10, pady=(0, 6))
            self.brand_toggle.configure(
                text="▾ Advanced: intro template & outro image")
        self.brand_open.set(not self.brand_open.get())

    def _on_drop(self, event):
        self._drop_color(DROP_IDLE)
        self._add_paths(_parse_drop(event.data))

    def _browse_files(self):
        exts = " ".join(f"*{e}" for e in core.VIDEO_EXTENSIONS)
        files = filedialog.askopenfilenames(
            title="Select video files",
            filetypes=[("Video files", exts), ("All files", "*.*")])
        self._add_paths(list(files))

    def _browse_folder(self):
        d = filedialog.askdirectory(title="Select a folder of videos")
        if d:
            self._add_paths([d])

    def _browse_output(self):
        d = filedialog.askdirectory(title="Select output folder")
        if d:
            self.custom_output.set(d)
            self.output_mode.set("custom")
            self._sync_enable()

    def _browse_image(self, var):
        f = filedialog.askopenfilename(
            title="Select image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp"),
                      ("All files", "*.*")])
        if f:
            var.set(f)
            self._persist_branding(var)

    def _settings_key(self, var):
        return "intro_template" if var is self.intro_template else "append"

    def _persist_branding(self, var):
        settings = core.load_settings()
        key = self._settings_key(var)
        default_name = (core.DEFAULT_INTRO_TEMPLATE if key == "intro_template"
                       else core.DEFAULT_APPEND_ASSET)
        value = var.get()
        if value and value != core.default_asset(default_name):
            settings[key] = value
        else:
            settings.pop(key, None)
        core.save_settings(settings)

    def _reset_image(self, var, default_name):
        var.set(core.default_asset(default_name))
        self._persist_branding(var)

    def _add_paths(self, paths):
        for p in paths:
            if p and p not in self.selected_paths:
                self.selected_paths.append(p)
        self._refresh_count()

    def _clear_paths(self):
        self.selected_paths = []
        self.video_rows = {}
        self._refresh_count()

    def _refresh_count(self):
        n = len(core.collect_videos(self.selected_paths))
        self.drop_sub.configure(
            text="No videos added yet" if n == 0
            else f"{n} video{'s' if n != 1 else ''} ready")
        self._rebuild_video_rows()

    def _sync_enable(self):
        trim_state = "normal" if self.do_trim.get() else "disabled"
        self.e_start.configure(state=trim_state)
        self.e_end.configure(state=trim_state)
        self.e_out.configure(
            state="normal" if self.output_mode.get() == "custom" else "disabled")

    # ------------------------------------------------------------- logging
    def _log_msg(self, msg):
        self._log_queue.put(msg)

    def _poll_log(self):
        try:
            while True:
                msg = self._log_queue.get_nowait()
                self.log.configure(state="normal")
                self.log.insert("end", msg + "\n")
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_log)

    def _check_ffmpeg(self):
        if not core.ffmpeg_available():
            self._log_msg("WARNING: ffmpeg was not found. If you are running "
                          "from source, install ffmpeg or place ffmpeg.exe/"
                          "ffprobe.exe in the 'ffmpeg' folder.")

    # -------------------------------------------------------------- action
    def _validate(self):
        vids = core.collect_videos(self.selected_paths)
        if not vids:
            messagebox.showwarning(APP_TITLE, "Add at least one video first.")
            return None
        if not self.add_branding.get() and not self.do_trim.get():
            messagebox.showwarning(
                APP_TITLE, "Turn on branding, trimming, or both.")
            return None

        ts = te = 0.0
        if self.do_trim.get():
            try:
                ts = max(0.0, float(self.trim_start.get() or 0))
                te = max(0.0, float(self.trim_end.get() or 0))
            except ValueError:
                messagebox.showwarning(APP_TITLE, "Trim seconds must be numbers.")
                return None
            if ts == 0 and te == 0:
                messagebox.showwarning(
                    APP_TITLE, "Enter how many seconds to trim (start or end).")
                return None

        if self.add_branding.get():
            if not os.path.isfile(self.intro_template.get()):
                messagebox.showwarning(
                    APP_TITLE, "The intro template image was not found:\n"
                    f"{self.intro_template.get()}")
                return None
            if not os.path.isfile(self.outro_path.get()):
                messagebox.showwarning(
                    APP_TITLE, "The outro image was not found:\n"
                    f"{self.outro_path.get()}")
                return None

        return {"videos": vids, "trim_start": ts, "trim_end": te}

    def _start(self):
        if self._worker and self._worker.is_alive():
            return
        params = self._validate()
        if not params:
            return

        self.start_btn.configure(state="disabled", text="Working…")
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.progress.configure(value=0, maximum=len(params["videos"]))

        self._worker = threading.Thread(
            target=self._run, args=(params,), daemon=True)
        self._worker.start()

    def _output_for(self, video):
        if self.output_mode.get() == "custom" and self.custom_output.get():
            outdir = self.custom_output.get()
        else:
            outdir = os.path.join(os.path.dirname(video), "Branded")
        return os.path.join(outdir, os.path.basename(video))

    def _run(self, params):
        videos = params["videos"]
        add_branding = self.add_branding.get()
        intro_template = self.intro_template.get()
        outro = self.outro_path.get()
        ok = fail = 0
        self._log_msg(f"Processing {len(videos)} video(s)…\n")

        for i, video in enumerate(videos, 1):
            name = os.path.basename(video)
            self._log_msg(f"[{i}/{len(videos)}] {name}")
            row = self.video_rows.get(video, {})
            vtitle = row["vtitle"].get() if "vtitle" in row else ""
            ctitle = row["ctitle"].get() if "ctitle" in row else ""
            out = self._output_for(video)
            try:
                if os.path.abspath(out) == os.path.abspath(video):
                    raise core.ProcessError(
                        "Output would overwrite the source; choose a "
                        "different output folder.")
                core.process_video(
                    video, out,
                    add_branding=add_branding,
                    intro_template=intro_template,
                    append_asset=outro,
                    video_title=vtitle,
                    course_title=ctitle,
                    trim_start=params["trim_start"],
                    trim_end=params["trim_end"],
                    log=self._log_msg,
                )
                ok += 1
            except core.ProcessError as exc:
                fail += 1
                self._log_msg(f"  ERROR: {exc}")
            except Exception as exc:  # pragma: no cover
                fail += 1
                self._log_msg(f"  UNEXPECTED ERROR: {exc}")
                self._log_msg(traceback.format_exc())
            self._log_msg("")
            self.root.after(0, lambda v=i: self.progress.configure(value=v))

        self._log_msg("=" * 44)
        self._log_msg(f"Done. {ok} succeeded, {fail} failed.")
        self.root.after(0, self._finish, ok, fail)

    def _finish(self, ok, fail):
        self.start_btn.configure(state="normal", text="Start")
        if fail == 0:
            messagebox.showinfo(APP_TITLE, f"Finished! {ok} video(s) branded.")
        else:
            messagebox.showwarning(
                APP_TITLE,
                f"Finished with problems: {ok} succeeded, {fail} failed.\n"
                f"See the log for details.")


def main():
    root = TkinterDnD.Tk() if _DND else tk.Tk()
    BranderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
