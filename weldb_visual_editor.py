#!/usr/bin/env python3
"""weldb visual editor — a tiny, self-contained Tkinter app.

A ``.weldb`` file is just YAML, so this is, at heart, a YAML text editor. On top
of that it renders every view's ``grid`` as an actual editable grid of cells so
the visual layout of the weld map is preserved while you edit it.

    python weldb_visual_editor.py            # then File > Open
    python weldb_visual_editor.py FILE.weldb # open a file directly

Behaviour
---------
* The **YAML Source** pane (left) is the master copy and what gets saved. Its
  leading ``#`` comment block is preserved across edits.
* The **View Grids** pane (right) shows one tab per map/view. Cells are colored
  by weld type (grey = empty, green = point ``*``, blue = linear ``_``, orange =
  area ``@``, white = plain label). Editing a cell rewrites the YAML body
  (header comments kept); editing the source and switching to a grid tab
  refreshes the grids.

Only the Python standard library and PyYAML (already a weldb dependency) are
required — no import of the ``weldb`` package, so this file stands alone.
"""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - friendly message when PyYAML is absent
    sys.stderr.write(
        "This editor needs PyYAML. Install it with:  pip install pyyaml\n"
    )
    raise

import tkinter as tk
from tkinter import filedialog, font, messagebox, ttk

# --- Cell colors (light enough to keep black text readable) --------------------
FILL_EMPTY = "#ececec"   # light grey  — blank / whitespace cells
FILL_POINT = "#d0f0d2"   # pastel green — point welds (*)
FILL_LINEAR = "#cee0f6"  # pastel blue  — linear welds (_)
FILL_AREA = "#fae4c8"    # pastel orange — area welds (@)
FILL_LABEL = "#ffffff"   # white        — plain labels (tube numbers, notes)

LEGEND = [
    ("empty", FILL_EMPTY),
    ("* point", FILL_POINT),
    ("_ linear", FILL_LINEAR),
    ("@ area", FILL_AREA),
    ("label", FILL_LABEL),
]


def cell_fill(value: str) -> str:
    """Background color for a grid cell, keyed to its content (see LEGEND)."""
    v = (value or "").strip()
    if not v:
        return FILL_EMPTY
    if v.startswith("*"):
        return FILL_POINT
    if v.startswith("_"):
        return FILL_LINEAR
    if v.startswith("@"):
        return FILL_AREA
    return FILL_LABEL


# --- YAML helpers --------------------------------------------------------------
class _FlowList(list):
    """A list that PyYAML dumps inline (``[a, b, c]``) — used for grid rows."""


def _represent_flow_list(dumper, data):
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True)


yaml.add_representer(_FlowList, _represent_flow_list, Dumper=yaml.SafeDumper)


def dump_doc(doc: dict) -> str:
    """Serialize a weldb doc to YAML, keeping grid rows inline and cells as text.

    Every grid cell is forced to a string so numeric-looking labels (e.g.
    ``250``) round-trip as strings rather than ints — the renderer treats cells
    as text.
    """
    d = copy.deepcopy(doc)
    for m in d.get("maps", []) or []:
        if not isinstance(m, dict):
            continue
        for v in m.get("views", []) or []:
            if isinstance(v, dict) and isinstance(v.get("grid"), list):
                v["grid"] = [
                    _FlowList(str(c) for c in row) if isinstance(row, list) else row
                    for row in v["grid"]
                ]
    return yaml.safe_dump(d, sort_keys=False, default_flow_style=False, allow_unicode=True)


def extract_header(text: str) -> str:
    """Return the leading run of comment/blank lines from ``text`` (with newline)."""
    out: list[str] = []
    for line in text.split("\n"):
        if line.strip() == "" or line.lstrip().startswith("#"):
            out.append(line)
        else:
            break
    return ("\n".join(out) + "\n") if out else ""


def iter_grids(doc: dict):
    """Yield ``(map_index, view_index, rev, view_name, grid)`` for every view grid."""
    if not isinstance(doc, dict):
        return
    for mi, m in enumerate(doc.get("maps", []) or []):
        if not isinstance(m, dict):
            continue
        rev = str(m.get("rev", f"map{mi}"))
        for vi, v in enumerate(m.get("views", []) or []):
            if isinstance(v, dict) and isinstance(v.get("grid"), list):
                yield mi, vi, rev, str(v.get("name", f"view{vi}")), v["grid"]


