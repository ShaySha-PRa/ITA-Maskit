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
from maskit.rules.defs import NORMALIZERS, RuleDef, RuleSet


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

# 中文人名检测（排除词表 + 姓氏开头）：
# 值级检测对「排除词表外 + 姓氏开头 + 2-4字纯中文」判定为人名，按 name 规则脱敏。
# 覆盖横排选手/教练收入表里的人名（无列名可依）。
_COMMON_SURNAMES = set(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹"
    "喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉岑薛雷贺倪"
    "汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹"
    "狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童"
    "颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯昝管卢莫经房裘缪干解应宗丁"
    "宣贲邓郁单杭洪包诸左石崔吉钮龚党刘姬"
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


def _is_person_name(value: str) -> bool:
    """判断值是否为中文人名（排除词表外 + 姓氏开头 + 2-4字纯中文）。"""
    v = value.strip()
    if not re.fullmatch(r"[一-鿿]{2,4}", v):
        return False
    if v in _COMMON_NON_NAMES:
        return False
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


def _value_scan_single(
    value: str,
    regexes: list[tuple[RuleDef, re.Pattern]],
    strategy: str,
    pepper: str | None,
    name_rule: RuleDef | None = None,
) -> dict:
    """值级检测：值**整体**命中某敏感正则 → 用该规则脱敏。

    - 强特征规则（email/ip/id_card）整值匹配
    - 中文人名检测：排除词表外 + 姓氏开头的 2-4 字纯中文 → 按 name 脱敏
    - 公式保护：=SUM(...) 开头不检测
    返回 {"masked_value", "changed"}。
    """
    v = value if value is not None else ""
    if not v.strip():
        return {"masked_value": "", "changed": 0}
    # 公式保护：Excel 公式（=SUM...）不做值检测
    if v.strip().startswith("="):
        return {"masked_value": value, "changed": 0}
    # 找命中的规则（最长正则优先）
    best = None
    best_len = -1
    for d, regex in regexes:
        if regex.fullmatch(v.strip()) and len(d.match) > best_len:
            best = d
            best_len = len(d.match)
    # 中文人名检测（排除词表外 + 姓氏开头）
    if best is None and name_rule is not None and _is_person_name(v):
        best = name_rule
    if best is None:
        return {"masked_value": value, "changed": 0}
    out = _apply_single(best, v.strip(), strategy, pepper)
    return {"masked_value": out, "changed": 1 if out != v.strip() else 0}


def apply_rules(
    df: pl.DataFrame,
    ruleset: RuleSet,
    pepper: str | None,
    value_scan: bool = True,
) -> tuple[pl.DataFrame, int]:
    """对 DataFrame 应用规则集，返回 (脱敏后 DataFrame, 脱敏单元格数)。

    - 映射列按规则/策略处理
    - 未映射列：value_scan=True 时做值级检测（身份证/手机/邮箱等强正则），
      命中即脱敏（补列名漏检）
    - null 保持 null
    """
    out = df
    total_masked = 0
    matched_cols = set()
    for spec in ruleset.specs:
        if spec.column not in out.columns:
            raise ValueError(f"规则引用了不存在的列: {spec.column!r}")
        rule = ruleset.defs.get(spec.rule)
        if rule is None:
            raise ValueError(f"规则 {spec.rule!r} 未定义")
        if rule.default_disabled:
            raise ValueError(f"规则 {spec.rule!r} 默认关闭，请在 YAML 中显式启用")

        matched_cols.add(spec.column)
        col = pl.col(spec.column).cast(pl.Utf8)
        # map_elements 返回 dict {masked_value, changed}，拆出值列 + 计数列
        result = col.map_elements(
            lambda v, r=rule, s=spec: _apply_single_count(
                r, v if v is not None else "", s.strategy, pepper
            ),
            return_dtype=pl.Struct({"masked_value": pl.Utf8, "changed": pl.Int8}),
        ).alias("__masked_result")
        # 展开
        out = out.with_columns(
            result.struct.field("masked_value").alias(spec.column),
            result.struct.field("changed").alias("__changed"),
        )
        total_masked += int(out["__changed"].sum())
        out = out.drop("__changed")

    # 值级检测：未匹配列的值跑敏感正则（补列名漏检）
    if value_scan:
        regexes = _build_value_scan_regexes(ruleset)
        name_rule = ruleset.defs.get("name")
        if regexes or name_rule:
            for col_name in out.columns:
                if col_name in matched_cols:
                    continue  # 已匹配列不重复
                col = pl.col(col_name).cast(pl.Utf8)
                result = col.map_elements(
                    lambda v, rx=regexes, nr=name_rule, p=pepper: _value_scan_single(
                        v if v is not None else "", rx, "mask", p, nr
                    ),
                    return_dtype=pl.Struct({"masked_value": pl.Utf8, "changed": pl.Int8}),
                ).alias("__vs_result")
                out = out.with_columns(
                    result.struct.field("masked_value").alias(col_name),
                    result.struct.field("changed").alias("__vs_changed"),
                )
                total_masked += int(out["__vs_changed"].sum())
                out = out.drop("__vs_changed")

    return out, total_masked


def validate_ruleset(ruleset: RuleSet) -> None:
    """校验规则集：列映射引用的规则都存在、策略合法。"""
    for spec in ruleset.specs:
        spec.validate(set(ruleset.defs.keys()))
