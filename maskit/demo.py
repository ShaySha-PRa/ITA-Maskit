"""demo 数据生成器。

Polars 原生生成（向量化，毫秒级），固定 seed 保证可复现。
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

# 演示用：确定性人名/公司/域名
_NAMES_CN = ["张伟", "李娜", "王芳", "刘洋", "陈静", "杨帆", "赵磊", "黄敏", "周杰", "吴霞"]
_NAMES_EN = ["Alice Chen", "Bob Liu", "Carol Wang", "David Zhang", "Eva Li"]
_COMPANIES = ["亚玛芬体育", "小菜园集团", "MayAir", "Joy IPO", "Acme Inc", "GlobalTech"]
_DOMAINS = ["corp.example", "company.cn", "gmail.com", "outlook.com", "internal.local"]
_PREFIXES = ["EID", "EMP", "ACCT"]


def generate_demo_data(rows: int = 100_000, seed: int = 42) -> pl.DataFrame:
    """生成确定性演示数据（含各类敏感字段）。"""
    rng = pl.DataFrame({"seed": range(rows)}).select(
        pl.col("seed").shuffle(seed=seed)
    )
    # 用确定性伪随机索引（基于 seed 列哈希），避免真随机
    idx = rng["seed"].to_list()

    def pick(pool: list[str]) -> list[str]:
        return [pool[i % len(pool)] for i in idx]

    def pseudo_random(lo: int, hi: int) -> list[int]:
        return [lo + (i % (hi - lo)) for i in idx]

    names = pick(_NAMES_CN + _NAMES_EN)
    companies = pick(_COMPANIES)
    domains = pick(_DOMAINS)
    prefixes = pick(_PREFIXES)

    employees = [
        f"{prefixes[i]}-{1000 + (i % 9000)}" for i in range(rows)
    ]
    emails = [
        f"user{i}@{domains[i]}" for i in range(rows)
    ]
    phones = [
        f"138{str((10000000 + i) % 100000000).zfill(8)}" for i in range(rows)
    ]
    ips = [
        f"10.{i % 256}.{(i // 256) % 256}.{(i // 65536) % 256}" for i in range(rows)
    ]
    accounts = [f"u{i}_audit" for i in range(rows)]
    versions = [
        f"v{1 + (i % 5)}.{i % 10}.{(i * 7) % 20}" for i in range(rows)
    ]

    return pl.DataFrame(
        {
            "name": names,
            "email": emails,
            "ip": ips,
            "phone": phones,
            "employee_id": employees,
            "account": accounts,
            "company": companies,
            "app_version": versions,
        }
    )


def write_demo(input_path: str | Path, rows: int = 100_000, seed: int = 42) -> Path:
    """生成演示数据并写入 CSV，返回路径。"""
    path = Path(input_path)
    df = generate_demo_data(rows=rows, seed=seed)
    df.write_csv(path)
    return path