# --- The application -----------------------------------------------------------
class WeldbEditor:
    def __init__(self, root: tk.Tk, initial: str | None = None):
        self.root = root
        self.path: Path | None = None
        self.doc: dict = {}
        self.modified = False
        self._suppress_source_event = False  # guard against feedback loops
        self._refresh_job = None
        self.mono = font.nametofont("TkFixedFont").copy()
        self.mono.configure(size=9)

        root.title("weldb visual editor")
        root.geometry("1280x780")
        root.minsize(800, 480)

        self._build_menu()
        self._build_toolbar()
        self._build_panes()
        self._build_statusbar()

        root.protocol("WM_DELETE_WINDOW", self.on_quit)
        root.bind("<Control-o>", lambda e: self.open_file())
        root.bind("<Control-s>", lambda e: self.save())

        if initial:
            self.load_path(Path(initial))
        else:
            self.update_title()

    # -- UI construction --------------------------------------------------------
    def _build_menu(self):
        bar = tk.Menu(self.root)
        filemenu = tk.Menu(bar, tearoff=0)
        filemenu.add_command(label="Open…", accelerator="Ctrl+O", command=self.open_file)
        filemenu.add_command(label="Save", accelerator="Ctrl+S", command=self.save)
        filemenu.add_command(label="Save As…", command=self.save_as)
        filemenu.add_separator()
        filemenu.add_command(label="Exit", command=self.on_quit)
        bar.add_cascade(label="File", menu=filemenu)
        helpmenu = tk.Menu(bar, tearoff=0)
        helpmenu.add_command(label="About", command=self.show_about)
        bar.add_cascade(label="Help", menu=helpmenu)
        self.root.config(menu=bar)

    def _build_toolbar(self):
        tb = ttk.Frame(self.root, padding=(6, 4))
        tb.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(tb, text="Open", command=self.open_file).pack(side=tk.LEFT)
        ttk.Button(tb, text="Save", command=self.save).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(tb, text="Refresh grids", command=self.refresh_grids_from_source).pack(
            side=tk.LEFT, padx=(12, 0)
        )
        # Color legend on the right.
        legend = ttk.Frame(tb)
        legend.pack(side=tk.RIGHT)
        for label, color in LEGEND:
            sw = tk.Label(legend, text="  ", bg=color, relief="solid", borderwidth=1)
            sw.pack(side=tk.LEFT, padx=(8, 2))
            ttk.Label(legend, text=label).pack(side=tk.LEFT)

    def _build_panes(self):
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Left: YAML source editor.
        left = ttk.Frame(paned)
        ttk.Label(left, text="YAML Source", padding=(4, 2)).pack(anchor="w")
        text_wrap = ttk.Frame(left)
        text_wrap.pack(fill=tk.BOTH, expand=True)
        self.text = tk.Text(text_wrap, wrap="none", undo=True, font=self.mono)
        ysb = ttk.Scrollbar(text_wrap, orient=tk.VERTICAL, command=self.text.yview)
        xsb = ttk.Scrollbar(text_wrap, orient=tk.HORIZONTAL, command=self.text.xview)
        self.text.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")
        text_wrap.rowconfigure(0, weight=1)
        text_wrap.columnconfigure(0, weight=1)
        self.text.bind("<<Modified>>", self.on_source_modified)
        paned.add(left, weight=1)

        # Right: grids.
        right = ttk.Frame(paned)
        ttk.Label(right, text="View Grids", padding=(4, 2)).pack(anchor="w")
        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", lambda e: None)
        self.grid_placeholder = ttk.Label(
            right, text="(open a .weldb file with view grids)", padding=8
        )
        paned.add(right, weight=1)
        self.root.after(80, lambda: paned.sashpos(0, 640))

    def _build_statusbar(self):
        self.status = tk.StringVar(value="Ready.")
        bar = ttk.Frame(self.root, relief="sunken", padding=(6, 2))
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Label(bar, textvariable=self.status).pack(side=tk.LEFT)

    # -- File operations --------------------------------------------------------
    def open_file(self):
        if not self.confirm_discard():
            return
        path = filedialog.askopenfilename(
            title="Open a weldb file",
            filetypes=[("weldb files", "*.weldb"), ("YAML files", "*.yaml *.yml"), ("All files", "*.*")],
        )
        if path:
            self.load_path(Path(path))

    def load_path(self, path: Path):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Open failed", f"Could not read file:\n{exc}")
            return
        self.path = path
        self.set_source_text(text)
        self.parse_source(report=True)
        self.rebuild_grids()
        self.set_modified(False)
        self.update_title()

    def save(self):
        if self.path is None:
            return self.save_as()
        return self._write_to(self.path)

    def save_as(self):
        path = filedialog.asksaveasfilename(
            title="Save weldb file",
            defaultextension=".weldb",
            filetypes=[("weldb files", "*.weldb"), ("All files", "*.*")],
        )
        if not path:
            return False
        self.path = Path(path)
        return self._write_to(self.path)

    def _write_to(self, path: Path) -> bool:
        text = self.text.get("1.0", "end-1c")
        try:
            yaml.safe_load(text)
        except yaml.YAMLError as exc:
            if not messagebox.askyesno(
                "Invalid YAML",
                f"The document is not valid YAML:\n\n{exc}\n\nSave anyway?",
            ):
                return False
        try:
            path.write_text(text, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Save failed", f"Could not write file:\n{exc}")
            return False
        self.set_modified(False)
        self.update_title()
        self.status.set(f"Saved {path}")
        return True

    def confirm_discard(self) -> bool:
        if not self.modified:
            return True
        ans = messagebox.askyesnocancel(
            "Unsaved changes", "Save changes before continuing?"
        )
        if ans is None:
            return False
        if ans:
            return self.save()
        return True

    def on_quit(self):
        if self.confirm_discard():
            self.root.destroy()

    # -- Source <-> model sync --------------------------------------------------
    def set_source_text(self, text: str):
        """Replace the source text without triggering a grid refresh."""
        self._suppress_source_event = True
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)
        self.text.edit_modified(False)
        self._suppress_source_event = False

    def on_source_modified(self, _event):
        if not self.text.edit_modified():
            return
        self.text.edit_modified(False)
        if self._suppress_source_event:
            return
        self.set_modified(True)
        # Debounce: refresh grids shortly after typing pauses.
        if self._refresh_job is not None:
            self.root.after_cancel(self._refresh_job)
        self._refresh_job = self.root.after(450, self.refresh_grids_from_source)

    def parse_source(self, report: bool = False) -> bool:
        """Parse the source text into ``self.doc``. Returns True on success."""
        text = self.text.get("1.0", "end-1c")
        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            if report:
                self.status.set(f"YAML error: {exc}".split("\n")[0])
            return False
        self.doc = doc if isinstance(doc, dict) else {}
        if report:
            n = sum(1 for _ in iter_grids(self.doc))
            self.status.set(f"Parsed OK — {n} view grid(s).")
        return True

    def refresh_grids_from_source(self):
        self._refresh_job = None
        if self.parse_source(report=True):
            self.rebuild_grids()

    def regen_source_from_doc(self):
        """Rewrite the YAML body from ``self.doc``, preserving the header comments."""
        header = extract_header(self.text.get("1.0", "end-1c"))
        body = dump_doc(self.doc)
        self.set_source_text(header + body)
        self.set_modified(True)

    # -- Grid rendering ---------------------------------------------------------
    def rebuild_grids(self):
        # Remember the selected tab so source edits don't jump the view around.
        try:
            prev = self.notebook.index(self.notebook.select())
        except tk.TclError:
            prev = 0
        for tab in self.notebook.tabs():
            self.notebook.forget(tab)

        grids = list(iter_grids(self.doc))
        if not grids:
            frame = ttk.Frame(self.notebook)
            ttk.Label(
                frame, text="No view grids in this document.", padding=12
            ).pack(anchor="nw")
            self.notebook.add(frame, text="(none)")
            return

        # weldb history is append-only: only the latest map (revision) is the
        # authoritative, editable layout. Grids from earlier revisions are shown
        # read-only so the visual editor does not silently rewrite history.
        last_map = max(mi for mi, *_ in grids)
        for mi, vi, rev, name, grid in grids:
            self._build_grid_tab(mi, vi, rev, name, grid, editable=(mi == last_map))

        if 0 <= prev < len(self.notebook.tabs()):
            self.notebook.select(prev)

    def _build_grid_tab(
        self, mi: int, vi: int, rev: str, name: str, grid: list, editable: bool = True
    ):
        tab = ttk.Frame(self.notebook)
        marker = "" if editable else " (read-only)"
        self.notebook.add(tab, text=f"{rev} · {name}{marker}")

        rows = len(grid)
        cols = max((len(r) for r in grid), default=0)

        # Per-tab toolbar: dimensions + structural editing.
        top = ttk.Frame(tab, padding=(4, 4))
        top.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(top, text=f"{rows} × {cols}").pack(side=tk.LEFT)
        if editable:
            for txt, cmd in (
                ("+Row", lambda: self._add_row(mi, vi)),
                ("−Row", lambda: self._del_row(mi, vi)),
                ("+Col", lambda: self._add_col(mi, vi)),
                ("−Col", lambda: self._del_col(mi, vi)),
            ):
                ttk.Button(top, text=txt, width=6, command=cmd).pack(side=tk.LEFT, padx=(8, 0))
        else:
            ttk.Label(
                top, text="historical revision — append a new revision to change the layout"
            ).pack(side=tk.LEFT, padx=(8, 0))

        # Scrollable cell area.
        body = ttk.Frame(tab)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(body, highlightthickness=0)
        vsb = ttk.Scrollbar(body, orient=tk.VERTICAL, command=canvas.yview)
        hsb = ttk.Scrollbar(body, orient=tk.HORIZONTAL, command=canvas.xview)
        canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        cells = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=cells, anchor="nw")
        cells.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        _bind_wheel(canvas)

        # Column index headers.
        for c in range(cols):
            tk.Label(
                cells, text=str(c), font=self.mono, fg="#666", padx=2
            ).grid(row=0, column=c + 1, sticky="nsew")

        # Column widths sized to the longest label in each column (in chars).
        widths = []
        for c in range(cols):
            longest = max((len(str(grid[r][c])) for r in range(rows) if c < len(grid[r])), default=0)
            widths.append(min(max(longest + 1, 4), 16))

        for r in range(rows):
            tk.Label(
                cells, text=str(r), font=self.mono, fg="#666", padx=2
            ).grid(row=r + 1, column=0, sticky="nsew")
            for c in range(cols):
                value = str(grid[r][c]) if c < len(grid[r]) else ""
                var = tk.StringVar(value=value)
                entry = tk.Entry(
                    cells,
                    textvariable=var,
                    width=widths[c],
                    font=self.mono,
                    justify="center",
                    relief="solid",
                    borderwidth=1,
                    bg=cell_fill(value),
                )
                entry.grid(row=r + 1, column=c + 1, sticky="nsew")
                if editable:
                    var.trace_add(
                        "write",
                        lambda *_a, mi=mi, vi=vi, r=r, c=c, var=var, entry=entry: self._on_cell_edit(
                            mi, vi, r, c, var, entry
                        ),
                    )
                else:
                    entry.configure(state="readonly", readonlybackground=cell_fill(value))

    def _on_cell_edit(self, mi, vi, r, c, var, entry):
        value = var.get()
        try:
            row = self.doc["maps"][mi]["views"][vi]["grid"][r]
        except (KeyError, IndexError, TypeError):
            return
        while len(row) <= c:  # tolerate ragged rows
            row.append("")
        row[c] = value
        entry.configure(bg=cell_fill(value))
        self.regen_source_from_doc()

    # -- Structural grid edits --------------------------------------------------
    def _grid_of(self, mi, vi):
        try:
            return self.doc["maps"][mi]["views"][vi]["grid"]
        except (KeyError, IndexError, TypeError):
            return None

    def _add_row(self, mi, vi):
        grid = self._grid_of(mi, vi)
        if grid is None:
            return
        cols = max((len(r) for r in grid), default=1)
        grid.append(["" for _ in range(cols)])
        self._after_structural_change()

    def _del_row(self, mi, vi):
        grid = self._grid_of(mi, vi)
        if grid and len(grid) > 1:
            grid.pop()
            self._after_structural_change()

    def _add_col(self, mi, vi):
        grid = self._grid_of(mi, vi)
        if grid is None:
            return
        for row in grid:
            row.append("")
        self._after_structural_change()

    def _del_col(self, mi, vi):
        grid = self._grid_of(mi, vi)
        if grid and max((len(r) for r in grid), default=0) > 1:
            for row in grid:
                if row:
                    row.pop()
            self._after_structural_change()

    def _after_structural_change(self):
        self.regen_source_from_doc()
        self.rebuild_grids()

    # -- Misc -------------------------------------------------------------------
    def set_modified(self, value: bool):
        if value != self.modified:
            self.modified = value
            self.update_title()

    def update_title(self):
        name = str(self.path) if self.path else "(untitled)"
        star = "*" if self.modified else ""
        self.root.title(f"{star}{name} — weldb visual editor")

    def show_about(self):
        messagebox.showinfo(
            "About",
            "weldb visual editor\n\n"
            "A .weldb file is YAML. Edit the source on the left; each view's grid "
            "is shown on the right as editable, color-coded cells.\n\n"
            "Editing a cell rewrites the YAML body (header comments are kept). "
            "Edit the source and switch to a grid tab (or click 'Refresh grids') "
            "to update the grids.",
        )


