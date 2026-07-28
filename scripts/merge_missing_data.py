#!/usr/bin/env python3
"""把新版本的数据种子补到服务器 data，绝不覆盖已有文件。"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    source = args.source.resolve()
    destination = args.destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            copied += 1
    print(f"补充缺失数据种子文件: {copied}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
