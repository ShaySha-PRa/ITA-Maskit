"""脱敏统计计数（GUI 实时显示用）。

处理数据数 / 脱敏数据数 / 文件数。支持跨文件累加。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MaskStats:
    """脱敏统计。

    - processed: 处理数据数（总行/单元格/段数）
    - masked:    脱敏数据数（实际被遮盖/伪名化的单元格数）
    - files:     已处理文件数
    """

    processed: int = 0
    masked: int = 0
    files: int = 0

    def __iadd__(self, other: MaskStats) -> MaskStats:  # noqa: PYI034
        self.processed += other.processed
        self.masked += other.masked
        self.files += other.files
        return self

    def add(self, processed: int = 0, masked: int = 0, files: int = 0) -> None:
        """增量累加。"""
        self.processed += processed
        self.masked += masked
        self.files += files

    @property
    def masked_ratio(self) -> float:
        """脱敏占比（0-1）。processed=0 时返回 0。"""
        if self.processed == 0:
            return 0.0
        return self.masked / self.processed
