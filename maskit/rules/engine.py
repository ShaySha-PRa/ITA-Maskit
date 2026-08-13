"""规则执行引擎。

mask 策略：Polars 表达式（向量化，快）。
pseudo 策略：map_elements + Python hmac（Polars 无 HMAC 表达式）。

关键设计：确定性伪名化对「规范化后」的值做 HMAC，保证跨表/跨批次
同一敏感值映射到同一伪名（保留关联性）。pepper 用 domain separation
派生子 key（伪名化与审计指纹分离，防 key 交叉泄露）。
"""
from __future__ import annotations

import hashlib
import hmac
import re

import polars as pl

from maskit.normalize import normalize_default
from maskit.rules.defs import NORMALIZERS, RuleDef, RuleSet, RuleSpec


def _strip_anchors(pattern: str) -> str:
    """去掉 ^ 和 $ 锚点，使规则正则可在值内匹配。"""
    p = pattern
    p = p.removeprefix("^")
    p = p.removesuffix("$")
    return p


def _domain_key(pepper: str, domain: str) -> bytes:
    """Domain separation：从同一 pepper 派生不同用途的 HMAC key。"""
    return hmac.new(
        pepper.encode("utf-8"), domain.encode("utf-8"), hashlib.sha256
    ).digest()


def pseudo_key(pepper: str) -> bytes:
    """伪名化专用 HMAC key。"""
    return _domain_key(pepper, "pseudonym")


def audit_key(pepper: str) -> bytes:
    """审计指纹专用 HMAC key（domain separation，与伪名化隔离）。"""
    return _domain_key(pepper, "audit")


def hmac_digest(value: str, key: bytes, length: int = 8) -> str:
    """确定性 HMAC 哈希，输出 hex 前缀。"""
    digest = hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:length].upper()


def pseudo_hash(value: str, pepper: str, length: int = 8) -> str:
    """确定性伪名哈希（对规范化后的值）。"""
    return hmac_digest(value, pseudo_key(pepper), length)


def render_template(template: str, value: str, pepper: str | None) -> str:
    """渲染遮盖/伪名模板。

    支持的占位符：
      {hash:8}   确定性 HMAC 哈希（需 pepper）
      {first}    首字符
      {last}     尾字符
      {tail:4}   尾部 N 字符
      {prefix}   首个分隔段（如 EID、138）
      {suffix}   末尾分隔段
      {digits}   确定性数字串（HMAC 派生，保留位数）
      {major}    版本主号（v1.2.3 → 1）
      {domain}   邮箱域名
    """
    # {hash:8} — 确定性伪名
    if "{hash:8}" in template:
        if pepper is None:
            raise ValueError("pseudo 策略需要 --pepper（或 MASKIT_PEPPER）才能生成确定性伪名")
        template = template.replace("{hash:8}", pseudo_hash(value, pepper, 8))

    if "{first}" in template:
        template = template.replace("{first}", value[:1] if value else "")

    if "{second}" in template:
        template = template.replace("{second}", value[1:2] if len(value) > 1 else "")

    if "{last}" in template:
        template = template.replace("{last}", value[-1:] if value else "")

    if "{tail:4}" in template:
        template = template.replace("{tail:4}", value[-4:] if len(value) >= 4 else value)

    # 通用 {head:N} / {tail:N}（任意 N）
    import re as _re

    def _head_repl(m: re.Match) -> str:
        n = int(m.group(1))
        return value[:n] if len(value) >= n else value

    def _tail_repl(m: re.Match) -> str:
        n = int(m.group(1))
        return value[-n:] if len(value) >= n else value

    template = _re.sub(r"\{head:(\d+)\}", _head_repl, template)
    template = _re.sub(r"\{tail:(\d+)\}", _tail_repl, template)

    if "{head:3}" in template:  # 兼容旧模板（通用正则已处理，此处兜底）
        template = template.replace("{head:3}", value[:3] if len(value) >= 3 else value)

    # {prefix}/{suffix}：按非字母数字分隔段切分
    if "{prefix}" in template or "{suffix}" in template:
        parts = re.split(r"[\s.\-]+", value)
        prefix = parts[0] if parts else ""
        suffix = parts[-1] if len(parts) > 1 else ""
        template = template.replace("{prefix}", prefix).replace("{suffix}", suffix)

    # {digits}：确定性数字串（HMAC 派生，保留位数）
    if "{digits}" in template:
        if pepper is None:
            raise ValueError("pseudo 策略需要 --pepper")
        n = len(re.sub(r"\D", "", value))
        n = n or 11
        h = pseudo_hash(value, pepper, 16)
        # 由哈希派生 n 位数字（确定性）
        digits = "".join(str(int(c, 16) % 10) for c in h)[:n].ljust(n, "0")
        template = template.replace("{digits}", digits)

    # {major}：版本主号
    if "{major}" in template:
        m = re.match(r"[vV]?(\d+)", value)
        template = template.replace("{major}", m.group(1) if m else "")

    # {domain}：邮箱域名
    if "{domain}" in template:
        domain = value.split("@")[-1] if "@" in value else ""
        template = template.replace("{domain}", domain)

    return template


