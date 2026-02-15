import pytest

from rp_hex_tool.hexfile import IntelHexError, parse_intel_hex, write_intel_hex


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
