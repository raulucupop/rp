import pytest

from rp_hex_tool.cli import build_parser


def test_generate_accepts_srec_format():
    parser = build_parser()
    args = parser.parse_args(["generate", "--project", "p.json", "--output", "o.srec", "--format", "srec"])
    assert args.command == "generate"
    assert args.format == "srec"


def test_patch_default_format_is_ihex():
    parser = build_parser()
    args = parser.parse_args(["patch", "--project", "p.json", "--output", "o.hex"])
    assert args.command == "patch"
    assert args.format == "ihex"


def test_batch_rejects_invalid_format():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["batch", "--project", "p.json", "--input", "items.json", "--output-dir", "out", "--format", "bad"]
        )
