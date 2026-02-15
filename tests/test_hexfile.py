import pytest

from rp_hex_tool.hexfile import (
    IntelHexError,
    SrecError,
    detect_format,
    parse_auto,
    parse_intel_hex,
    parse_srec,
    write_intel_hex,
    write_srec,
)


def test_parse_requires_eof_record():
    with pytest.raises(IntelHexError, match="missing EOF record"):
        parse_intel_hex(":0100000001FE\n")


def test_parse_rejects_content_after_eof():
    with pytest.raises(IntelHexError, match="content found after EOF"):
        parse_intel_hex(":00000001FF\n:0100000001FE\n")


def test_writer_omits_initial_ela_for_low_addresses():
    content = write_intel_hex({0x0010: 0x41, 0x0011: 0x42})
    lines = [line for line in content.splitlines() if line]
    assert lines[0].startswith(":02001000")
    assert lines[-1] == ":00000001FF"


def test_write_srec_emits_header_data_and_termination():
    content = write_srec({0x10010: 0x41, 0x10011: 0x42})
    lines = [line for line in content.splitlines() if line]
    assert lines[0].startswith("S0")
    assert lines[1].startswith("S3")
    assert lines[-1].startswith("S7")


def test_parse_srec_requires_termination_record():
    content = write_srec({0x10010: 0x41})
    header_and_data = "\n".join(content.splitlines()[:-1]) + "\n"
    with pytest.raises(SrecError, match="missing termination record"):
        parse_srec(header_and_data)


def test_parse_srec_rejects_bad_checksum():
    content = write_srec({0x10010: 0x41})
    lines = content.splitlines()
    bad = lines[1][:-2] + "00"
    with pytest.raises(SrecError, match="invalid checksum"):
        parse_srec("\n".join([lines[0], bad, lines[2]]) + "\n")


def test_parse_srec_rejects_byte_count_mismatch():
    content = write_srec({0x10010: 0x41})
    lines = content.splitlines()
    data_line = lines[1]
    bad = data_line[:2] + "00" + data_line[4:]
    with pytest.raises(SrecError, match="byte count mismatch"):
        parse_srec("\n".join([lines[0], bad, lines[2]]) + "\n")


def test_srec_round_trip_memory_equivalence():
    memory = {0x0: 0xAA, 0x1: 0xBB, 0x10010: 0x41, 0x10011: 0x42}
    encoded = write_srec(memory)
    parsed = parse_srec(encoded)
    assert parsed == memory


def test_detect_format_and_parse_auto():
    ihex = write_intel_hex({0x10: 0x41})
    srec = write_srec({0x10010: 0x41})
    assert detect_format("\n\n" + ihex) == "ihex"
    assert detect_format(" \n" + srec) == "srec"
    assert parse_auto(ihex)[0x10] == 0x41
    assert parse_auto(srec)[0x10010] == 0x41