def _mask_single(rule: RuleDef, value: str) -> str:
    """单个值的 mask 处理（遮盖模板）。"""
    if not value:
        return value
    return render_template(rule.mask, value, pepper=None)


def _pseudo_single(rule: RuleDef, value: str, pepper: str) -> str:
    """单个值的 pseudo 处理（确定性伪名化）。"""
    if not value:
        return value
    norm_fn = NORMALIZERS.get(rule.normalize, normalize_default)
    norm_value = norm_fn(value)
    return render_template(rule.pseudo, norm_value, pepper)


def _apply_single(rule: RuleDef, value: str, strategy: str, pepper: str | None) -> str:
    """按策略派发单值处理，返回脱敏后的字符串（兼容单值场景）。"""
    return _apply_single_count(rule, value, strategy, pepper)["masked_value"]


def preview_rule(
    rule: RuleDef,
    sample: str,
    strategy: str = "mask",
    pepper: str | None = None,
) -> dict:
    """预览单条规则对样例值的脱敏效果（GUI 规则编辑测试用）。

    返回 {original, masked, changed, strategy}。复用 _apply_single。
    """
    masked = _apply_single(rule, sample, strategy, pepper)
    return {
        "original": sample,
        "masked": masked,
        "changed": 1 if masked != sample else 0,
        "strategy": strategy,
    }


def _apply_single_count(
    rule: RuleDef, value: str, strategy: str, pepper: str | None
) -> dict:
    """按策略派发单值处理，返回 dict（Polars struct 用）: {masked_value, changed}。

    GUI 需要「脱敏了多少数据」计数，故在单值层返回是否改变。
    """
    if strategy == "mask":
        out = _mask_single(rule, value)
    elif strategy == "pseudo":
        if pepper is None:
            raise ValueError(
                "pseudo 策略激活但未提供 --pepper（或 MASKIT_PEPPER），拒绝静默执行"
            )
        out = _pseudo_single(rule, value, pepper)
    else:
        raise ValueError(f"非法策略: {strategy}")
    return {"masked_value": out, "changed": 1 if out != value else 0}


# 值级检测白名单：只对这些「强特征」规则做整值检测。
# 弱特征规则（app_version/account/employee_id/phone）误伤率高
# （会匹配 2.5/2024.1.1 等日期小数），排除。
_VALUE_SCAN_RULES = {"email", "ip", "id_card", "bank_card"}

# 格内 IP：禁止紧贴 v/字母数字/点（避免 v10.20.30.40），八位 0-255
_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)"
CELL_IP_RE = re.compile(
    rf"(?<![vV0-9A-Za-z.]){_OCTET}(?:\.{_OCTET}){{3}}(?![0-9A-Za-z])(?!\.\d)"
)
_DATE_LIKE_VERSION_RE = re.compile(r"^(19|20)\d{2}[./-]\d{1,2}([./-]\d{1,2})?$")
_DEPT_LIKE_RE = re.compile(r"^[\u4e00-\u9fff]{1,8}(部|处|科|组|室)$")
_SPACED_ID_RE = re.compile(r"\d{6}\s+\d{8}\s+\d{3}[\dXx]")
_DASHED_BANK_RE = re.compile(r"\d{4}[\s\-]\d{4}[\s\-]\d{4}[\s\-]\d{4}(?:[\s\-]\d{1,3})?")
_EMAIL_BODY_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_CATCHALL_BODIES = {".+", ".*", ".+?", ".*?"}

