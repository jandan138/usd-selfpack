from __future__ import annotations

import argparse
from pathlib import Path

from .packager import Packager


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="USD 资产同目录自包含打包器")
    parser.add_argument("--input", required=True, help="主 USD 文件路径")
    parser.add_argument("--out", required=True, help="输出目录")
    parser.add_argument("--mode", default="self_contained", choices=["self_contained"], help="打包模式")
    parser.add_argument("--copy-usd-deps", action="store_true", help="复制子 USD 依赖")
    parser.add_argument("--no-copy-usd-deps", dest="copy_usd_deps", action="store_false")
    parser.set_defaults(copy_usd_deps=False)
    parser.add_argument("--flatten", default="none", choices=["none", "layerstack", "full"], help="flatten 策略（打平 layerstack；full 当前等同 layerstack）")
    parser.add_argument("--dry-run", action="store_true", help="仅扫描不复制不改写")
    parser.add_argument("--collision-strategy", default="keep_tree", choices=["keep_tree", "hash_prefix"],
                        help="文件命名冲突策略")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING"], help="日志级别")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    packager = Packager(
        input_path=Path(args.input),
        out_dir=Path(args.out),
        mode=args.mode,
        copy_usd_deps=args.copy_usd_deps,
        dry_run=args.dry_run,
        collision_strategy=args.collision_strategy,
        flatten=args.flatten,
        log_level=args.log_level,
    )
    packager.run()


if __name__ == "__main__":
    main()
