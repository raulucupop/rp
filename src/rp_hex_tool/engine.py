from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal
import csv
import json
import logging
from logging.handlers import RotatingFileHandler

from .hexfile import parse_intel_hex, write_intel_hex
from .models import DataConfig, FieldDef, Project, load_json


def setup_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger("rp_hex_tool")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


def encode_field(field: FieldDef, value: str) -> tuple[bytes, list[str]]:
    warnings: list[str] = []
    encoded = value.encode(field.encoding)
    if len(encoded) > field.length_bytes:
        if field.allow_truncate:
            warnings.append(f"{field.key}: truncated from {len(encoded)} to {field.length_bytes} bytes")
            encoded = encoded[: field.length_bytes]
        else:
            raise ValueError(f"{field.key}: too long ({len(encoded)}>{field.length_bytes})")

    pad_len = field.length_bytes - len(encoded)
    if pad_len:
        pad = bytes([field.padding]) * pad_len
        encoded = (pad + encoded) if field.pad_direction == "left" else (encoded + pad)
    return encoded, warnings


def decode_field(field: FieldDef, raw: bytes) -> str:
    if field.trim_rule == "stop_at_0x00":
        raw = raw.split(b"\x00", 1)[0]
    elif field.trim_rule == "strip_padding":
        raw = raw.rstrip(bytes([field.padding])) if field.pad_direction == "right" else raw.lstrip(bytes([field.padding]))
    return raw.decode(field.encoding, errors="replace")


def fields_to_memory(project: Project, values: dict[str, str]) -> tuple[dict[int, int], list[str]]:
    errors = project.validate()
    if errors:
        raise ValueError("project invalid: " + "; ".join(errors))

    memory: dict[int, int] = {}
    warnings: list[str] = []
    for field in project.fields:
        value = values.get(field.key, field.default_value or "")
        if field.required and not value:
            raise ValueError(f"{field.key}: required")
        value_errors = field.validate_value(value)
        if value_errors:
            raise ValueError(f"{field.key}: " + ", ".join(value_errors))

        encoded, field_warnings = encode_field(field, value)
        warnings.extend(field_warnings)
        for idx, b in enumerate(encoded):
            memory[field.address + idx] = b
    return memory, warnings


def read_fields_from_memory(project: Project, memory: dict[int, int]) -> tuple[dict[str, str], dict[str, str]]:
    values: dict[str, str] = {}
    status: dict[str, str] = {}
    for field in project.fields:
        buf = []
        missing = False
        for idx in range(field.length_bytes):
            addr = field.address + idx
            if addr not in memory:
                missing = True
                break
            buf.append(memory[addr])
        if missing:
            status[field.key] = "not present in HEX"
            continue
        values[field.key] = decode_field(field, bytes(buf))
        status[field.key] = "ok"
    return values, status


def generate_hex(project: Project, values: dict[str, str]) -> tuple[str, list[str]]:
    memory, warnings = fields_to_memory(project, values)
    return write_intel_hex(memory, project.record_length), warnings


def patch_hex(project: Project, template_hex: str, values: dict[str, str]) -> tuple[str, list[str]]:
    base = parse_intel_hex(template_hex)
    patch_mem, warnings = fields_to_memory(project, values)
    base.update(patch_mem)
    return write_intel_hex(base, project.record_length), warnings


def verify(project: Project, values: dict[str, str], output_hex: str) -> dict[str, Literal["PASS", "FAIL"]]:
    memory = parse_intel_hex(output_hex)
    expected, _ = fields_to_memory(project, values)
    result: dict[str, Literal["PASS", "FAIL"]] = {}
    for field in project.fields:
        expected_bytes = [expected[field.address + i] for i in range(field.length_bytes)]
        actual_bytes = [memory.get(field.address + i) for i in range(field.length_bytes)]
        result[field.key] = "PASS" if expected_bytes == actual_bytes else "FAIL"
    return result


def diff_ranges(project: Project, left_hex: str, right_hex: str) -> dict[str, list[tuple[int, int, int]]]:
    left = parse_intel_hex(left_hex)
    right = parse_intel_hex(right_hex)
    diff: dict[str, list[tuple[int, int, int]]] = {}
    for field in project.fields:
        entries = []
        for i in range(field.length_bytes):
            addr = field.address + i
            l = left.get(addr, -1)
            r = right.get(addr, -1)
            if l != r:
                entries.append((addr, l, r))
        diff[field.key] = entries
    return diff


def load_project(path: str) -> Project:
    project = Project.from_dict(load_json(path))
    errors = project.validate()
    if errors:
        raise ValueError("invalid project: " + "; ".join(errors))
    return project


def load_config(path: str) -> DataConfig:
    return DataConfig.from_dict(load_json(path))


def batch_from_csv(path: str) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def batch_from_json(path: str) -> list[dict[str, str]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload["items"]
    return payload


def file_hash(path: str | Path) -> str:
    data = Path(path).read_bytes()
    return sha256(data).hexdigest()
