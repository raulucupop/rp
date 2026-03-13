from __future__ import annotations

import json
from pathlib import Path
import secrets
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from .engine import (
        generate_hex,
        load_project,
        parse_memory,
        read_fields_from_memory,
    )
    from .models import Project
except ImportError:
    # Support execution as a top-level script in bundled contexts.
    from rp_hex_tool.engine import (
        generate_hex,
        load_project,
        parse_memory,
        read_fields_from_memory,
    )
    from rp_hex_tool.models import Project


_EMBEDDED_SAMPLE_PROJECT_JSON = """
{
  "schemaVersion": 1,
  "name": "Sample Parts SN",
  "record_length": 16,
  "memory_limit": 131072,
  "template_hex": null,
  "fields": [
    {
      "name": "Mercedes SG IDENT",
      "key": "hardware_part_number",
      "address": 0,
      "length_bytes": 10,
      "encoding": "ascii",
      "allowed_charset": "printable_ascii",
      "padding": 0,
      "pad_direction": "right",
      "trim_rule": "none",
      "required": true,
      "default_value": "5819019601",
      "allow_truncate": false
    },
    {
      "name": "Hardware Version Info (input: dec)",
      "key": "hardware_version_info",
      "address": 10,
      "length_bytes": 3,
      "encoding": "ascii",
      "input_format": "dec",
      "allowed_charset": "regex:[0-9]{1,2}( [0-9]{1,2}){2}",
      "padding": 0,
      "pad_direction": "right",
      "trim_rule": "none",
      "required": true,
      "default_value": "25 46 01",
      "allow_truncate": false
    },
    {
      "name": "Hardware Supplier Info (input: hex, fixed)",
      "key": "hardware_supplier_info",
      "address": 13,
      "length_bytes": 2,
      "encoding": "ascii",
      "input_format": "hex",
      "allowed_charset": "regex:[0-9A-Fa-f]*",
      "padding": 0,
      "pad_direction": "right",
      "trim_rule": "none",
      "required": true,
      "default_value": "3B01",
      "allow_truncate": false
    },
    {
      "name": "ECU Serial Number (input: ascii)",
      "key": "ecu_serial_number",
      "address": 15,
      "length_bytes": 33,
      "encoding": "ascii",
      "allowed_charset": "printable_ascii",
      "padding": 0,
      "pad_direction": "right",
      "trim_rule": "none",
      "required": true,
      "default_value": "",
      "allow_truncate": false
    },
    {
      "name": "Aumovio PCB assembly (input: ascii)",
      "key": "aumovio_pcb_assembly",
      "address": 48,
      "length_bytes": 34,
      "encoding": "ascii",
      "allowed_charset": "printable_ascii",
      "padding": 0,
      "pad_direction": "right",
      "trim_rule": "none",
      "required": true,
      "default_value": "AAA2910270100000000000000000000000",
      "allow_truncate": false
    },
    {
      "name": "HW compatibility index (input: hex)",
      "key": "hw_compatibility_index",
      "address": 82,
      "length_bytes": 3,
      "encoding": "ascii",
      "input_format": "hex",
      "allowed_charset": "regex:[0-9A-Fa-f]*",
      "padding": 0,
      "pad_direction": "right",
      "trim_rule": "none",
      "required": true,
      "default_value": "000001",
      "allow_truncate": false
    },
    {
      "name": "KML IRK (input: hex)",
      "key": "kml_irk",
      "address": 85,
      "length_bytes": 16,
      "encoding": "ascii",
      "input_format": "hex",
      "allowed_charset": "regex:[0-9A-Fa-f]*",
      "padding": 0,
      "pad_direction": "right",
      "trim_rule": "none",
      "required": true,
      "default_value": "",
      "allow_truncate": false
    },
    {
      "name": "KML Vehicle Bt Address (input: hex)",
      "key": "kml_vehicle_bt_address",
      "address": 101,
      "length_bytes": 6,
      "encoding": "ascii",
      "input_format": "hex",
      "allowed_charset": "regex:[0-9A-Fa-f]*",
      "padding": 0,
      "pad_direction": "right",
      "trim_rule": "none",
      "required": true,
      "default_value": "",
      "allow_truncate": false
    },
    {
      "name": "VHL WCC (input: hex)",
      "key": "vhl_wcc",
      "address": 107,
      "length_bytes": 1,
      "encoding": "ascii",
      "input_format": "hex",
      "allowed_charset": "regex:[0-9A-Fa-f]*",
      "padding": 0,
      "pad_direction": "right",
      "trim_rule": "none",
      "required": true,
      "default_value": "01",
      "allow_truncate": false
    }
  ]
}
"""


class HexGuiApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("MB EA L EIS - Sample Parts - EOL Data Generator")
        self.project: Project | None = None
        self.field_vars: dict[str, tk.StringVar] = {}
        self.field_entries: list[ttk.Entry] = []
        self.last_verify_result: dict[str, str] | None = None

        self.project_path = tk.StringVar(value="examples/sample_parts_project.json")
        self.input_hex_path = tk.StringVar(value="")
        self.output_format = tk.StringVar(value="ihex")
        self.version_text = tk.StringVar(value="Version 001 of 13.03.2026")

        self._build_layout()
        self._try_load_default_project()

    def _build_layout(self) -> None:
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill=tk.X)

        ttk.Label(top, text="Project:").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.project_path, width=60).grid(row=0, column=1, sticky="ew")
        ttk.Button(top, text="Browse", command=self.browse_project).grid(row=0, column=2, padx=4)
        ttk.Button(top, text="Load Project", command=self.load_project).grid(row=0, column=3, padx=4)

        ttk.Label(top, text="Readback file:").grid(row=1, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.input_hex_path, width=60).grid(row=1, column=1, sticky="ew")
        ttk.Button(top, text="Browse", command=self.browse_input_hex).grid(row=1, column=2, padx=4)
        ttk.Button(top, text="Readback", command=self.readback).grid(row=1, column=3, padx=4)

        ttk.Label(top, text="Output format:").grid(row=2, column=0, sticky="w")
        fmt = ttk.Combobox(top, textvariable=self.output_format, values=["ihex", "srec"], state="readonly", width=10)
        fmt.grid(row=2, column=1, sticky="w")
        fmt.current(0)

        ttk.Label(
            top,
            text="Double the data to fill the shadow memory too: Yes",
        ).grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Label(top, textvariable=self.version_text).grid(row=3, column=3, sticky="e")

        top.columnconfigure(1, weight=1)

        self.form_frame = ttk.LabelFrame(self.root, text="Fields", padding=10)
        self.form_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        actions = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        actions.pack(fill=tk.X)
        ttk.Button(actions, text="Preview", command=self.preview).pack(side=tk.LEFT)
        ttk.Button(actions, text="Generate HEX", command=self.generate).pack(side=tk.LEFT, padx=5)
        ttk.Button(actions, text="Verify", command=self.run_verify).pack(side=tk.LEFT, padx=5)

        self.preview_text = tk.Text(self.root, height=12)
        self.preview_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.preview_text.tag_configure("status_pass", foreground="green")
        self.preview_text.tag_configure("status_fail", foreground="red")

        footer = ttk.Frame(self.root, padding=(10, 0, 10, 6))
        footer.pack(fill=tk.X)
        ttk.Label(footer, text="© Copyright RP 2026").pack(anchor="e")

    def _try_load_default_project(self) -> None:
        try:
            payload = json.loads(_EMBEDDED_SAMPLE_PROJECT_JSON)
            self._apply_project(Project.from_dict(payload), "embedded sample_parts_project.json")
            self.project_path.set("embedded: sample_parts_project.json")
            return
        except Exception:
            pass

        default_path = self._resolve_default_project_path()
        if default_path is not None:
            self.project_path.set(str(default_path))
            self.load_project()

    def _resolve_default_project_path(self) -> Path | None:
        rel = Path("examples") / "sample_parts_project.json"
        candidates = [Path.cwd() / rel]
        if getattr(sys, "frozen", False):
            candidates.append(Path(sys.executable).resolve().parent / rel)
        else:
            candidates.append(Path(__file__).resolve().parents[2] / rel)
            candidates.append(Path(__file__).resolve().parents[3] / rel)
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def browse_project(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json"), ("All files", "*")])
        if path:
            self.project_path.set(path)

    def browse_input_hex(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("HEX/SREC files", "*.hex *.srec"), ("All files", "*")])
        if path:
            self.input_hex_path.set(path)

    def load_project(self) -> None:
        raw_path = self.project_path.get().strip()
        if not raw_path:
            messagebox.showerror("Project load error", "Project path is empty. Select a project JSON file.")
            return

        project_path = Path(raw_path).expanduser()
        if project_path.is_dir():
            messagebox.showerror(
                "Project load error",
                f"'{project_path}' is a folder. Please select a project JSON file.",
            )
            return
        if not project_path.exists():
            messagebox.showerror("Project load error", f"Project file not found: {project_path}")
            return

        try:
            project = load_project(str(project_path))
        except Exception as exc:
            messagebox.showerror("Project load error", str(exc))
            return

        self._apply_project(project, str(project_path))

    def _apply_project(self, project: Project, source: str) -> None:
        self.project = project

        for child in self.form_frame.winfo_children():
            child.destroy()
        self.field_vars.clear()
        self.field_entries.clear()

        for row, field in enumerate(project.fields):
            ttk.Label(self.form_frame, text=f"{field.name} ({field.key})").grid(row=row, column=0, sticky="w", pady=2)
            initial_value = field.default_value or ""
            if field.key == "vhl_wcc":
                initial_value = "01"
            var = tk.StringVar(value=initial_value)
            entry = ttk.Entry(self.form_frame, textvariable=var, width=50)
            entry.grid(row=row, column=1, sticky="ew", padx=4)
            if field.key == "vhl_wcc":
                entry.configure(state="readonly")
            if field.key == "kml_vehicle_bt_address":
                ttk.Button(
                    self.form_frame,
                    text="Random",
                    command=self._randomize_kml_vehicle_bt_address,
                ).grid(row=row, column=3, sticky="w", padx=(4, 0))
            if field.key == "kml_irk":
                ttk.Button(
                    self.form_frame,
                    text="Random",
                    command=self._randomize_kml_irk,
                ).grid(row=row, column=3, sticky="w", padx=(4, 0))
            entry.bind("<Return>", self._on_field_enter)
            ttk.Label(
                self.form_frame,
                text=f"addr=0x{field.address:X}, len={field.length_bytes}, charset={field.allowed_charset}",
            ).grid(row=row, column=2, sticky="w")
            var.trace_add("write", lambda *_args, f=field, v=var, e=entry: self._validate_live(f, v, e))
            self.field_vars[field.key] = var
            self.field_entries.append(entry)

        self.form_frame.columnconfigure(1, weight=1)
        self.preview_text.insert("end", f"Loaded project: {project.name} ({source})\n")

    def _set_field_value(self, key: str, value: str) -> None:
        var = self.field_vars.get(key)
        if var is None:
            return
        var.set(value.upper())

    def _randomize_kml_vehicle_bt_address(self) -> None:
        first_byte = 0xC0 | secrets.randbelow(0x40)
        tail = secrets.token_bytes(5)
        value = bytes([first_byte]) + tail
        self._set_field_value("kml_vehicle_bt_address", value.hex().upper())

    def _randomize_kml_irk(self) -> None:
        self._set_field_value("kml_irk", secrets.token_bytes(16).hex().upper())

    def _on_field_enter(self, event: tk.Event) -> str:
        widget = event.widget
        try:
            idx = self.field_entries.index(widget)
        except ValueError:
            return "break"
        if idx + 1 < len(self.field_entries):
            self.field_entries[idx + 1].focus_set()
        else:
            widget.tk_focusNext().focus_set()
        return "break"

    def _validate_live(self, field, var, entry) -> None:
        errors = field.validate_value(var.get())
        if errors:
            entry.configure(foreground="red")
        else:
            entry.configure(foreground="black")

    def _collect_values(self) -> dict[str, str]:
        return {key: var.get() for key, var in self.field_vars.items()}

    def _validate_fields(self, values: dict[str, str]) -> dict[str, str]:
        invalid_fields: dict[str, str] = {}
        if not self.project:
            return invalid_fields
        for field in self.project.fields:
            value = values.get(field.key, "")
            if field.required and not value:
                invalid_fields[field.key] = "required"
                continue
            errors = field.validate_value(value)
            if errors:
                invalid_fields[field.key] = ", ".join(errors)
        return invalid_fields

    def _shadow_offset(self) -> int | None:
        return 0x02000000

    def _ask_output_path(self) -> str:
        default_ext = ".hex"
        if self.output_format.get() == "srec":
            filetypes = [("HEX files", "*.hex"), ("S-record files", "*.srec"), ("All files", "*")]
        else:
            filetypes = [("HEX files", "*.hex"), ("S-record files", "*.srec"), ("All files", "*")]
        return filedialog.asksaveasfilename(defaultextension=default_ext, filetypes=filetypes)

    def preview(self) -> None:
        if not self.project:
            return
        values = self._collect_values()
        try:
            text, warnings = generate_hex(
                self.project,
                values,
                fmt=self.output_format.get(),
                shadow_offset=self._shadow_offset(),
            )
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
        invalid_fields = self._validate_fields(values)
        if invalid_fields:
            reason = "; ".join(f"{k}: {v}" for k, v in invalid_fields.items())
            self.preview_text.delete("1.0", "end")
            self.preview_text.insert("end", "Verify result: ")
            self.preview_text.insert("end", "FAIL\n", "status_fail")
            self.preview_text.insert("end", f"Reason: {reason}\n")
            messagebox.showerror("Generate blocked", f"Verify failed. HEX was not generated.\n{reason}")
            return

        output_path = self._ask_output_path()
        if not output_path:
            return
        try:
            text, warnings = generate_hex(
                self.project,
                values,
                fmt=self.output_format.get(),
                shadow_offset=self._shadow_offset(),
            )
            Path(output_path).write_text(text, encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("Generate error", str(exc))
            return
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("end", f"Generated: {output_path}\n")
        if warnings:
            self.preview_text.insert("end", "Warnings:\n" + "\n".join(warnings) + "\n")

    def readback(self) -> None:
        if not self.project:
            return
        raw_path = self.input_hex_path.get().strip()
        if not raw_path:
            messagebox.showerror("Readback error", "Select a readback file first.")
            return
        input_path = Path(raw_path).expanduser()
        if input_path.is_dir():
            messagebox.showerror("Readback error", f"'{input_path}' is a folder. Please select a file.")
            return
        if not input_path.exists():
            messagebox.showerror("Readback error", f"Readback file not found: {input_path}")
            return
        try:
            text = input_path.read_text(encoding="utf-8")
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
        values = self._collect_values()
        invalid_fields = self._validate_fields(values)
        if invalid_fields:
            result = {field.key: "PASS" for field in self.project.fields}
            for key in invalid_fields:
                result[key] = "FAIL"
            self.preview_text.delete("1.0", "end")
            self.last_verify_result = result
            self.preview_text.insert("end", "Verify result: ")
            self.preview_text.insert("end", "FAIL\n", "status_fail")
            reason = "; ".join(f"{k}: {v}" for k, v in invalid_fields.items())
            self.preview_text.insert("end", f"Reason: {reason}\n")
            for field in self.project.fields:
                state = result.get(field.key, "FAIL")
                tag = "status_pass" if state == "PASS" else "status_fail"
                self.preview_text.insert("end", f"{field.key}: ")
                self.preview_text.insert("end", state + "\n", tag)
            messagebox.showerror("Verify error", reason)
            return
        result = {field.key: "PASS" for field in self.project.fields}
        self.preview_text.delete("1.0", "end")
        self.last_verify_result = result
        overall = "PASS"
        overall_tag = "status_pass"
        self.preview_text.insert("end", "Verify result: ")
        self.preview_text.insert("end", overall + "\n", overall_tag)
        for key, state in result.items():
            tag = "status_pass" if state == "PASS" else "status_fail"
            self.preview_text.insert("end", f"{key}: ")
            self.preview_text.insert("end", state + "\n", tag)


def main() -> int:
    root = tk.Tk()
    HexGuiApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

