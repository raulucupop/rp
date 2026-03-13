from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import re
from typing import Any, Literal


PaddingByte = int
Encoding = Literal["ascii", "utf-8"]
PadDirection = Literal["left", "right"]
TrimRule = Literal["strip_padding", "stop_at_0x00", "none"]
InputFormat = Literal["ascii", "hex", "dec"]


@dataclass
class FieldDef:
    name: str
    key: str
    address: int
    length_bytes: int
    encoding: Encoding = "ascii"
    allowed_charset: str = "printable_ascii"
    padding: PaddingByte = 0x00
    pad_direction: PadDirection = "right"
    trim_rule: TrimRule = "strip_padding"
    input_format: InputFormat = "ascii"
    required: bool = False
    default_value: str | None = None
    allow_truncate: bool = False

    def validate_value(self, value: str) -> list[str]:
        errors: list[str] = []
        if self.input_format == "hex":
            raw = value.strip()
            if raw.lower().startswith("0x"):
                raw = raw[2:]
            if raw:
                if any(ch not in "0123456789abcdefABCDEF" for ch in raw):
                    errors.append("must be valid hex")
                    return errors
                if len(raw) % 2 == 1:
                    errors.append("must have an even number of hex characters (2 chars = 1 byte)")
                    return errors
                byte_len = len(raw) // 2
                if byte_len < self.length_bytes:
                    errors.append(f"must be exactly {self.length_bytes} bytes; got {byte_len}")
                    return errors
                if byte_len > self.length_bytes and not self.allow_truncate:
                    errors.append(f"max {self.length_bytes} bytes; got {byte_len}")
                if self.key == "vhl_wcc" and raw.upper() != "01":
                    errors.append("must be fixed to 01")
                if self.key == "hardware_supplier_info" and raw.upper() not in ("013B", "3B01"):
                    errors.append("must be fixed to 013B or 3B01")
                if self.key == "kml_vehicle_bt_address":
                    first_byte = int(raw[:2], 16)
                    if (first_byte & 0xC0) != 0xC0:
                        errors.append("the 2 most significant bits of byte 0 must be 1")
            elif self.required:
                errors.append("required")
            return errors
        if self.input_format == "dec":
            raw = value.strip()
            if not raw:
                if self.required:
                    errors.append("required")
                return errors
            if self.key == "hardware_version_info":
                tokens = raw.split()
                if len(tokens) != self.length_bytes:
                    errors.append(f"must contain exactly {self.length_bytes} decimal values separated by spaces")
                    return errors
                for token in tokens:
                    if not token.isdigit():
                        errors.append("must contain decimal integers only")
                        return errors
                    if len(token) > 2:
                        errors.append("each decimal value must be 1 or 2 digits")
                        return errors
                return errors
            if not raw.isdigit():
                errors.append("must be a decimal integer")
                return errors
            if self.allowed_charset.startswith("regex:"):
                pattern = self.allowed_charset.removeprefix("regex:")
                if not re.fullmatch(pattern, raw):
                    errors.append(f"does not match regex {pattern}")
                    return errors
            max_value = (1 << (8 * self.length_bytes)) - 1
            dec_value = int(raw, 10)
            if dec_value > max_value:
                errors.append(f"max value for {self.length_bytes} bytes is {max_value}")
                return errors
            return errors

        if self.allowed_charset == "alphanumeric" and not re.fullmatch(r"[A-Za-z0-9]*", value):
            errors.append("must be alphanumeric")
        elif self.allowed_charset == "printable_ascii" and any(ord(ch) < 0x20 or ord(ch) > 0x7E for ch in value):
            errors.append("must contain printable ASCII only")
        elif self.allowed_charset.startswith("regex:"):
            pattern = self.allowed_charset.removeprefix("regex:")
            if not re.fullmatch(pattern, value):
                errors.append(f"does not match regex {pattern}")

        try:
            encoded = value.encode(self.encoding)
        except UnicodeEncodeError as exc:
            errors.append(f"encoding error: {exc}")
            return errors

        if (
            self.input_format == "ascii"
            and self.allowed_charset == "printable_ascii"
            and self.padding == 0x00
            and self.trim_rule == "none"
            and len(encoded) < self.length_bytes
        ):
            errors.append(f"must be exactly {self.length_bytes} bytes; got {len(encoded)}")

        if len(encoded) > self.length_bytes and not self.allow_truncate:
            errors.append(f"max {self.length_bytes} bytes; got {len(encoded)}")
        return errors


@dataclass
class Project:
    schemaVersion: int
    name: str
    fields: list[FieldDef]
    memory_limit: int | None = None
    record_length: int = 16
    template_hex: str | None = None

    def validate(self) -> list[str]:
        errors: list[str] = []
        seen_keys: set[str] = set()
        ranges: list[tuple[int, int, str]] = []
        for field in self.fields:
            if field.key in seen_keys:
                errors.append(f"duplicate key: {field.key}")
            seen_keys.add(field.key)
            if field.length_bytes <= 0:
                errors.append(f"{field.key}: length_bytes must be > 0")
            if field.address < 0:
                errors.append(f"{field.key}: address must be >=0")
            start = field.address
            end = field.address + field.length_bytes - 1
            if self.memory_limit is not None and end >= self.memory_limit:
                errors.append(f"{field.key}: outside memory_limit {self.memory_limit:#x}")
            ranges.append((start, end, field.key))

        ranges.sort(key=lambda x: x[0])
        for i in range(1, len(ranges)):
            prev_s, prev_e, prev_k = ranges[i - 1]
            cur_s, cur_e, cur_k = ranges[i]
            if cur_s <= prev_e:
                errors.append(f"range collision: {prev_k} [{prev_s:#x}-{prev_e:#x}] and {cur_k} [{cur_s:#x}-{cur_e:#x}]")

        if self.record_length not in (16, 32):
            errors.append("record_length must be 16 or 32")
        return errors

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "Project":
        fields = [FieldDef(**f) for f in payload["fields"]]
        return Project(
            schemaVersion=payload["schemaVersion"],
            name=payload["name"],
            fields=fields,
            memory_limit=payload.get("memory_limit"),
            record_length=payload.get("record_length", 16),
            template_hex=payload.get("template_hex"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schemaVersion,
            "name": self.name,
            "memory_limit": self.memory_limit,
            "record_length": self.record_length,
            "template_hex": self.template_hex,
            "fields": [field.__dict__ for field in self.fields],
        }


@dataclass
class DataConfig:
    values: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "DataConfig":
        return DataConfig(values=payload.get("values", {}), metadata=payload.get("metadata", {}))

    def merge(self, current: dict[str, str]) -> dict[str, str]:
        merged = dict(current)
        for key, value in self.values.items():
            if not merged.get(key):
                merged[key] = value
        return merged


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path: str | Path, payload: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")



