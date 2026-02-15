from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import getpass
import socket

from .engine import (
    batch_from_csv,
    batch_from_json,
    diff_ranges,
    file_hash,
    generate_hex,
    load_config,
    load_project,
    patch_hex,
    read_fields_from_memory,
    setup_logger,
    verify,
)
from .hexfile import parse_intel_hex


def _load_values(config_path: str | None) -> dict[str, str]:
    if not config_path:
        return {}
    return load_config(config_path).values


def cmd_generate(args: argparse.Namespace) -> int:
    project = load_project(args.project)
    values = _load_values(args.config)
    content, warnings = generate_hex(project, values)
    Path(args.output).write_text(content, encoding="utf-8")
    for w in warnings:
        print(f"WARN: {w}")
    print(f"Generated {args.output}")
    return 0


def cmd_patch(args: argparse.Namespace) -> int:
    project = load_project(args.project)
    values = _load_values(args.config)
    template = Path(args.template or project.template_hex).read_text(encoding="utf-8")
    content, warnings = patch_hex(project, template, values)
    Path(args.output).write_text(content, encoding="utf-8")
    for w in warnings:
        print(f"WARN: {w}")
    print(f"Patched {args.output}")
    return 0


def cmd_readback(args: argparse.Namespace) -> int:
    project = load_project(args.project)
    memory = parse_intel_hex(Path(args.hex).read_text(encoding="utf-8"))
    values, status = read_fields_from_memory(project, memory)
    for field in project.fields:
        print(f"{field.key}: {status[field.key]} | {values.get(field.key, '')}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    project = load_project(args.project)
    values = _load_values(args.config)
    result = verify(project, values, Path(args.hex).read_text(encoding="utf-8"))
    failed = False
    for key, state in result.items():
        print(f"{key}: {state}")
        failed = failed or state == "FAIL"
    return 1 if failed else 0


def cmd_diff(args: argparse.Namespace) -> int:
    project = load_project(args.project)
    left = Path(args.left).read_text(encoding="utf-8")
    right = Path(args.right).read_text(encoding="utf-8")
    diff = diff_ranges(project, left, right)
    for key, entries in diff.items():
        print(f"[{key}] diffs={len(entries)}")
        for addr, l, r in entries:
            print(f"  {addr:#08x}: {l:#04x} -> {r:#04x}")
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    project = load_project(args.project)
    template = Path(args.template or project.template_hex).read_text(encoding="utf-8") if args.mode == "patch" else None
    items = batch_from_csv(args.input) if args.input.endswith(".csv") else batch_from_json(args.input)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logger(Path(args.log))
    success = 0
    for idx, item in enumerate(items, start=1):
        ts = datetime.now().strftime("%Y%m%d")
        file_name = args.naming.format(date=ts, idx=idx, **item)
        output = out_dir / file_name
        try:
            content, warnings = patch_hex(project, template, item) if args.mode == "patch" else generate_hex(project, item)
            output.write_text(content, encoding="utf-8")
            success += 1
            logger.info("batch_success idx=%s output=%s warnings=%s", idx, output, warnings)
        except Exception as exc:
            logger.error("batch_fail idx=%s err=%s", idx, exc)

    print(f"Batch done: {success}/{len(items)} successful")
    return 0 if success == len(items) else 2


def cmd_audit(args: argparse.Namespace) -> int:
    logger = setup_logger(Path(args.log))
    logger.info(
        "audit user=%s host=%s project=%s config=%s input_hash=%s output_hash=%s",
        getpass.getuser(),
        socket.gethostname(),
        args.project,
        args.config,
        file_hash(args.input),
        file_hash(args.output),
    )
    print("Audit logged")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rp-hex")
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate")
    g.add_argument("--project", required=True)
    g.add_argument("--config")
    g.add_argument("--output", required=True)
    g.set_defaults(func=cmd_generate)

    p = sub.add_parser("patch")
    p.add_argument("--project", required=True)
    p.add_argument("--config")
    p.add_argument("--template")
    p.add_argument("--output", required=True)
    p.set_defaults(func=cmd_patch)

    r = sub.add_parser("readback")
    r.add_argument("--project", required=True)
    r.add_argument("--hex", required=True)
    r.set_defaults(func=cmd_readback)

    v = sub.add_parser("verify")
    v.add_argument("--project", required=True)
    v.add_argument("--config")
    v.add_argument("--hex", required=True)
    v.set_defaults(func=cmd_verify)

    d = sub.add_parser("diff")
    d.add_argument("--project", required=True)
    d.add_argument("--left", required=True)
    d.add_argument("--right", required=True)
    d.set_defaults(func=cmd_diff)

    b = sub.add_parser("batch")
    b.add_argument("--project", required=True)
    b.add_argument("--input", required=True)
    b.add_argument("--output-dir", required=True)
    b.add_argument("--mode", choices=["generate", "patch"], default="generate")
    b.add_argument("--template")
    b.add_argument("--naming", default="{idx}_{date}.hex")
    b.add_argument("--log", default="rp_hex.log")
    b.set_defaults(func=cmd_batch)

    a = sub.add_parser("audit")
    a.add_argument("--project", required=True)
    a.add_argument("--config")
    a.add_argument("--input", required=True)
    a.add_argument("--output", required=True)
    a.add_argument("--log", default="rp_hex.log")
    a.set_defaults(func=cmd_audit)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
