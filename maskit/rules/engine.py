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

from maskit.detection.canonical import canonical_for_rule as _canonical_for_rule
from maskit.detection.canonical import should_skip_catchall_value as _should_skip_catchall_value_raw
from maskit.detection.canonical import to_halfwidth as _to_halfwidth
from maskit.detection.canonical import value_matches_rule as _value_matches_rule_raw
from maskit.detection.patterns import CELL_IP_RE
from maskit.detection.patterns import DASHED_BANK_RE as _DASHED_BANK_RE
from maskit.detection.patterns import EMAIL_BODY_RE as _EMAIL_BODY_RE
from maskit.detection.patterns import SPACED_ID_RE as _SPACED_ID_RE
from maskit.detection.patterns import VALUE_SCAN_RULES as _VALUE_SCAN_RULES
from maskit.detection.patterns import strip_anchors as _strip_match_anchors
from maskit.normalize import normalize_default
from maskit.rules.defs import NORMALIZERS, RuleDef, RuleSet, RuleSpec
from maskit.rules.name_company import COMMON_NON_NAMES as _COMMON_NON_NAMES
from maskit.rules.name_company import is_person_name as _is_person_name


def _hold_checksum_review(
    rule: RuleDef,
    original: str,
    apply_src: str,
    *,
    column: str | None = None,
    checksum_policy: str | None = None,
) -> bool:
    """INVALID checksum under review/strict → do not write."""
    from maskit.detection.policy import checksum_should_review

    if checksum_policy == "legacy":
        return False
    return checksum_should_review(rule.name, apply_src, checksum_policy)


def _allowlisted(rule_name: str, value: str, allowlist=None) -> bool:
    from maskit.detection.policy import current_allowlist

    al = allowlist if allowlist is not None else current_allowlist()
    if al is None or not getattr(al, "entries", None):
        return False
    from maskit.detection.review import fingerprint

    return al.allows(rule_name, value, fingerprint=fingerprint(value))


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


NORMALIZER_VERSION = "1"

def pseudo_key_v2(pepper: str, entity_type: str) -> bytes:
    """v2: HMAC(pepper, maskit:pseudonym:v2) then HMAC(root, entity_type)."""
    root = hmac.new(
        pepper.encode("utf-8"), b"maskit:pseudonym:v2", hashlib.sha256
    ).digest()
    return hmac.new(root, entity_type.encode("utf-8"), hashlib.sha256).digest()


def pseudo_hash_v2(
    value: str,
    pepper: str,
    entity_type: str,
    *,
    length: int = 24,
    normalizer_version: str = NORMALIZER_VERSION,
) -> str:
    """96-bit hex default. Domain-separated by entity type + normalizer version."""
    key = pseudo_key_v2(pepper, entity_type)
    msg = f"v2|{normalizer_version}|{value}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()[:length].upper()


def digits_from_hex(hex_str: str, n: int) -> str:
    """HMAC hex → deterministic decimal digits (shared with native parity)."""
    return "".join(str(int(c, 16) % 10) for c in hex_str)[:n].ljust(n, "0")


def hmac_digest(value: str, key: bytes, length: int = 8) -> str:
    """确定性 HMAC 哈希，输出 hex 前缀。"""
    digest = hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:length].upper()


def pseudo_hash(value: str, pepper: str, length: int = 8) -> str:
    """确定性伪名哈希（对规范化后的值）。"""
    return hmac_digest(value, pseudo_key(pepper), length)


