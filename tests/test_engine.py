from rp_hex_tool.engine import diff_ranges, generate_hex, parse_memory, patch_hex, read_fields_from_memory, verify
from rp_hex_tool.hexfile import detect_format, parse_intel_hex, write_intel_hex
from rp_hex_tool.models import FieldDef, Project


def _project() -> Project:
    return Project(
        schemaVersion=1,
        name="demo",
        record_length=16,
        fields=[
            FieldDef(name="Serial", key="serial", address=0x10010, length_bytes=8, required=True, padding=0x20),
            FieldDef(name="HW", key="hw", address=0x10020, length_bytes=4, padding=0x00),
            FieldDef(name="SW", key="sw", address=0x10024, length_bytes=4, padding=0x00),
        ],
    )


def test_round_trip_generate_readback_verify():
    project = _project()
    values = {"serial": "AB12", "hw": "A1", "sw": "B2"}

    hex_out, warnings = generate_hex(project, values)
    assert not warnings
    mem = parse_intel_hex(hex_out)

    back, status = read_fields_from_memory(project, mem)
    assert status == {"serial": "ok", "hw": "ok", "sw": "ok"}
    assert back["serial"] == "AB12"

    check = verify(project, values, hex_out)
    assert all(v == "PASS" for v in check.values())


def test_patch_only_changes_mapped_ranges():
    project = _project()
    values = {"serial": "XYZ", "hw": "H1", "sw": "S1"}

    base_mem = {0x10000 + i: 0xAA for i in range(0, 0x40)}
    base_hex = write_intel_hex(base_mem)

    out_hex, _ = patch_hex(project, base_hex, values)
    diff = diff_ranges(project, base_hex, out_hex)

    assert diff["serial"]
    assert diff["hw"]
    assert diff["sw"]

    out_mem = parse_intel_hex(out_hex)
    assert out_mem[0x10000] == 0xAA


def test_overlap_validation():
    project = Project(
        schemaVersion=1,
        name="bad",
        fields=[
            FieldDef(name="A", key="a", address=0x10, length_bytes=8),
            FieldDef(name="B", key="b", address=0x17, length_bytes=4),
        ],
    )
    errors = project.validate()
    assert any("range collision" in e for e in errors)


def test_generate_srec_round_trip():
    project = _project()
    values = {"serial": "AB12", "hw": "A1", "sw": "B2"}

    out, warnings = generate_hex(project, values, fmt="srec")
    assert not warnings
    assert detect_format(out) == "srec"
    mem = parse_memory(out)

    back, status = read_fields_from_memory(project, mem)
    assert status == {"serial": "ok", "hw": "ok", "sw": "ok"}
    assert back["serial"] == "AB12"


def test_patch_intel_template_and_emit_srec():
    project = _project()
    values = {"serial": "XYZ", "hw": "H1", "sw": "S1"}
    base_mem = {0x10000 + i: 0xAA for i in range(0, 0x40)}
    base_hex = write_intel_hex(base_mem)

    out_srec, _ = patch_hex(project, base_hex, values, fmt="srec")
    assert detect_format(out_srec) == "srec"

    diff = diff_ranges(project, base_hex, out_srec)
    assert diff["serial"]
    assert diff["hw"]
    assert diff["sw"]

    check = verify(project, values, out_srec)
    assert all(v == "PASS" for v in check.values())
