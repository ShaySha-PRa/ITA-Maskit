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

_COMMON_SURNAMES = set(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹"
    "喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉岑薛雷贺倪"
    "汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹"
    "狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童"
    "颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯昝管卢莫经房裘缪干解应宗丁"
    "宣贲邓郁单杭洪包诸左石崔吉钮龚党刘姬欧司"
)
_COMMON_COMPOUND_SURNAMES = (
    "欧阳", "司马", "上官", "诸葛", "夏侯", "东方", "皇甫", "尉迟",
    "公孙", "慕容", "司徒", "司空", "西门", "南宫", "端木", "轩辕",
    "令狐", "独孤", "宇文", "长孙", "呼延", "闻人",
)
COMMON_NON_NAMES = {
    "一队", "万元", "主体", "俱乐部", "债务类别", "入职时间", "关联关系", "其他",
    "其他费用", "分析师", "原币单位", "变更类型", "合计", "后期", "品牌主管",
    "品牌策划", "商务总监", "商务经理", "备注", "奖金分成", "姓名", "实习生",
    "平面设计", "应付账款", "总人数", "序号", "岗位", "应发", "实发", "扣款",
    "社保", "公积金", "个税", "实付", "应收", "应付", "账款", "工资", "薪酬",
    "金额", "费用", "类型", "说明", "名称", "单位", "时期", "期间", "摘要",
    "项目", "科目", "凭证", "日期", "时间", "人员", "部门", "职务", "级别",
    "总计", "小计", "大写", "人民币", "银行", "账号", "账户", "审核",
    "制表", "复核", "批准", "录入", "提交", "状态", "进度", "类别", "来源",
}


def is_person_name(value: str) -> bool:
    """排除词表外 + 单/复姓开头 + 2-4字纯中文。"""
    v = value.strip()
    if not re.fullmatch(r"[一-鿿]{2,4}", v):
        return False
    if v in COMMON_NON_NAMES:
        return False
    if len(v) >= 2 and v[:2] in _COMMON_COMPOUND_SURNAMES:
        return True
    return v[0] in _COMMON_SURNAMES


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


_SENTENCE_CONT = (
    "不", "没", "也", "还", "就", "都", "很", "会", "能", "要", "把", "被",
    "从", "向", "对", "和", "与", "及", "等", "的", "在", "于", "已",
)
_ACTION_SUFFIXES = (
    "负责", "复核", "审批", "经办", "提交", "确认", "签字", "录入", "申请",
    "离职", "入职", "完毕", "出示", "作证", "到场",
)
_ROLE_PREFIXES = (
    "经办人", "经办", "申请人", "审批人", "复核人", "员工", "用户",
    "姓名", "操作人", "创建人", "联系人", "负责人",
)


def _is_cjk(ch: str) -> bool:
    return bool(re.match(r"[一-鿿]", ch))


def _is_longer_name_trap(name: str, rest: str, name_set: set[str]) -> bool:
    """清单短名后面仍是中文、且不是动作/虚词边界 → 拒绝截断更长姓名。

    适用于 2–4 字及复姓，不只二字。动作后缀（复核/负责…）视为合法边界。
    """
    if not rest or not name:
        return False
    if any(rest.startswith(other) for other in name_set):
        return False
    if any(rest.startswith(s) for s in _CONTACT_SUFFIXES):
        return False
    if any(rest.startswith(s) for s in _PROSE_PARTICLES):
        return False
    if any(rest.startswith(s) for s in _ACTION_SUFFIXES):
        return False
    if any(rest.startswith(s) for s in _SENTENCE_CONT):
        return False
    if any(rest.startswith(s) for s in _ORG_SUFFIXES):
        return False
    extra = rest[0]
    if not _is_cjk(extra):
        return False
    i = 0
    while i < len(rest) and _is_cjk(rest[i]):
        tail = rest[i:]
        if any(tail.startswith(s) for s in _ACTION_SUFFIXES + _PROSE_PARTICLES + _CONTACT_SUFFIXES + _ORG_SUFFIXES):
            break
        i += 1
        if i >= 4:
            break
    if i == 0:
        return False
    combined = name + rest[:i]
    if combined in name_set:
        return False
    if not re.fullmatch(r"[一-鿿]{2,8}", combined):
        return False
    return True


def iter_person_list_spans_ref(text: str, names: set[str]) -> list[tuple[int, int, str]]:
    """Python reference: 最长优先，跳过机构名/更长姓名。"""
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


def iter_person_list_spans(text: str, names: set[str]) -> list[tuple[int, int, str]]:
    """清单人名跨度。Native 可用时走 Trie；否则 Python reference。"""
    from maskit.native import get_backend

    return get_backend().match_person_list(text, names)


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