def render_template(
    template: str,
    value: str,
    pepper: str | None,
    *,
    scheme: str = "v1",
    entity_type: str = "",
    hmac_hex: str | None = None,
) -> str:
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
        if hmac_hex is not None:
            digest = hmac_hex[:24] if scheme == "v2" else hmac_hex[:8]
        elif scheme == "v2":
            digest = pseudo_hash_v2(value, pepper, entity_type or "unknown", length=24)
        else:
            digest = pseudo_hash(value, pepper, 8)
        template = template.replace("{hash:8}", digest)

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
        if hmac_hex is not None:
            h = hmac_hex[: max(16, n)] if scheme == "v2" else hmac_hex[:16]
        elif scheme == "v2":
            h = pseudo_hash_v2(value, pepper, entity_type or "unknown", length=max(16, n))
        else:
            h = pseudo_hash(value, pepper, 16)
        digits = digits_from_hex(h, n)
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


def _pseudo_single_v2(rule: RuleDef, value: str, pepper: str) -> str:
    """Opt-in v2 pseudonym: 96-bit, entity-type domain separation. Does not change v1."""
    if not value:
        return value
    norm_fn = NORMALIZERS.get(rule.normalize, normalize_default)
    norm_value = norm_fn(value)
    return render_template(
        rule.pseudo, norm_value, pepper, scheme="v2", entity_type=rule.name
    )


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
    elif strategy == "pseudo_v2":
        if pepper is None:
            raise ValueError(
                "pseudo_v2 策略激活但未提供 --pepper（或 MASKIT_PEPPER），拒绝静默执行"
            )
        out = _pseudo_single_v2(rule, value, pepper)
    else:
        raise ValueError(f"非法策略: {strategy}")
    return {"masked_value": out, "changed": 1 if out != value else 0}


def _should_skip_catchall_value(value: str) -> bool:
    """部门/科室或排除词 → 不套 name/company 的 .+ 模板。"""
    return _should_skip_catchall_value_raw(value, _COMMON_NON_NAMES)


def _value_matches_rule(rule: RuleDef, value: str) -> bool:
    """值是否整体命中规则正则（列映射套模板前的校验）。"""
    return _value_matches_rule_raw(rule, value, _COMMON_NON_NAMES)


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
    column: str | None = None,
    checksum_policy: str | None = None,
    allowlist=None,
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
    apply_src = _canonical_for_rule(best, v.strip())
    if _allowlisted(best.name, v, allowlist):
        return {"masked_value": value, "changed": 0}
    if (
        checksum_policy != "legacy"
        and _hold_checksum_review(
            best, v, apply_src, column=column, checksum_policy=checksum_policy
        )
    ):
        return {"masked_value": value, "changed": 0, "review": 1}
        return {"masked_value": value, "changed": 0}
    out = _apply_single(best, apply_src, strategy, pepper)
    return {"masked_value": out, "changed": 1 if out != v.strip() else 0}


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
    column: str | None = None,
    checksum_policy: str | None = None,
) -> str:
    """扫描单元格内部的强特征 PII，可选按人员清单做边界替换。

    不跑姓氏启发式（避免长句误伤）。
    """
    from maskit.rules.name_company import mask_person_list_in_text

    out = value
    for rule, regex in cell_regexes:
        def _repl(m: re.Match, r=rule) -> str:
            src = m.group(0)
            if r.name in {"id_card", "bank_card"}:
                apply_src = _canonical_for_rule(r, src)
                if checksum_policy != "legacy" and _hold_checksum_review(
                    r, src, apply_src, column=column, checksum_policy=checksum_policy
                ):
                    return src
                return _apply_single(r, apply_src, strategy, pepper)
            return _apply_single(r, src, strategy, pepper)

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


def _apply_src(hit) -> str:
    """Mask/pseudo 输入：证件/卡号/全角邮箱用规范化值，其余用原文（与历史行为一致）。"""
    if hit.original_value != hit.normalized_value and hit.entity_type in {
        "id_card",
        "bank_card",
        "email",
    }:
        return hit.normalized_value
    return hit.original_value


