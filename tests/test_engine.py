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


def test_hex_input_uses_byte_length_not_char_length():
    project = Project(
        schemaVersion=1,
        name="hex-input",
        record_length=16,
        fields=[
            FieldDef(
                name="VHL WCC",
                key="vhl_wcc",
                address=0x00,
                length_bytes=1,
                input_format="hex",
                trim_rule="none",
                required=True,
            )
        ],
    )

    out_1, _ = generate_hex(project, {"vhl_wcc": "01"})
    mem_1 = parse_memory(out_1)
    assert mem_1[0x00] == 0x01

    try:
        generate_hex(project, {"vhl_wcc": "0x0"})
        assert False, "expected ValueError for odd-length hex input"
    except ValueError as exc:
        assert "even number of hex characters" in str(exc)

    try:
        generate_hex(project, {"vhl_wcc": "03"})
        assert False, "expected ValueError for non-fixed VHL WCC value"
    except ValueError as exc:
        assert "must be fixed to 01" in str(exc)


def test_kml_vehicle_bt_address_requires_two_most_significant_bits_set():
    project = Project(
        schemaVersion=1,
        name="bt-address",
        record_length=16,
        fields=[
            FieldDef(
                name="KML Vehicle Bt Address",
                key="kml_vehicle_bt_address",
                address=0x00,
                length_bytes=6,
                input_format="hex",
                trim_rule="none",
                required=True,
            )
        ],
    )

    out_ok, _ = generate_hex(project, {"kml_vehicle_bt_address": "C00102030405"})
    mem_ok = parse_memory(out_ok)
    assert mem_ok[0x00] == 0xC0

    try:
        generate_hex(project, {"kml_vehicle_bt_address": "3F0102030405"})
        assert False, "expected ValueError for invalid BT address top bits"
    except ValueError as exc:
        assert "2 most significant bits" in str(exc)


def test_generate_with_shadow_memory_duplicates_payload():
    project = _project()
    values = {"serial": "AB12", "hw": "A1", "sw": "B2"}
    shadow_offset = 0x02000000

    out, _ = generate_hex(project, values, shadow_offset=shadow_offset)
    mem = parse_memory(out)

    serial_bytes = b"AB12    "
    for i, b in enumerate(serial_bytes):
        assert mem[0x10010 + i] == b
        assert mem[0x10010 + shadow_offset + i] == b


def test_printable_ascii_with_null_padding_and_no_trim_rejects_too_short():
    project = Project(
        schemaVersion=1,
        name="strict-ascii",
        fields=[
            FieldDef(
                name="Part",
                key="part",
                address=0x00,
                length_bytes=4,
                input_format="ascii",
                allowed_charset="printable_ascii",
                padding=0x00,
                trim_rule="none",
                required=True,
            )
        ],
    )

    try:
        generate_hex(project, {"part": "AB"})
        assert False, "expected ValueError for too-short printable ASCII input"
    except ValueError as exc:
        assert "must be exactly 4 bytes; got 2" in str(exc)


def test_hardware_version_info_dec_encodes_decimal_values_per_byte():
    project = Project(
        schemaVersion=1,
        name="hw-version-dec",
        fields=[
            FieldDef(
                name="Hardware Version Info",
                key="hardware_version_info",
                address=0x10,
                length_bytes=3,
                input_format="dec",
                allowed_charset="regex:[0-9]{1,2}( [0-9]{1,2}){2}",
                trim_rule="none",
                required=True,
            )
        ],
    )

    out, _ = generate_hex(project, {"hardware_version_info": "25 46 1"})
    mem = parse_memory(out)
    assert mem[0x10] == 0x19
    assert mem[0x11] == 0x2E
    assert mem[0x12] == 0x01

    back, status = read_fields_from_memory(project, mem)
    assert status["hardware_version_info"] == "ok"
    assert back["hardware_version_info"] == "25 46 1"

    for bad in ("15", "1 2", "100 46 1", "AA 46 1"):
        try:
            generate_hex(project, {"hardware_version_info": bad})
            assert False, "expected ValueError for invalid hardware_version_info decimal-byte input"
        except ValueError as exc:
            assert (
                "does not match regex [0-9]{1,2}( [0-9]{1,2}){2}" in str(exc)
                or "must contain exactly 3 decimal values separated by spaces" in str(exc)
                or "each decimal value must be 1 or 2 digits" in str(exc)
                or "must contain decimal integers only" in str(exc)
            )


def test_hardware_supplier_info_is_fixed_to_013b_or_3b01():
    project = Project(
        schemaVersion=1,
        name="hw-supplier-fixed",
        fields=[
            FieldDef(
                name="Hardware Supplier Info",
                key="hardware_supplier_info",
                address=0x20,
                length_bytes=2,
                input_format="hex",
                trim_rule="none",
                required=True,
                default_value="013B",
            )
        ],
    )

    out_ok, _ = generate_hex(project, {"hardware_supplier_info": "013B"})
    mem_ok = parse_memory(out_ok)
    assert mem_ok[0x20] == 0x01
    assert mem_ok[0x21] == 0x3B

    out_ok2, _ = generate_hex(project, {"hardware_supplier_info": "3B01"})
    mem_ok2 = parse_memory(out_ok2)
    assert mem_ok2[0x20] == 0x3B
    assert mem_ok2[0x21] == 0x01

    try:
        generate_hex(project, {"hardware_supplier_info": "ABCD"})
        assert False, "expected ValueError for non-fixed supplier info"
    except ValueError as exc:
        assert "must be fixed to 013B or 3B01" in str(exc)



