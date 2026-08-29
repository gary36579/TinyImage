import os
import sys
import threading
import time
from tkinter import filedialog, messagebox
import customtkinter as ctk

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import main as ti


class TinyImageGUI:
    def __init__(self):
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("green")

        self.root = ctk.CTk()
        self.root.title("TinyImage - Image Optimization Tool")
        self.root.geometry("920x800")
        self.root.minsize(800, 650)

        self._cancelled = False
        self._processing = False

        self._setup_ui()

    def _setup_ui(self):
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(5, weight=0)
        self.root.grid_rowconfigure(7, weight=1)

        # Header
        title_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        title_frame.grid(row=0, column=0, padx=20, pady=(15, 0), sticky="ew")
        ctk.CTkLabel(
            title_frame, text="TinyImage",
            font=ctk.CTkFont(size=22, weight="bold")
        ).pack(side="left")
        ctk.CTkLabel(
            title_frame, text="Image Optimization Tool",
            font=ctk.CTkFont(size=12)
        ).pack(side="left", padx=(10, 0))

        # Directories
        dir_frame = ctk.CTkFrame(self.root)
        dir_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        dir_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(dir_frame, text="Input:", width=60).grid(
            row=0, column=0, padx=(10, 5), pady=8, sticky="w")
        self.input_var = ctk.StringVar(value="input")
        ctk.CTkEntry(dir_frame, textvariable=self.input_var).grid(
            row=0, column=1, padx=5, pady=8, sticky="ew")
        ctk.CTkButton(dir_frame, text="Browse", width=80,
                      command=self._browse_input).grid(
            row=0, column=2, padx=(5, 10), pady=8)

        ctk.CTkLabel(dir_frame, text="Output:", width=60).grid(
            row=1, column=0, padx=(10, 5), pady=8, sticky="w")
        self.output_var = ctk.StringVar(value="output")
        ctk.CTkEntry(dir_frame, textvariable=self.output_var).grid(
            row=1, column=1, padx=5, pady=8, sticky="ew")
        ctk.CTkButton(dir_frame, text="Browse", width=80,
                      command=self._browse_output).grid(
            row=1, column=2, padx=(5, 10), pady=8)

        # Tab view
        self.tab_view = ctk.CTkTabview(self.root)
        self.tab_view.grid(row=2, column=0, padx=20, pady=(5, 0), sticky="ew")
        self._setup_main_tab()
        self._setup_advanced_tab()
        self._setup_output_tab()

        # Control buttons
        btn_frame = ctk.CTkFrame(self.root)
        btn_frame.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        btn_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.start_btn = ctk.CTkButton(
            btn_frame, text="\u25b6 Start", command=self._start_processing)
        self.start_btn.grid(row=0, column=0, padx=10, pady=8, sticky="ew")

        self.stop_btn = ctk.CTkButton(
            btn_frame, text="\u25a0 Stop", command=self._stop_processing,
            state="disabled", fg_color="#c0392b", hover_color="#e74c3c")
        self.stop_btn.grid(row=0, column=1, padx=10, pady=8, sticky="ew")

        ctk.CTkButton(btn_frame, text="Show Config",
                      command=self._show_config).grid(
            row=0, column=2, padx=10, pady=8, sticky="ew")

        # Progress
        self.progress_frame = ctk.CTkFrame(self.root)
        self.progress_frame.grid(row=4, column=0, padx=20, pady=(0, 5),
                                 sticky="ew")
        self.progress_frame.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            self.progress_frame, text="Ready", anchor="w")
        self.status_label.grid(row=0, column=0, padx=10, pady=(5, 0),
                               sticky="ew")

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame)
        self.progress_bar.grid(row=1, column=0, padx=10, pady=(5, 5),
                               sticky="ew")
        self.progress_bar.set(0)

        # Results header
        ctk.CTkLabel(
            self.root, text="Results",
            font=ctk.CTkFont(size=13, weight="bold"), anchor="w"
        ).grid(row=5, column=0, padx=20, pady=(5, 0), sticky="ew")

        # Results scrollable frame
        self.results_frame = ctk.CTkScrollableFrame(self.root)
        self.results_frame.grid(row=6, column=0, padx=20, pady=(2, 5),
                                sticky="nsew")
        self.results_frame.grid_columnconfigure(0, weight=1)

        self._result_widgets = []

        # Summary
        self.summary_frame = ctk.CTkFrame(self.root)
        self.summary_frame.grid(row=7, column=0, padx=20, pady=(0, 15),
                                sticky="ew")
        self.summary_frame.grid_columnconfigure(0, weight=1)

        self.summary_label = ctk.CTkLabel(
            self.summary_frame, text="", anchor="w", justify="left")
        self.summary_label.grid(row=0, column=0, padx=12, pady=8, sticky="ew")

    def _setup_main_tab(self):
        tab = self.tab_view.add("Main")
        tab.grid_columnconfigure(1, weight=1)

        row = 0
        ctk.CTkLabel(tab, text="Quality:").grid(
            row=row, column=0, padx=(15, 5), pady=8, sticky="w")
        self.quality_var = ctk.IntVar(value=80)
        ctk.CTkSlider(tab, from_=1, to=100, number_of_steps=99,
                      variable=self.quality_var).grid(
            row=row, column=1, padx=5, pady=8, sticky="ew")
        ctk.CTkLabel(tab, textvariable=self.quality_var, width=30).grid(
            row=row, column=2, padx=(5, 15), pady=8)

        row = 1
        ctk.CTkLabel(tab, text="PNG Level:").grid(
            row=row, column=0, padx=(15, 5), pady=8, sticky="w")
        self.png_level_var = ctk.IntVar(value=9)
        ctk.CTkSlider(tab, from_=0, to=9, number_of_steps=9,
                      variable=self.png_level_var).grid(
            row=row, column=1, padx=5, pady=8, sticky="ew")
        ctk.CTkLabel(tab, textvariable=self.png_level_var, width=30).grid(
            row=row, column=2, padx=(5, 15), pady=8)

        row = 2
        ctk.CTkLabel(tab, text="WebP Method:").grid(
            row=row, column=0, padx=(15, 5), pady=8, sticky="w")
        self.webp_method_var = ctk.IntVar(value=6)
        ctk.CTkSlider(tab, from_=0, to=6, number_of_steps=6,
                      variable=self.webp_method_var).grid(
            row=row, column=1, padx=5, pady=8, sticky="ew")
        ctk.CTkLabel(tab, textvariable=self.webp_method_var, width=30).grid(
            row=row, column=2, padx=(5, 15), pady=8)

        row = 3
        self.jpeg_progressive_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(tab, text="JPEG Progressive",
                      variable=self.jpeg_progressive_var).grid(
            row=row, column=0, columnspan=3, padx=(15, 5), pady=8, sticky="w")

        row = 4
        ctk.CTkLabel(tab, text="").grid(row=row, column=0, pady=2)

        row = 5
        self.png_to_webp_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(tab, text="PNG \u2192 WebP",
                      variable=self.png_to_webp_var).grid(
            row=row, column=0, columnspan=3, padx=(15, 5), pady=8, sticky="w")

        row = 6
        self.jpg_to_webp_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(tab, text="JPEG \u2192 WebP",
                      variable=self.jpg_to_webp_var).grid(
            row=row, column=0, columnspan=3, padx=(15, 5), pady=8, sticky="w")

    def _setup_advanced_tab(self):
        tab = self.tab_view.add("Advanced")
        tab.grid_columnconfigure(1, weight=1)

        row = 0
        ctk.CTkLabel(tab, text="PNG Level (stream):").grid(
            row=row, column=0, padx=(15, 5), pady=8, sticky="w")
        self.png_level_stream_var = ctk.IntVar(value=3)
        ctk.CTkSlider(tab, from_=0, to=9, number_of_steps=9,
                      variable=self.png_level_stream_var).grid(
            row=row, column=1, padx=5, pady=8, sticky="ew")
        ctk.CTkLabel(tab, textvariable=self.png_level_stream_var, width=30).grid(
            row=row, column=2, padx=(5, 15), pady=8)

        row = 1
        ctk.CTkLabel(tab, text="WebP Method (stream):").grid(
            row=row, column=0, padx=(15, 5), pady=8, sticky="w")
        self.webp_method_stream_var = ctk.IntVar(value=4)
        ctk.CTkSlider(tab, from_=0, to=6, number_of_steps=6,
                      variable=self.webp_method_stream_var).grid(
            row=row, column=1, padx=5, pady=8, sticky="ew")
        ctk.CTkLabel(tab, textvariable=self.webp_method_stream_var, width=30).grid(
            row=row, column=2, padx=(5, 15), pady=8)

        row = 2
        ctk.CTkLabel(tab, text="").grid(row=row, column=0, pady=2)

        row = 3
        ctk.CTkLabel(tab, text="Suffix:").grid(
            row=row, column=0, padx=(15, 5), pady=8, sticky="w")
        self.suffix_var = ctk.StringVar(value="[minify]")
        ctk.CTkEntry(tab, textvariable=self.suffix_var).grid(
            row=row, column=1, columnspan=2, padx=5, pady=8, sticky="ew")

        row = 4
        ctk.CTkLabel(tab, text="Workers:").grid(
            row=row, column=0, padx=(15, 5), pady=8, sticky="w")
        self.workers_var = ctk.StringVar(value=str(os.cpu_count() or 4))
        ctk.CTkEntry(tab, textvariable=self.workers_var, width=70).grid(
            row=row, column=1, padx=5, pady=8, sticky="w")

        row = 5
        self.sequential_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(tab, text="Sequential mode",
                      variable=self.sequential_var).grid(
            row=row, column=0, columnspan=3, padx=(15, 5), pady=8, sticky="w")

        row = 6
        self.override_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(tab, text="Override (force re-compression)",
                      variable=self.override_var).grid(
            row=row, column=0, columnspan=3, padx=(15, 5), pady=8, sticky="w")

    def _setup_output_tab(self):
        tab = self.tab_view.add("Output")
        tab.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(tab, text="Original File Handling:",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, columnspan=3, padx=(15, 5), pady=(10, 5),
            sticky="w")

        self.delete_mode_var = ctk.StringVar(value="none")
        ctk.CTkRadioButton(tab, text="Keep originals",
                           variable=self.delete_mode_var,
                           value="none").grid(
            row=1, column=0, columnspan=3, padx=(25, 5), pady=5, sticky="w")
        ctk.CTkRadioButton(tab, text="Delete originals",
                           variable=self.delete_mode_var,
                           value="delete").grid(
            row=2, column=0, columnspan=3, padx=(25, 5), pady=5, sticky="w")
        ctk.CTkRadioButton(tab, text="Soft-delete (to trash)",
                           variable=self.delete_mode_var,
                           value="soft").grid(
            row=3, column=0, columnspan=3, padx=(25, 5), pady=5, sticky="w")

        row = 4
        ctk.CTkLabel(tab, text="").grid(row=row, column=0, pady=2)

        row = 5
        ctk.CTkLabel(tab, text="Watch Mode:",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=row, column=0, columnspan=3, padx=(15, 5), pady=(10, 5),
            sticky="w")

        row = 6
        self.watch_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(tab, text="Enable watch mode",
                      variable=self.watch_var).grid(
            row=row, column=0, columnspan=3, padx=(25, 5), pady=8,
            sticky="w")

        row = 7
        ctk.CTkLabel(tab, text="Poll interval (s):").grid(
            row=row, column=0, padx=(25, 5), pady=8, sticky="w")
        self.watch_interval_var = ctk.StringVar(value="3")
        ctk.CTkEntry(tab, textvariable=self.watch_interval_var,
                     width=70).grid(
            row=row, column=1, padx=5, pady=8, sticky="w")

    def _browse_input(self):
        d = filedialog.askdirectory(title="Select Input Directory")
        if d:
            self.input_var.set(d)

    def _browse_output(self):
        d = filedialog.askdirectory(title="Select Output Directory")
        if d:
            self.output_var.set(d)

    def _start_processing(self):
        self._cancelled = False
        self._processing = True
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

        for w in self._result_widgets:
            w.destroy()
        self._result_widgets = []
        self.summary_label.configure(text="")
        self.progress_bar.set(0)
        self.status_label.configure(text="Initializing...")

        config = self._collect_config()

        if config["delete_mode"] == "soft" and not ti.HAS_SEND2TRASH:
            messagebox.showerror(
                "Missing Dependency",
                "Soft-delete requires send2trash.\n"
                "Install with: pip install send2trash")
            self._reset_ui()
            return

        t = threading.Thread(
            target=self._process_thread, args=(config,), daemon=True)
        t.start()

    def _stop_processing(self):
        self._cancelled = True
        self.status_label.configure(
            text="Cancelling... (finishing current file)")

    def _collect_config(self):
        try:
            workers = int(self.workers_var.get())
        except ValueError:
            workers = os.cpu_count() or 4
        try:
            watch_interval = int(self.watch_interval_var.get())
        except ValueError:
            watch_interval = 3
        return {
            "input_dir": self.input_var.get(),
            "output_dir": self.output_var.get(),
            "quality": self.quality_var.get(),
            "png_level": self.png_level_var.get(),
            "webp_method": self.webp_method_var.get(),
            "jpeg_progressive": self.jpeg_progressive_var.get(),
            "png_to_webp": self.png_to_webp_var.get(),
            "jpg_to_webp": self.jpg_to_webp_var.get(),
            "png_level_stream": self.png_level_stream_var.get(),
            "webp_method_stream": self.webp_method_stream_var.get(),
            "suffix": self.suffix_var.get(),
            "workers": max(1, workers),
            "sequential": self.sequential_var.get(),
            "override": self.override_var.get(),
            "delete_mode": self.delete_mode_var.get(),
            "watch": self.watch_var.get(),
            "watch_interval": max(1, watch_interval),
        }

    def _process_thread(self, config):
        try:
            ti.SUFFIX = config["suffix"]

            delete_original = config["delete_mode"] == "delete"
            soft_delete = config["delete_mode"] == "soft"

            def progress_cb(phase, rel_path, current, total, status, extra):
                if self._cancelled:
                    return False
                if phase == "start":
                    self.root.after(0, self._on_start, total)
                elif phase == "progress":
                    self.root.after(0, self._on_progress,
                                    rel_path, current, total)
                elif phase == "file_done":
                    self.root.after(
                        0, self._on_file_done,
                        rel_path, status,
                        extra.get("final_filename", ""),
                        extra.get("orig_size", 0),
                        extra.get("new_size", 0),
                        extra.get("pct", 0))
                elif phase == "file_delete":
                    self.root.after(0, self._on_file_delete,
                                    rel_path, extra.get("label", ""))
                elif phase == "complete":
                    self.root.after(
                        0, self._on_complete,
                        extra.get("total_orig", 0),
                        extra.get("total_new", 0))
                return not self._cancelled

            if config["watch"]:
                self._gui_watch_loop(config, progress_cb)
            else:
                self._gui_single_run(config, progress_cb)

        except Exception as e:
            self.root.after(0, self._on_error, str(e))
        finally:
            self.root.after(0, self._reset_ui)

    def _gui_single_run(self, config, progress_cb):
        os.makedirs(config["output_dir"], exist_ok=True)

        image_tasks, archive_tasks, found = ti._scan_directory(
            config["input_dir"], ti.IMG_EXTENSIONS, ti.ARC_EXTENSIONS,
            config["override"], config["suffix"])

        if not found:
            self.root.after(
                0, self._on_error, "No image files or archives found.")
            return

        ti._run_tasks(
            image_tasks, archive_tasks, config["output_dir"],
            config["sequential"], config["workers"],
            config["png_to_webp"], config["jpg_to_webp"],
            config["quality"], config["png_level"], config["webp_method"],
            config["jpeg_progressive"], config["override"],
            config["delete_mode"] == "delete",
            config["delete_mode"] == "soft",
            config["png_level_stream"], config["webp_method_stream"],
            progress_cb=progress_cb)

    def _gui_watch_loop(self, config, progress_cb):
        input_dir = config["input_dir"]
        output_dir = config["output_dir"]
        interval = max(1, config["watch_interval"])
        delete_original = config["delete_mode"] == "delete"
        soft_delete = config["delete_mode"] == "soft"

        os.makedirs(output_dir, exist_ok=True)

        # Initial scan and process
        image_tasks, archive_tasks, found = ti._scan_directory(
            input_dir, ti.IMG_EXTENSIONS, ti.ARC_EXTENSIONS,
            config["override"], config["suffix"])

        if image_tasks or archive_tasks:
            self.root.after(
                0, self._on_watch_status,
                "Initial scan: processing existing files...")
            ti._run_tasks(
                image_tasks, archive_tasks, output_dir,
                config["sequential"], config["workers"],
                config["png_to_webp"], config["jpg_to_webp"],
                config["quality"], config["png_level"], config["webp_method"],
                config["jpeg_progressive"], config["override"],
                delete_original, soft_delete,
                config["png_level_stream"], config["webp_method_stream"],
                progress_cb=progress_cb)
            if self._cancelled:
                return

        # Build initial tracked dict
        tracked = {}
        for root, dirs, files in os.walk(input_dir):
            dirs[:] = [d for d in dirs
                       if not ti.is_hidden(os.path.join(root, d))]
            for fname in files:
                fpath = os.path.join(root, fname)
                if ti.is_hidden(fpath):
                    continue
                try:
                    tracked[fpath] = os.path.getmtime(fpath)
                except OSError:
                    pass

        self.root.after(
            0, self._on_watch_status,
            f"Watch mode active. Monitoring '{input_dir}'...")

        # Polling loop
        while not self._cancelled:
            time.sleep(interval)
            if self._cancelled:
                break

            current = {}
            for root, dirs, files in os.walk(input_dir):
                dirs[:] = [d for d in dirs
                           if not ti.is_hidden(os.path.join(root, d))]
                for fname in files:
                    fpath = os.path.join(root, fname)
                    if ti.is_hidden(fpath):
                        continue
                    try:
                        current[fpath] = os.path.getmtime(fpath)
                    except OSError:
                        pass

            delta_images = []
            delta_archives = []

            for fpath, mtime in current.items():
                if fpath not in tracked or mtime != tracked[fpath]:
                    filename = os.path.basename(fpath)
                    if (not config["override"]
                            and config["suffix"] in filename):
                        continue
                    ext = os.path.splitext(filename)[1].lower()
                    if (ext not in ti.IMG_EXTENSIONS
                            and ext not in ti.ARC_EXTENSIONS):
                        continue
                    rel_path = os.path.relpath(fpath, input_dir)
                    root_dir = os.path.dirname(fpath)
                    if ext in ti.IMG_EXTENSIONS:
                        delta_images.append((root_dir, filename, rel_path))
                    else:
                        delta_archives.append((root_dir, filename, rel_path))

            for fpath in list(tracked):
                if fpath not in current:
                    del tracked[fpath]

            if delta_images or delta_archives:
                count = len(delta_images) + len(delta_archives)
                self.root.after(
                    0, self._on_watch_status,
                    f"Changes detected: processing {count} file(s)...")
                ti._run_tasks(
                    delta_images, delta_archives, output_dir,
                    config["sequential"], config["workers"],
                    config["png_to_webp"], config["jpg_to_webp"],
                    config["quality"], config["png_level"],
                    config["webp_method"],
                    config["jpeg_progressive"], config["override"],
                    delete_original, soft_delete,
                    config["png_level_stream"],
                    config["webp_method_stream"],
                    progress_cb=progress_cb)
                self.root.after(
                    0, self._on_watch_status,
                    f"Watch mode active. Monitoring '{input_dir}'...")

            tracked = current

    def _on_start(self, total):
        self.progress_bar.set(0)
        self.status_label.configure(text=f"Processing 0/{total} files...")

    def _on_progress(self, rel_path, current, total):
        pct = current / total if total > 0 else 0
        self.progress_bar.set(pct)
        self.status_label.configure(
            text=f"Processing: {rel_path}  ({current}/{total})")

    def _on_file_done(self, rel_path, status, final_filename,
                      orig_size, new_size, pct):
        if status == 0:
            msg = (f"\u2714  {rel_path} \u2192 {final_filename}  "
                   f"({ti.format_size(orig_size)} \u2192 "
                   f"{ti.format_size(new_size)}, -{pct:.1f}%)")
            color = "#27ae60"
        elif status == 1:
            msg = f"\u2718  {rel_path}  (error)"
            color = "#e74c3c"
        else:
            msg = f"\u23ed  {rel_path}"
            color = "#7f8c8d"
        self._add_result(msg, color)

    def _on_file_delete(self, rel_path, label):
        msg = f"         [{label}] {rel_path}"
        self._add_result(msg, "#e67e22")

    def _on_complete(self, total_orig, total_new):
        if total_orig > 0:
            saved = total_orig - total_new
            pct = (saved / total_orig) * 100
            text = (f"Total size optimized: "
                    f"{ti.format_size(total_orig)} \u2192 "
                    f"{ti.format_size(total_new)} "
                    f"(-{pct:.2f}%, saved {ti.format_size(saved)})")
        else:
            text = "No files were processed."
        self.summary_label.configure(text=text)

    def _on_watch_status(self, msg):
        self.status_label.configure(text=msg)

    def _on_error(self, msg):
        self._add_result(f"\u2718  ERROR: {msg}", "#e74c3c")

    def _add_result(self, msg, color):
        label = ctk.CTkLabel(
            self.results_frame, text=msg, anchor="w", justify="left",
            text_color=color, font=ctk.CTkFont(size=12))
        label.pack(fill="x", padx=5, pady=1)
        self._result_widgets.append(label)
        try:
            self.results_frame._parent_canvas.yview_moveto(1.0)
        except AttributeError:
            try:
                self.results_frame._canvas.yview_moveto(1.0)
            except AttributeError:
                pass

    def _reset_ui(self):
        self._processing = False
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        if not self._cancelled:
            self.status_label.configure(text="Done")

    def _show_config(self):
        c = self._collect_config()
        lines = [
            f"Input directory:    {c['input_dir']}",
            f"Output directory:   {c['output_dir']}",
            "",
            f"Quality:            {c['quality']}",
            f"PNG level:          {c['png_level']}",
            f"WebP method:        {c['webp_method']}",
            f"JPEG progressive:   {c['jpeg_progressive']}",
            "",
            f"PNG level stream:   {c['png_level_stream']}",
            f"WebP method stream: {c['webp_method_stream']}",
            f"Suffix:             '{c['suffix']}'",
            f"Workers:            {c['workers']}",
            f"Sequential:         {c['sequential']}",
            f"Override:           {c['override']}",
            "",
            f"PNG to WebP:        {c['png_to_webp']}",
            f"JPEG to WebP:       {c['jpg_to_webp']}",
            f"Delete mode:        {c['delete_mode']}",
            "",
            f"Watch mode:         {c['watch']}",
            f"Watch interval:     {c['watch_interval']}s",
        ]
        messagebox.showinfo("TinyImage Configuration", "\n".join(lines))

    def run(self):
        self.root.mainloop()


def main():
    app = TinyImageGUI()
    app.run()


if __name__ == "__main__":
    main()