def _apply_detections(
    raw: str,
    hits: list,
    strategy: str,
    pepper: str | None,
    ruleset: RuleSet,
) -> dict:
    """把 DetectionResult 列表变成脱敏字符串（不改检测逻辑）。"""
    if not hits:
        return {"masked_value": raw, "changed": 0}
    whole = [h for h in hits if h.start is None]
    if whole:
        h = whole[0]
        rule = ruleset.defs.get(h.entity_type)
        if rule is None:
            return {"masked_value": raw, "changed": 0}
        return _apply_single_count(rule, _apply_src(h), strategy, pepper)
    ordered = sorted(hits, key=lambda h: len(h.original_value), reverse=True)
    out = raw
    seen: set[str] = set()
    for h in ordered:
        if h.original_value in seen:
            continue
        seen.add(h.original_value)
        rule = ruleset.defs.get(h.entity_type)
        if rule is None:
            continue
        repl = _apply_single(rule, _apply_src(h), strategy, pepper)
        out = out.replace(h.original_value, repl)
    return {"masked_value": out, "changed": 1 if out != raw else 0}


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
    ruleset: RuleSet | None = None,
    bind_mode: str = "validate",
    column: str | None = None,
    checksum_policy: str | None = None,
    allowlist=None,
) -> dict:
    """单单元格：列映射（先校验）→ 整格值级检测 → 格内扫描。

    bind_mode=force 时跳过格式校验（仅用户显式 FORCE，列名推断不得进入）。
    """
    raw = value if value is not None else ""
    if not str(raw).strip():
        return {"masked_value": raw, "changed": 0}
    s = str(raw)
    if s.strip().startswith("="):
        return {"masked_value": s, "changed": 0}

    fallback_strategy = mapped_strategy if mapped_rule is not None else "mask"

    if mapped_rule is not None:
        force = bind_mode == "force" and bool(s.strip())
        if force or _value_matches_rule(mapped_rule, s):
            if _allowlisted(mapped_rule.name, s, allowlist):
                return {"masked_value": s, "changed": 0}
            apply_src = _canonical_for_rule(mapped_rule, s)
            if (
                bind_mode != "force"
                and checksum_policy != "legacy"
                and _hold_checksum_review(
                    mapped_rule, s, apply_src, column=column, checksum_policy=checksum_policy
                )
            ):
                return {"masked_value": s, "changed": 0}
            return _apply_single_count(mapped_rule, apply_src, mapped_strategy, pepper)

    if not value_scan:
        return {"masked_value": s, "changed": 0}

    vs = _value_scan_single(
        s, regexes, fallback_strategy, pepper, name_rule, person_list,
        column=column, checksum_policy=checksum_policy, allowlist=allowlist,
    )
    if vs["changed"] or vs.get("review"):
        return {"masked_value": vs["masked_value"], "changed": vs["changed"]}

    inner = _mask_cell_inner(
        s, cell_regexes, name_rule, pepper, fallback_strategy, person_names,
        column=column, checksum_policy=checksum_policy,
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
    from maskit.detection.plan import compile_column_plan, mapped_rule_for

    cols = df.columns
    plan = compile_column_plan(list(cols), ruleset)
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
        binding = plan.binding_for(col)
        mapped_rule = mapped_rule_for(plan, ruleset, col)
        mapped_strategy = binding.strategy if binding else "mask"
        bind_mode = binding.bind_mode if binding else "validate"
        if binding is not None:
            rule_label = binding.rule
            strategy_label = binding.strategy
        from maskit.detection.policy import checksum_should_review, current_checksum_policy

        checksum_policy = current_checksum_policy()
        col_review = 0
        for v in values:
            if v is None:
                continue
            total += 1
            out = _mask_one_cell(
                v, mapped_rule, mapped_strategy, regexes, name_rule, pepper,
                person_list, cell_regexes, person_names, value_scan=True,
                ruleset=ruleset, bind_mode=bind_mode, column=col,
                checksum_policy=checksum_policy,
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
            elif mapped_rule is not None and checksum_should_review(
                mapped_rule.name, str(v), checksum_policy
            ):
                col_review += 1
            elif mapped_rule is None:
                for rn in ("id_card", "bank_card"):
                    if checksum_should_review(rn, str(v), checksum_policy):
                        col_review += 1
                        break
        results.append({
            "column": col,
            "rule": rule_label,
            "strategy": strategy_label,
            "hits": hits,
            "total": total,
            "ratio": round(hits / total, 3) if total else 0.0,
            "sample_before": sample_before,
            "sample_after": sample_after,
            "auto_apply": hits,
            "review": col_review,
            "reject": 0,
        })
    return results


def _template_needs_hmac(template: str) -> bool:
    return "{hash:8}" in template or "{digits}" in template


def _apply_mapped_pseudo_column(
    values: list,
    mapped_rule: RuleDef,
    mapped_strategy: str,
    regexes: list[tuple[RuleDef, re.Pattern]],
    name_rule: RuleDef | None,
    pepper: str,
    person_list: set[str] | None,
    cell_regexes: list[tuple[RuleDef, re.Pattern]],
    person_names: tuple[str, ...],
    value_scan: bool,
    ruleset: RuleSet,
    bind_mode: str,
    column: str,
    checksum_policy: str | None,
    allowlist,
    backend,
) -> tuple[list[str], int]:
    """Mapped pseudo/pseudo_v2 column: match in Python, HMAC in one batch.

    Cells that miss the mapped rule still go through _mask_one_cell.
    `changed` matches _apply_single_count (compare against apply_src).
    """
    scheme = "v2" if mapped_strategy == "pseudo_v2" else "v1"
    norm_fn = NORMALIZERS.get(mapped_rule.normalize, normalize_default)
    need_hmac = _template_needs_hmac(mapped_rule.pseudo)

    out: list[str] = [""] * len(values)
    changed = 0
    batch_idx: list[int] = []
    norms: list[str] = []
    apply_srcs: list[str] = []

    for i, v in enumerate(values):
        raw = "" if v is None else str(v)
        if not raw.strip() or raw.strip().startswith("="):
            out[i] = raw
            continue
        force = bind_mode == "force" and bool(raw.strip())
        if not (force or _value_matches_rule(mapped_rule, raw)):
            cell = _mask_one_cell(
                raw,
                mapped_rule,
                mapped_strategy,
                regexes,
                name_rule,
                pepper,
                person_list,
                cell_regexes,
                person_names,
                value_scan,
                ruleset=ruleset,
                bind_mode=bind_mode,
                column=column,
                checksum_policy=checksum_policy,
                allowlist=allowlist,
            )
            out[i] = cell["masked_value"]
            changed += int(cell["changed"])
            continue
        if _allowlisted(mapped_rule.name, raw, allowlist):
            out[i] = raw
            continue
        apply_src = _canonical_for_rule(mapped_rule, raw)
        if (
            bind_mode != "force"
            and checksum_policy != "legacy"
            and _hold_checksum_review(
                mapped_rule,
                raw,
                apply_src,
                column=column,
                checksum_policy=checksum_policy,
            )
        ):
            out[i] = raw
            continue
        batch_idx.append(i)
        apply_srcs.append(apply_src)
        norms.append(norm_fn(apply_src))

    hmac_hexes: list[str | None]
    if batch_idx and need_hmac:
        hmac_hexes = backend.hash_batch(
            norms, pepper, scheme, [mapped_rule.name], 64, "1"
        )
    else:
        hmac_hexes = [None] * len(norms)

    for j, i in enumerate(batch_idx):
        masked = render_template(
            mapped_rule.pseudo,
            norms[j],
            pepper,
            scheme=scheme,
            entity_type=mapped_rule.name,
            hmac_hex=hmac_hexes[j],
        )
        out[i] = masked
        if masked != apply_srcs[j]:
            changed += 1

    return out, changed


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

    from maskit.detection.policy import current_allowlist, current_checksum_policy

    checksum_policy = current_checksum_policy()
    allowlist = current_allowlist()
    pseudo_backend = None
    for col_name in out.columns:
        spec = spec_by_col.get(col_name)
        if spec is None and not value_scan:
            continue
        mapped_rule = ruleset.defs.get(spec.rule) if spec is not None else None
        mapped_strategy = spec.strategy if spec is not None else "mask"
        bind_mode = spec.bind_mode if spec is not None else "validate"
        if (
            mapped_rule is not None
            and mapped_strategy in {"pseudo", "pseudo_v2"}
            and pepper is not None
        ):
            orig_vals = out[col_name].cast(pl.Utf8).to_list()
            if pseudo_backend is None:
                from maskit.native import get_backend

                pseudo_backend = get_backend()
            masked_vals, n_changed = _apply_mapped_pseudo_column(
                orig_vals,
                mapped_rule,
                mapped_strategy,
                regexes,
                name_rule,
                pepper,
                person_list,
                cell_regexes,
                person_names,
                value_scan,
                ruleset,
                bind_mode,
                col_name,
                checksum_policy,
                allowlist,
                pseudo_backend,
            )
            out = out.with_columns(pl.Series(col_name, masked_vals, dtype=pl.Utf8))
            total_masked += n_changed
            if checksum_policy != "legacy":
                from maskit.detection.policy import checksum_should_review
                from maskit.detection.runctx import current_run

                stats = current_run()
                for orig, new in zip(orig_vals, masked_vals):
                    if orig is None or str(orig) != str(new):
                        continue
                    if checksum_should_review(mapped_rule.name, str(orig), checksum_policy):
                        stats.add_review(
                            entity_type=mapped_rule.name,
                            value=str(orig),
                            column=col_name,
                            reason="checksum invalid",
                            validation_status="INVALID",
                            recognizer="checksum",
                        )
            continue
        orig_vals = out[col_name].to_list() if checksum_policy != "legacy" else None
        col = pl.col(col_name).cast(pl.Utf8)
        result = col.map_elements(
            lambda v, mr=mapped_rule, ms=mapped_strategy, bm=bind_mode, cn=col_name, pol=checksum_policy, al=allowlist: _mask_one_cell(
                v if v is not None else "",
                mr, ms, regexes, name_rule, pepper,
                person_list, cell_regexes, person_names, value_scan,
                ruleset=ruleset, bind_mode=bm, column=cn, checksum_policy=pol,
                allowlist=al,
            ),
            return_dtype=pl.Struct({"masked_value": pl.Utf8, "changed": pl.Int8}),
        ).alias("__cell_result")
        out = out.with_columns(
            result.struct.field("masked_value").alias(col_name),
            result.struct.field("changed").alias("__changed"),
        )
        total_masked += int(out["__changed"].sum())
        out = out.drop("__changed")
        if checksum_policy != "legacy" and orig_vals is not None:
            from maskit.detection.policy import checksum_should_review
            from maskit.detection.runctx import current_run

            stats = current_run()
            for orig, new in zip(orig_vals, out[col_name].to_list()):
                if orig is None or str(orig) != str(new):
                    continue
                names = [mapped_rule.name] if mapped_rule is not None else ["id_card", "bank_card"]
                for rn in names:
                    if checksum_should_review(rn, str(orig), checksum_policy):
                        stats.add_review(
                            entity_type=rn,
                            value=str(orig),
                            column=col_name,
                            reason="checksum invalid",
                            validation_status="INVALID",
                            recognizer="checksum",
                        )
                        break

    from maskit.detection.runctx import current_run

    current_run().auto_apply += total_masked
    return out, total_masked


def validate_ruleset(ruleset: RuleSet) -> None:
    """校验规则集：列映射引用的规则都存在、策略合法。"""
    for spec in ruleset.specs:
        spec.validate(set(ruleset.defs.keys()))
