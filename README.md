# rp-hex-tool

Implementare inițială pentru cerințele de management profile + conversie bidirecțională Fields ↔ Intel HEX.

## Funcționalități incluse
- Model `Project` cu `FieldDef` extensibil (N câmpuri), validare coliziuni/adrese/lungimi.
- Conversie `Fields -> bytes -> Intel HEX` (generate + patch mode).
- Conversie `HEX -> bytes -> Fields` (readback cu status `not present in HEX`).
- Verify PASS/FAIL per field.
- Diff pe intervalele mapate.
- Batch processing (`csv/json`) cu naming template și log rotativ.
- CLI pentru rulare în CI/pipeline.
- GUI desktop (Tkinter) pentru creare HEX cu formular dinamic pe baza proiectului (inclusiv sample „parts SN”).

## Sample Project (parts SN)
- Fișier: `examples/sample_parts_project.json`
- Include câmpuri predefinite:
  - `part_sn`
  - `hw_sn`
  - `sw_sn`

## CLI
```bash
python -m rp_hex_tool.cli generate --project project.json --config config.json --output out.hex
python -m rp_hex_tool.cli patch --project project.json --template fw.hex --config config.json --output out.hex
python -m rp_hex_tool.cli readback --project project.json --hex out.hex
python -m rp_hex_tool.cli verify --project project.json --config config.json --hex out.hex
python -m rp_hex_tool.cli diff --project project.json --left base.hex --right out.hex
python -m rp_hex_tool.cli batch --project project.json --input items.csv --output-dir out --mode patch --template fw.hex --naming "{serial}_{date}.hex"
```

## GUI
```bash
PYTHONPATH=src python -m rp_hex_tool.gui
# sau după instalare pachet:
# rp-hex-gui
```

Ce oferă GUI-ul:
- Load project JSON + formular dinamic.
- Live validation pe câmpuri.
- Load config values JSON cu mod `merge`/`override`.
- Preview înainte de export.
- Generate / Patch / Readback / Verify.