# 中文人名检测（排除词表 + 姓氏开头）：
# 值级检测对「排除词表外 + 姓氏开头 + 2-4字纯中文」判定为人名，按 name 规则脱敏。
# 覆盖横排选手/教练收入表里的人名（无列名可依）。
_COMMON_SURNAMES = set(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹"
    "喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉岑薛雷贺倪"
    "汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹"
    "狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童"
    "颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯昝管卢莫经房裘缪干解应宗丁"
    "宣贲邓郁单杭洪包诸左石崔吉钮龚党刘姬欧司"
)

# 常见复姓：优先匹配（2 字姓），覆盖欧阳/司马/上官/诸葛/夏侯/东方/皇甫/尉迟/公孙/慕容等
_COMMON_COMPOUND_SURNAMES = (
    "欧阳", "司马", "上官", "诸葛", "夏侯", "东方", "皇甫", "尉迟",
    "公孙", "慕容", "司徒", "司空", "西门", "南宫", "端木", "轩辕",
    "令狐", "独孤", "宇文", "长孙", "呼延", "闻人",
)

# 排除词表：常见 2-4 字普通中文词（不是人名），避免误伤
_COMMON_NON_NAMES = {
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


def _to_halfwidth(s: str) -> str:
    """全角 ASCII（FF01-FF5E）按位映射为半角，下标 1:1。"""
    chars = []
    for c in s:
        o = ord(c)
        if 0xFF01 <= o <= 0xFF5E:
            chars.append(chr(o - 0xFEE0))
        elif c == "\u3000":
            chars.append(" ")
        else:
            chars.append(c)
    return "".join(chars)


def _is_catchall_rule(rule: RuleDef) -> bool:
    body = rule.match.removeprefix("^").removesuffix("$")
    return body in _CATCHALL_BODIES


def _should_skip_catchall_value(value: str) -> bool:
    """部门/科室或排除词 → 不套 name/company 的 .+ 模板。"""
    s = value.strip()
    if s in _COMMON_NON_NAMES:
        return True
    return _DEPT_LIKE_RE.fullmatch(s) is not None


def _canonical_for_rule(rule: RuleDef, raw: str) -> str:
    """列映射/整格检测用的规范化值（空格证号、横线卡号、全角邮箱）。"""
    if rule.name == "id_card":
        return re.sub(r"\s+", "", raw)
    if rule.name == "bank_card":
        return re.sub(r"[\s\-]", "", raw)
    if rule.name == "email":
        return _to_halfwidth(raw)
    return raw.strip()


def iter_pii_variant_hits(
    text: str,
    rules_by_name: dict[str, RuleDef],
    strategy: str,
    pepper: str | None,
) -> list[tuple[str, str]]:
    """格内写法变体：空格身份证、横线卡号、全角邮箱 → [(原文, 替换), ...]。"""
    hits: list[tuple[str, str]] = []
    id_rule = rules_by_name.get("id_card")
    bank_rule = rules_by_name.get("bank_card")
    email_rule = rules_by_name.get("email")
    if id_rule:
        for m in _SPACED_ID_RE.finditer(text):
            compact = re.sub(r"\s+", "", m.group(0))
            hits.append((m.group(0), _apply_single(id_rule, compact, strategy, pepper)))
    if bank_rule:
        for m in _DASHED_BANK_RE.finditer(text):
            digits = re.sub(r"[\s\-]", "", m.group(0))
            if 16 <= len(digits) <= 19:
                hits.append((m.group(0), _apply_single(bank_rule, digits, strategy, pepper)))
    if email_rule:
        half = _to_halfwidth(text)
        if half != text:
            for m in _EMAIL_BODY_RE.finditer(half):
                orig = text[m.start() : m.end()]
                if orig == m.group(0):
                    continue
                hits.append((orig, _apply_single(email_rule, m.group(0), strategy, pepper)))
    hits.sort(key=lambda pair: len(pair[0]), reverse=True)
    return hits


def apply_pii_variants(
    text: str,
    rules_by_name: dict[str, RuleDef],
    strategy: str,
    pepper: str | None,
) -> str:
    out = text
    for original, replacement in iter_pii_variant_hits(text, rules_by_name, strategy, pepper):
        out = out.replace(original, replacement)
    return out


def _is_person_name(value: str) -> bool:
    """判断值是否为中文人名（排除词表外 + 单/复姓开头 + 2-4字纯中文）。"""
    v = value.strip()
    if not re.fullmatch(r"[一-鿿]{2,4}", v):
        return False
    if v in _COMMON_NON_NAMES:
        return False
    # 复姓优先（欧阳修 → 欧阳在复姓表）
    if len(v) >= 2 and v[:2] in _COMMON_COMPOUND_SURNAMES:
        return True
    return v[0] in _COMMON_SURNAMES


def _build_value_scan_regexes(ruleset: RuleSet) -> list[tuple[RuleDef, re.Pattern]]:
    """构建值级检测正则（仅强特征白名单规则）。

    用**原始带锚点**的正则做整值匹配——值必须整体匹配规则，
    避免 app_version 等把「2024.1.1」当版本号、phone 把日期当手机号。
    """
    compiled = []
    for d in ruleset.defs.values():
        if d.name not in _VALUE_SCAN_RULES:
            continue
        if d.text_scanable and not d.default_disabled:
            try:
                compiled.append((d, re.compile(d.match)))
            except re.error:
                continue
    return compiled


def _scan_match_rule(
    value: str,
    regexes: list[tuple[RuleDef, re.Pattern]],
    name_rule: RuleDef | None = None,
    person_list: set[str] | None = None,
) -> RuleDef | None:
    """返回命中值级检测的规则（无命中返回 None）。

    与 _value_scan_single 的命中判定完全一致，供预验证标注命中规则名。
    - 强特征规则（email/ip/id_card）整值匹配，最长正则优先
    - 人员清单：值在清单里 → name（精确匹配，零误伤）
    - 姓氏启发式：仅当**无** person_list 时启用（有清单则关闭，防误伤）
    - 公式保护：=SUM(...) 开头不检测
    """
    v = value if value is not None else ""
    if not v.strip() or v.strip().startswith("="):
        return None
    best = None
    best_len = -1
    s = v.strip()
    for d, regex in regexes:
        cand = _canonical_for_rule(d, s)
        if regex.fullmatch(cand) and len(d.match) > best_len:
            best = d
            best_len = len(d.match)
    if best is None and name_rule is not None and person_list and s in person_list:
        best = name_rule
    # 有人员清单时关闭姓氏启发式（清单是主路径；清单外名字不误伤）
    if best is None and name_rule is not None and not person_list and _is_person_name(v):
        best = name_rule
    return best


def _value_scan_single(
    value: str,
    regexes: list[tuple[RuleDef, re.Pattern]],
    strategy: str,
    pepper: str | None,
    name_rule: RuleDef | None = None,
    person_list: set[str] | None = None,
) -> dict:
    """值级检测：值**整体**命中某敏感正则 → 用该规则脱敏。

    命中规则用 _scan_match_rule 判定；返回 {"masked_value", "changed"}。
    """
    v = value if value is not None else ""
    if not v.strip():
        return {"masked_value": "", "changed": 0}
    best = _scan_match_rule(value, regexes, name_rule, person_list)
    if best is None:
        return {"masked_value": value, "changed": 0}
    out = _apply_single(best, _canonical_for_rule(best, v.strip()), strategy, pepper)
    return {"masked_value": out, "changed": 1 if out != v.strip() else 0}


def _strip_match_anchors(pattern: str) -> str:
    """去掉 ^ / $，供格内扫描用。"""
    return pattern.removeprefix("^").removesuffix("$")


def _value_matches_rule(rule: RuleDef, value: str) -> bool:
    """值是否整体命中规则正则（列映射套模板前的校验）。"""
    s = value.strip()
    if not s:
        return False
    if _is_catchall_rule(rule) and _should_skip_catchall_value(s):
        return False
    if rule.name == "app_version" and _DATE_LIKE_VERSION_RE.fullmatch(s):
        return False
    cand = _canonical_for_rule(rule, s)
    try:
        return re.fullmatch(rule.match, cand) is not None
    except re.error:
        return False


def _build_cell_scan_regexes(ruleset: RuleSet) -> list[tuple[RuleDef, re.Pattern]]:
    """格内强特征扫描正则（去锚点，仅 _VALUE_SCAN_RULES）。IP 用带边界的专用正则。"""
    compiled = []
    for name in _VALUE_SCAN_RULES:
        d = ruleset.defs.get(name)
        if d is None or d.default_disabled:
            continue
        try:
            if name == "ip":
                compiled.append((d, CELL_IP_RE))
            else:
                compiled.append((d, re.compile(_strip_match_anchors(d.match))))
        except re.error:
            continue
    return compiled


def _mask_cell_inner(
    value: str,
    cell_regexes: list[tuple[RuleDef, re.Pattern]],
    name_rule: RuleDef | None,
    pepper: str | None,
    strategy: str,
    person_names: tuple[str, ...],
) -> str:
    """扫描单元格内部的强特征 PII，可选按人员清单做边界替换。

    不跑姓氏启发式（避免长句误伤）。
    """
    from maskit.rules.name_company import mask_person_list_in_text

    out = value
    for rule, regex in cell_regexes:
        def _repl(m: re.Match, r=rule) -> str:
            return _apply_single(r, m.group(0), strategy, pepper)

        out = regex.sub(_repl, out)
    by_name = {r.name: r for r, _ in cell_regexes}
    out = apply_pii_variants(out, by_name, strategy, pepper)
    if name_rule and person_names:
        out = mask_person_list_in_text(
            out,
            set(person_names),
            lambda n, nr=name_rule: _apply_single(nr, n, strategy, pepper),
        )
    return out


def _mask_one_cell(
    value: str | None,
    mapped_rule: RuleDef | None,
    mapped_strategy: str,
    regexes: list[tuple[RuleDef, re.Pattern]],
    name_rule: RuleDef | None,
    pepper: str | None,
    person_list: set[str] | None,
    cell_regexes: list[tuple[RuleDef, re.Pattern]],
    person_names: tuple[str, ...],
    value_scan: bool,
) -> dict:
    """单单元格：列映射（先校验）→ 整格值级检测 → 格内扫描。"""
    raw = value if value is not None else ""
    if not str(raw).strip():
        return {"masked_value": raw, "changed": 0}
    s = str(raw)
    if s.strip().startswith("="):
        return {"masked_value": s, "changed": 0}

    fallback_strategy = mapped_strategy if mapped_rule is not None else "mask"

    if mapped_rule is not None and _value_matches_rule(mapped_rule, s):
        apply_src = _canonical_for_rule(mapped_rule, s)
        return _apply_single_count(mapped_rule, apply_src, mapped_strategy, pepper)

    if not value_scan:
        return {"masked_value": s, "changed": 0}

    vs = _value_scan_single(s, regexes, fallback_strategy, pepper, name_rule, person_list)
    if vs["changed"]:
        return vs

    inner = _mask_cell_inner(
        s, cell_regexes, name_rule, pepper, fallback_strategy, person_names
    )
    return {"masked_value": inner, "changed": 1 if inner != s else 0}


def preview_dataframe(
    df: pl.DataFrame,
    ruleset: RuleSet,
    pepper: str | None = None,
    person_list: set[str] | None = None,
) -> list[dict]:
    """预验证 DataFrame：按规则集「预演」，返回每列统计（不产出文件）。

    每列一项：{column, rule, strategy, hits, total, ratio,
              sample_before, sample_after}。
    - rule 为命中规则名（列映射规则，或值级检测命中的规则）；无命中为 None
    - 判定逻辑与 apply_rules 一致（含值级检测补漏），保证预览=实际脱敏
    """
    from maskit.rules.matcher import auto_match_columns

    cols = df.columns
    # 列映射（与 _mask_dataframe 一致：缺列跳过 optional，否则报错）
    effective_specs = []
    for spec in ruleset.specs:
        if spec.column not in cols:
            if spec.optional:
                continue
            raise ValueError(f"规则引用了不存在的列: {spec.column!r}")
        effective_specs.append(spec)
    if not effective_specs and all(s.optional for s in ruleset.specs):
        effective_specs = auto_match_columns(cols)
    spec_by_col = {s.column: s for s in effective_specs}

    regexes = _build_value_scan_regexes(ruleset)
    cell_regexes = _build_cell_scan_regexes(ruleset)
    name_rule = ruleset.defs.get("name")
    person_names = tuple(sorted(person_list, key=len, reverse=True)) if person_list else ()

    results = []
    for col in cols:
        values = df[col].cast(pl.Utf8).to_list()
        total = hits = 0
        rule_label: str | None = None
        strategy_label: str | None = None
        sample_before = sample_after = None
        spec = spec_by_col.get(col)
        mapped_rule = None
        mapped_strategy = "mask"
        if spec is not None:
            mapped_rule = ruleset.defs.get(spec.rule)
            if mapped_rule is None:
                raise ValueError(f"规则 {spec.rule!r} 未定义")
            mapped_strategy = spec.strategy
            rule_label = spec.rule
            strategy_label = spec.strategy
        for v in values:
            if v is None:
                continue
            total += 1
            out = _mask_one_cell(
                v, mapped_rule, mapped_strategy, regexes, name_rule, pepper,
                person_list, cell_regexes, person_names, value_scan=True,
            )
            if out["changed"]:
                hits += 1
                if sample_before is None:
                    sample_before = v
                    sample_after = out["masked_value"]
                if rule_label is None:
                    hit = _scan_match_rule(v, regexes, name_rule, person_list)
                    rule_label = hit.name if hit else "in_cell"
                    strategy_label = "mask"
        results.append({
            "column": col,
            "rule": rule_label,
            "strategy": strategy_label,
            "hits": hits,
            "total": total,
            "ratio": round(hits / total, 3) if total else 0.0,
            "sample_before": sample_before,
            "sample_after": sample_after,
        })
    return results


def apply_rules(
    df: pl.DataFrame,
    ruleset: RuleSet,
    pepper: str | None,
    value_scan: bool = True,
    person_list: set[str] | None = None,
) -> tuple[pl.DataFrame, int]:
    """对 DataFrame 应用规则集，返回 (脱敏后 DataFrame, 脱敏单元格数)。

    每个单元格顺序：
    1. 列已映射且值整体命中该规则正则 → 按列策略整格脱敏
    2. 否则（value_scan=True）：整格值级检测（强特征 / 人员清单 / 无清单时启发式）
    3. 仍未命中 → 格内扫描强特征（email/ip/id_card/bank_card）+ 人员清单子串

    - null 保持为空字符串处理后的结果（与历史行为一致）
    """
    out = df
    total_masked = 0
    spec_by_col: dict[str, RuleSpec] = {}
    for spec in ruleset.specs:
        if spec.column not in out.columns:
            raise ValueError(f"规则引用了不存在的列: {spec.column!r}")
        rule = ruleset.defs.get(spec.rule)
        if rule is None:
            raise ValueError(f"规则 {spec.rule!r} 未定义")
        if rule.default_disabled:
            raise ValueError(f"规则 {spec.rule!r} 默认关闭，请在 YAML 中显式启用")
        spec_by_col[spec.column] = spec

    regexes = _build_value_scan_regexes(ruleset) if value_scan else []
    cell_regexes = _build_cell_scan_regexes(ruleset) if value_scan else []
    name_rule = ruleset.defs.get("name")
    person_names = tuple(sorted(person_list, key=len, reverse=True)) if person_list else ()

    for col_name in out.columns:
        spec = spec_by_col.get(col_name)
        if spec is None and not value_scan:
            continue
        mapped_rule = ruleset.defs.get(spec.rule) if spec is not None else None
        mapped_strategy = spec.strategy if spec is not None else "mask"
        col = pl.col(col_name).cast(pl.Utf8)
        result = col.map_elements(
            lambda v, mr=mapped_rule, ms=mapped_strategy: _mask_one_cell(
                v if v is not None else "",
                mr, ms, regexes, name_rule, pepper,
                person_list, cell_regexes, person_names, value_scan,
            ),
            return_dtype=pl.Struct({"masked_value": pl.Utf8, "changed": pl.Int8}),
        ).alias("__cell_result")
        out = out.with_columns(
            result.struct.field("masked_value").alias(col_name),
            result.struct.field("changed").alias("__changed"),
        )
        total_masked += int(out["__changed"].sum())
        out = out.drop("__changed")

    return out, total_masked


def validate_ruleset(ruleset: RuleSet) -> None:
    """校验规则集：列映射引用的规则都存在、策略合法。"""
    for spec in ruleset.specs:
        spec.validate(set(ruleset.defs.keys()))
