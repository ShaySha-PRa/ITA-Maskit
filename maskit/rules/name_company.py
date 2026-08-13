"""name/company 文本识别（纯本地，零网络、零下载）。

策略：
1. 语义前缀 + 上下文 —— 识别「申请人：张伟」「供应商：亚玛芬体育」
   （复用 ITA 已有思路，仅在明确语义语境下识别，误伤低）
2. 内置词表 —— 审计常见姓名/公司全文匹配（补充已知名单）

数据绝不外发：全部本地正则 + 本地词表，无模型、无网络。
"""
from __future__ import annotations

import re
from pathlib import Path

# 语义前缀（人名/公司）
_PERSON_PREFIXES = ["申请人", "审批人", "经理", "姓名", "负责人", "经办人", "联系人", "客户经理"]
_COMPANY_PREFIXES = ["供应商", "公司", "企业", "客户公司", "合作方", "厂商", "甲方", "乙方"]

# 中文姓名：前缀 + 冒号 + 2-4 个汉字
_CN_NAME_RE = re.compile(
    r"(?:"
    + "|".join(_PERSON_PREFIXES)
    + r")\s*[：:]\s*([一-鿿]{2,4})"
)
# 公司名：前缀 + 冒号 + 中英文/数字/Inc/Ltd 等（2-30 字符）
_CN_COMPANY_RE = re.compile(
    r"(?:"
    + "|".join(_COMPANY_PREFIXES)
    + r")\s*[：:]\s*([一-鿿A-Za-z0-9&.,·\-\s]{2,30})"
)

# 内置审计常见姓名词表（可扩展；演示数据 + 常见场景）
BUILTIN_NAMES = {
    "张伟", "李娜", "王芳", "刘洋", "陈静", "杨帆", "赵磊", "黄敏", "周杰", "吴霞",
    "Alice Chen", "Bob Liu", "Carol Wang", "David Zhang", "Eva Li",
}

# 内置审计常见公司词表
BUILTIN_COMPANIES = {
    "亚玛芬体育", "小菜园集团", "MayAir", "Joy IPO", "Acme Inc", "GlobalTech",
    "阿里巴巴", "腾讯", "华为", "字节跳动", "工商银行", "中国移动",
}


def load_person_list(path: str | Path) -> set[str]:
    """从本地 CSV 加载全量人员清单（动态词表，数据全程本地）。

    支持列：name / 姓名 / employee_name / user_name（大小写不敏感）。
    返回人名集合。CSV 不存在/无姓名列 → 抛 ValueError。
    """
    import csv

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"人员清单文件不存在: {p}")
    with open(p, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"人员清单无表头: {p}")
        # 找姓名列
        name_col = None
        for col in reader.fieldnames:
            if col.strip().lower() in {"name", "姓名", "employee_name", "user_name", "人员"}:
                name_col = col
                break
        if name_col is None:
            raise ValueError(
                f"人员清单缺少姓名列（可用 name/姓名/employee_name/user_name），实际列: {reader.fieldnames}"
            )
        names = {row[name_col].strip() for row in reader if row.get(name_col) and row[name_col].strip()}
    if not names:
        raise ValueError(f"人员清单无有效姓名: {p}")
    return names


# 清单人名命中后紧跟这些 → 视为机构名的一部分，不替换
_ORG_SUFFIXES = (
    "公司", "集团", "有限", "工作室", "事务所", "医院", "银行", "大学", "学院", "厂", "店", "中心",
)
# 人名后接联系方式，仍应替换人名
_CONTACT_SUFFIXES = ("邮箱", "邮件", "电话", "手机", "联系")
# 双名并列后的常见虚词/谓语，不当成「更长姓名」
_PROSE_PARTICLES = (
    "均", "和", "与", "及", "等", "的", "在", "于", "已", "还", "也", "称", "说",
    "表示", "出席", "负责", "来函", "同志", "先生", "女士", "主任", "经理",
)


def _is_longer_name_trap(name: str, rest: str, name_set: set[str]) -> bool:
    """2 字清单名后跟 1 个汉字、拼起来像更长姓名且不在清单 → 视为误伤（张伟达）。"""
    if len(name) != 2 or not rest:
        return False
    if any(rest.startswith(other) for other in name_set):
        return False
    if any(rest.startswith(s) for s in _CONTACT_SUFFIXES):
        return False
    if any(rest.startswith(s) for s in _PROSE_PARTICLES):
        return False
    extra = rest[0]
    if not re.match(r"[一-鿿]", extra):
        return False
    combined = name + extra
    return combined not in name_set and re.fullmatch(r"[一-鿿]{3}", combined) is not None


def iter_person_list_spans(text: str, names: set[str]) -> list[tuple[int, int, str]]:
    """在文本中找应替换的清单人名跨度（最长优先，跳过机构名/更长姓名）。"""
    name_set = {n for n in names if n}
    if not text or not name_set:
        return []
    by_len = sorted(name_set, key=len, reverse=True)
    spans: list[tuple[int, int, str]] = []
    i = 0
    n = len(text)
    while i < n:
        matched: tuple[int, int, str] | None = None
        for name in by_len:
            end = i + len(name)
            if end > n or text[i:end] != name:
                continue
            rest = text[end:]
            if any(rest.startswith(suf) for suf in _ORG_SUFFIXES):
                continue
            if _is_longer_name_trap(name, rest, name_set):
                continue
            matched = (i, end, name)
            break
        if matched:
            spans.append(matched)
            i = matched[1]
        else:
            i += 1
    return spans


def mask_person_list_in_text(text: str, names: set[str], replacer) -> str:
    """按边界规则替换清单人名；replacer(name) → 遮盖后的字符串。"""
    spans = iter_person_list_spans(text, names)
    if not spans:
        return text
    out = text
    for start, end, name in reversed(spans):
        out = out[:start] + replacer(name) + out[end:]
    return out


def find_person_names(text: str, person_list: set[str] | None = None) -> list[str]:
    """从语义前缀 + 词表（内置 + 可选外部清单）识别文本中的中文名。

    内置词表与外部清单共用边界规则：不切「张伟达」、不切「东方不败工作室」。
    """
    found = []
    for m in _CN_NAME_RE.finditer(text):
        name = m.group(1).strip()
        if name and name not in found:
            found.append(name)
    names = set(BUILTIN_NAMES) | (person_list or set())
    for _, _, name in iter_person_list_spans(text, names):
        if name not in found:
            found.append(name)
    return found


def find_company_names(text: str) -> list[str]:
    """从语义前缀 + 词表识别文本中的公司名。"""
    found = []
    # 语义前缀
    for m in _CN_COMPANY_RE.finditer(text):
        name = m.group(1).strip()
        if name and name not in found:
            found.append(name)
    # 词表
    for name in BUILTIN_COMPANIES:
        if name not in found and re.search(re.escape(name), text):
            found.append(name)
    return found
