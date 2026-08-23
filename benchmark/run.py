"""CLI: python benchmark/run.py"""

from __future__ import annotations

import sys

from maskit.detection.eval_gold import format_report, run_gold


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else None
    from pathlib import Path

    from maskit.detection.eval_gold import GOLD_PATH

    gold = Path(path) if path else GOLD_PATH
    print(format_report(run_gold(gold)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
