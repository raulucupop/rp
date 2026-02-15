from __future__ import annotations

from typing import Literal


FileFormat = Literal["ihex", "srec"]


class IntelHexError(ValueError):
    pass


class SrecError(ValueError):
    pass


def _checksum(byte_values: bytes) -> int:
    return ((~sum(byte_values) + 1) & 0xFF)


def parse_intel_hex(text: str) -> dict[int, int]:
    memory: dict[int, int] = {}
    upper = 0
    seen_eof = False
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if seen_eof:
            raise IntelHexError(f"line {lineno}: content found after EOF record")
        if not line.startswith(":"):
            raise IntelHexError(f"line {lineno}: missing ':'")
        try:
            payload = bytes.fromhex(line[1:])
        except ValueError as exc:
            raise IntelHexError(f"line {lineno}: invalid hex payload") from exc
        if len(payload) < 5:
            raise IntelHexError(f"line {lineno}: too short")
        count = payload[0]
        addr = int.from_bytes(payload[1:3], "big")
        rec_type = payload[3]
        data = payload[4:-1]
        checksum = payload[-1]
        if count != len(data):
            raise IntelHexError(f"line {lineno}: byte count mismatch")
        if _checksum(payload[:-1]) != checksum:
            raise IntelHexError(f"line {lineno}: invalid checksum")

        if rec_type == 0x00:
            abs_addr = upper + addr
            for offset, value in enumerate(data):
                memory[abs_addr + offset] = value
        elif rec_type == 0x01:
            if count != 0:
                raise IntelHexError(f"line {lineno}: EOF record must have zero length")
            seen_eof = True
        elif rec_type == 0x04:
            if count != 2:
                raise IntelHexError(f"line {lineno}: invalid ELA length")
            upper = int.from_bytes(data, "big") << 16
        else:
            continue
    if not seen_eof:
        raise IntelHexError("missing EOF record")
    return memory


def _format_record(record_type: int, address: int, data: bytes) -> str:
    body = bytes([len(data)]) + address.to_bytes(2, "big") + bytes([record_type]) + data
    chk = _checksum(body)
    return ":" + (body + bytes([chk])).hex().upper()


def write_intel_hex(memory: dict[int, int], record_length: int = 16) -> str:
    if not memory:
        return _format_record(0x01, 0, b"") + "\n"

    lines: list[str] = []
    sorted_addrs = sorted(memory)
    current_upper = None
    idx = 0
    while idx < len(sorted_addrs):
        start = sorted_addrs[idx]
        upper = start >> 16
        if upper != current_upper:
            if upper != 0 or current_upper is not None:
                lines.append(_format_record(0x04, 0, upper.to_bytes(2, "big")))
            current_upper = upper

        chunk_addrs = [sorted_addrs[idx]]
        idx += 1
        while idx < len(sorted_addrs):
            nxt = sorted_addrs[idx]
            if nxt >> 16 != upper:
                break
            if nxt != chunk_addrs[-1] + 1:
                break
            if len(chunk_addrs) >= record_length:
                break
            chunk_addrs.append(nxt)
            idx += 1

        low_addr = chunk_addrs[0] & 0xFFFF
        data = bytes(memory[a] for a in chunk_addrs)
        lines.append(_format_record(0x00, low_addr, data))

    lines.append(_format_record(0x01, 0, b""))
    return "\n".join(lines) + "\n"


_SREC_ADDR_LEN = {
    "0": 2,
    "1": 2,
    "2": 3,
    "3": 4,
    "5": 2,
    "6": 3,
    "7": 4,
    "8": 3,
    "9": 2,
}


def _srec_checksum(payload: bytes) -> int:
    return (~sum(payload)) & 0xFF


def _format_srec_record(record_type: str, address: int, data: bytes) -> str:
    if record_type not in _SREC_ADDR_LEN:
        raise SrecError(f"unsupported S-record type: {record_type}")
    addr_len = _SREC_ADDR_LEN[record_type]
    count = addr_len + len(data) + 1
    body = bytes([count]) + address.to_bytes(addr_len, "big") + data
    chk = _srec_checksum(body)
    return f"S{record_type}{(body + bytes([chk])).hex().upper()}"


def write_srec(memory: dict[int, int], record_length: int = 16, header_text: str = "RP-HEX-TOOL") -> str:
    header = header_text.encode("ascii")
    lines: list[str] = [_format_srec_record("0", 0, header)]

    sorted_addrs = sorted(memory)
    idx = 0
    while idx < len(sorted_addrs):
        chunk_addrs = [sorted_addrs[idx]]
        idx += 1
        while idx < len(sorted_addrs):
            nxt = sorted_addrs[idx]
            if nxt != chunk_addrs[-1] + 1:
                break
            if len(chunk_addrs) >= record_length:
                break
            chunk_addrs.append(nxt)
            idx += 1
        start_addr = chunk_addrs[0]
        data = bytes(memory[a] for a in chunk_addrs)
        lines.append(_format_srec_record("3", start_addr, data))

    lines.append(_format_srec_record("7", 0, b""))
    return "\n".join(lines) + "\n"


def parse_srec(text: str) -> dict[int, int]:
    memory: dict[int, int] = {}
    seen_termination = False
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if seen_termination:
            raise SrecError(f"line {lineno}: content found after termination record")
        if not line.startswith("S") or len(line) < 4:
            raise SrecError(f"line {lineno}: invalid S-record prefix")

        rec_type = line[1]
        if rec_type not in _SREC_ADDR_LEN:
            raise SrecError(f"line {lineno}: unsupported S-record type {rec_type!r}")

        try:
            payload = bytes.fromhex(line[2:])
        except ValueError as exc:
            raise SrecError(f"line {lineno}: invalid hex payload") from exc
        if len(payload) < 2:
            raise SrecError(f"line {lineno}: too short")

        count = payload[0]
        if count != len(payload[1:]):
            raise SrecError(f"line {lineno}: byte count mismatch")
        if (sum(payload) & 0xFF) != 0xFF:
            raise SrecError(f"line {lineno}: invalid checksum")

        addr_len = _SREC_ADDR_LEN[rec_type]
        body = payload[1:]
        if len(body) < addr_len + 1:
            raise SrecError(f"line {lineno}: record too short for address/checksum")
        address = int.from_bytes(body[:addr_len], "big")
        data = body[addr_len:-1]

        if rec_type == "3":
            for offset, value in enumerate(data):
                memory[address + offset] = value
        elif rec_type == "7":
            seen_termination = True

    if not seen_termination:
        raise SrecError("missing termination record")
    return memory


def detect_format(text: str) -> FileFormat:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(":"):
            return "ihex"
        if line.startswith("S"):
            return "srec"
        break
    raise ValueError("unknown file format: expected Intel HEX ':' or S-record 'S'")


def parse_auto(text: str) -> dict[int, int]:
    fmt = detect_format(text)
    if fmt == "ihex":
        return parse_intel_hex(text)
    return parse_srec(text)
