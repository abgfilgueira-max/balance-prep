"""Command line: python -m balance_prep <assignment.xlsx|csv> [--out DIR] [--raw-names]"""
import argparse
import os
import sys
from pathlib import Path

from . import core


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="balance_prep",
                                 description="Prepare the balances file (last payment discounted) from an assignment file.")
    ap.add_argument("base", type=Path, help="assignment file (.xlsx or .csv)")
    ap.add_argument("--out", type=Path, default=Path(os.environ.get("BALANCE_PREP_OUTPUT_DIR") or "."),
                    help="output folder (default: BALANCE_PREP_OUTPUT_DIR or current folder)")
    ap.add_argument("--raw-names", action="store_true", help="keep names as they come, without flipping them")
    args = ap.parse_args(argv)

    if not args.base.exists():
        print(f"File not found: {args.base}", file=sys.stderr)
        return 1
    try:
        base = core.read_base(args.base)
    except Exception as e:
        print(f"Cannot read the file: {e}", file=sys.stderr)
        return 1
    out, summary = core.transform(base, flip_names=not args.raw_names)
    for key, value in summary.items():
        print(f"  {key:<20} {value}")
    if not out:
        print("Nothing left to load.")
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / core.output_name()
    core.build_workbook(out).save(target)
    print(f"Done: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
