from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .engine import (
    generate_hex,
    load_config,
    load_project,
    patch_hex,
    parse_memory,
    read_fields_from_memory,
    verify,
)
from .models import Project


class HexGuiApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("RP HEX Creator - Sample Parts SN")
        self.project: Project | None = None
        self.field_vars: dict[str, tk.StringVar] = {}

        self.project_path = tk.StringVar(value="examples/sample_parts_project.json")
        self.template_path = tk.StringVar(value="")
        self.input_hex_path = tk.StringVar(value="")
        self.output_path = tk.StringVar(value="output.hex")
        self.config_mode = tk.StringVar(value="merge")
        self.output_format = tk.StringVar(value="ihex")

        self._build_layout()
        self._try_load_default_project()

    def _build_layout(self) -> None:
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill=tk.X)

        ttk.Label(top, text="Project:").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.project_path, width=60).grid(row=0, column=1, sticky="ew")
        ttk.Button(top, text="Load Project", command=self.load_project).grid(row=0, column=2, padx=4)

        ttk.Label(top, text="Template file (patch mode):").grid(row=1, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.template_path, width=60).grid(row=1, column=1, sticky="ew")
        ttk.Button(top, text="Browse", command=self.browse_template).grid(row=1, column=2, padx=4)

        ttk.Label(top, text="Output file:").grid(row=2, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.output_path, width=60).grid(row=2, column=1, sticky="ew")
        ttk.Button(top, text="Browse", command=self.browse_output).grid(row=2, column=2, padx=4)

        ttk.Label(top, text="Readback file:").grid(row=3, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.input_hex_path, width=60).grid(row=3, column=1, sticky="ew")
        ttk.Button(top, text="Browse", command=self.browse_input_hex).grid(row=3, column=2, padx=4)

        ttk.Label(top, text="Output format:").grid(row=4, column=0, sticky="w")
        fmt = ttk.Combobox(top, textvariable=self.output_format, values=["ihex", "srec"], state="readonly", width=10)
        fmt.grid(row=4, column=1, sticky="w")
        fmt.current(0)

        top.columnconfigure(1, weight=1)

        cfg_frame = ttk.LabelFrame(self.root, text="Config load mode", padding=8)
        cfg_frame.pack(fill=tk.X, padx=10)
        ttk.Radiobutton(cfg_frame, text="Merge (completează doar câmpurile goale)", variable=self.config_mode, value="merge").pack(anchor="w")
        ttk.Radiobutton(cfg_frame, text="Override (înlocuiește valorile existente)", variable=self.config_mode, value="override").pack(anchor="w")
        ttk.Button(cfg_frame, text="Load Values Config (JSON)", command=self.load_values_config).pack(anchor="w", pady=(6, 0))

        self.form_frame = ttk.LabelFrame(self.root, text="Fields", padding=10)
        self.form_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        actions = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        actions.pack(fill=tk.X)
        ttk.Button(actions, text="Preview", command=self.preview).pack(side=tk.LEFT)
        ttk.Button(actions, text="Generate HEX", command=self.generate).pack(side=tk.LEFT, padx=5)
        ttk.Button(actions, text="Patch HEX", command=self.patch).pack(side=tk.LEFT, padx=5)
        ttk.Button(actions, text="Readback", command=self.readback).pack(side=tk.LEFT, padx=5)
        ttk.Button(actions, text="Verify", command=self.run_verify).pack(side=tk.LEFT, padx=5)

        self.preview_text = tk.Text(self.root, height=12)
        self.preview_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

    def _try_load_default_project(self) -> None:
        if Path(self.project_path.get()).exists():
            self.load_project()

    def browse_template(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("HEX/SREC files", "*.hex *.srec"), ("All files", "*")])
        if path:
            self.template_path.set(path)

    def browse_output(self) -> None:
        path = filedialog.asksaveasfilename(
            filetypes=[("HEX files", "*.hex"), ("S-record files", "*.srec"), ("All files", "*")]
        )
        if path:
            self.output_path.set(path)

    def browse_input_hex(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("HEX/SREC files", "*.hex *.srec"), ("All files", "*")])
        if path:
            self.input_hex_path.set(path)

    def load_project(self) -> None:
        try:
            self.project = load_project(self.project_path.get())
        except Exception as exc:
            messagebox.showerror("Project load error", str(exc))
            return

        for child in self.form_frame.winfo_children():
            child.destroy()
        self.field_vars.clear()

        for row, field in enumerate(self.project.fields):
            ttk.Label(self.form_frame, text=f"{field.name} ({field.key})").grid(row=row, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=field.default_value or "")
            entry = ttk.Entry(self.form_frame, textvariable=var, width=50)
            entry.grid(row=row, column=1, sticky="ew", padx=4)
            ttk.Label(
                self.form_frame,
                text=f"addr={field.address:#x}, len={field.length_bytes}, charset={field.allowed_charset}",
            ).grid(row=row, column=2, sticky="w")
            var.trace_add("write", lambda *_args, f=field, v=var, e=entry: self._validate_live(f, v, e))
            self.field_vars[field.key] = var

        self.form_frame.columnconfigure(1, weight=1)
        self.preview_text.insert("end", f"Loaded project: {self.project.name}\n")

    def _validate_live(self, field, var, entry) -> None:
        errors = field.validate_value(var.get())
        if errors:
            entry.configure(foreground="red")
        else:
            entry.configure(foreground="black")

    def _collect_values(self) -> dict[str, str]:
        return {key: var.get() for key, var in self.field_vars.items()}

    def load_values_config(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json"), ("All files", "*")])
        if not path:
            return
        cfg = load_config(path)
        current = self._collect_values()
        merged = cfg.merge(current) if self.config_mode.get() == "merge" else {**current, **cfg.values}
        for key, value in merged.items():
            if key in self.field_vars:
                self.field_vars[key].set(value)
        missing = [k for k in cfg.values if k not in self.field_vars]
        if missing:
            messagebox.showwarning("Config warning", f"Keys not in current project: {', '.join(missing)}")

    def preview(self) -> None:
        if not self.project:
            return
        values = self._collect_values()
        try:
            text, warnings = generate_hex(self.project, values, fmt=self.output_format.get())
        except Exception as exc:
            messagebox.showerror("Preview error", str(exc))
            return
        self.preview_text.delete("1.0", "end")
        if warnings:
            self.preview_text.insert("end", "Warnings:\n" + "\n".join(warnings) + "\n\n")
        self.preview_text.insert("end", text)

    def generate(self) -> None:
        if not self.project:
            return
        values = self._collect_values()
        try:
            text, warnings = generate_hex(self.project, values, fmt=self.output_format.get())
            Path(self.output_path.get()).write_text(text, encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("Generate error", str(exc))
            return
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("end", f"Generated: {self.output_path.get()}\n")
        if warnings:
            self.preview_text.insert("end", "Warnings:\n" + "\n".join(warnings) + "\n")

    def patch(self) -> None:
        if not self.project:
            return
        values = self._collect_values()
        try:
            template = Path(self.template_path.get()).read_text(encoding="utf-8")
            text, warnings = patch_hex(self.project, template, values, fmt=self.output_format.get())
            Path(self.output_path.get()).write_text(text, encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("Patch error", str(exc))
            return
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("end", f"Patched: {self.output_path.get()}\n")
        if warnings:
            self.preview_text.insert("end", "Warnings:\n" + "\n".join(warnings) + "\n")

    def readback(self) -> None:
        if not self.project:
            return
        try:
            text = Path(self.input_hex_path.get()).read_text(encoding="utf-8")
            memory = parse_memory(text)
            values, status = read_fields_from_memory(self.project, memory)
        except Exception as exc:
            messagebox.showerror("Readback error", str(exc))
            return

        for key, state in status.items():
            if state == "ok":
                self.field_vars[key].set(values.get(key, ""))

        report = "\n".join(f"{key}: {state}" for key, state in status.items())
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("end", f"Readback from {self.input_hex_path.get()}\n{report}\n")

    def run_verify(self) -> None:
        if not self.project:
            return
        try:
            text = Path(self.input_hex_path.get() or self.output_path.get()).read_text(encoding="utf-8")
            result = verify(self.project, self._collect_values(), text)
        except Exception as exc:
            messagebox.showerror("Verify error", str(exc))
            return

        report = "\n".join(f"{k}: {v}" for k, v in result.items())
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("end", report + "\n")


def main() -> int:
    root = tk.Tk()
    HexGuiApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
