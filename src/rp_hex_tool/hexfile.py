from __future__ import annotations

class IntelHexError(ValueError):
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