def _bind_wheel(canvas: tk.Canvas):
    """Vertical/horizontal mouse-wheel scrolling while the pointer is over canvas.

    Handles both the Windows/macOS ``<MouseWheel>`` event (with ``event.delta``)
    and the X11/Linux ``<Button-4>``/``<Button-5>`` events, so scrolling works on
    all three platforms.
    """
    def _on_wheel(event):
        canvas.yview_scroll(int(-event.delta / 120), "units")

    def _on_shift_wheel(event):
        canvas.xview_scroll(int(-event.delta / 120), "units")

    def _on_button4(_event):  # X11 wheel up
        canvas.yview_scroll(-1, "units")

    def _on_button5(_event):  # X11 wheel down
        canvas.yview_scroll(1, "units")

    canvas.bind("<Enter>", lambda e: (
        canvas.bind_all("<MouseWheel>", _on_wheel),
        canvas.bind_all("<Shift-MouseWheel>", _on_shift_wheel),
        canvas.bind_all("<Button-4>", _on_button4),
        canvas.bind_all("<Button-5>", _on_button5),
    ))
    canvas.bind("<Leave>", lambda e: (
        canvas.unbind_all("<MouseWheel>"),
        canvas.unbind_all("<Shift-MouseWheel>"),
        canvas.unbind_all("<Button-4>"),
        canvas.unbind_all("<Button-5>"),
    ))


def _build_arg_parser() -> argparse.ArgumentParser:
    """CLI: an optional file to open on launch (positional ``file``)."""
    parser = argparse.ArgumentParser(
        prog="weldb_visual_editor",
        description=(
            "Open the weldb visual editor. Pass a .weldb (or YAML) file to open it "
            "directly on launch — handy for scripting, e.g. after generating a "
            "panel. Omit it to start empty and use File > Open."
        ),
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="Path to a .weldb/.yaml file to open on launch. If omitted, the "
        "editor starts empty.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(sys.argv[1:] if argv is None else argv)

    initial: Path | None = None
    if args.file:
        # Validate before launching the GUI so a bad path from a script fails
        # fast with a clear message and a non-zero exit code, rather than opening
        # an empty window.
        initial = Path(args.file).expanduser()
        if not initial.exists():
            sys.stderr.write(f"weldb_visual_editor: file not found: {initial}\n")
            return 2
        if not initial.is_file():
            sys.stderr.write(f"weldb_visual_editor: not a file: {initial}\n")
            return 2

    root = tk.Tk()
    WeldbEditor(root, str(initial) if initial else None)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
