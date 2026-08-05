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

    if "{last}" in template:
        template = template.replace("{last}", value[-1:] if value else "")

    if "{tail:4}" in template:
        template = template.replace("{tail:4}", value[-4:] if len(value) >= 4 else value)

    if "{head:3}" in template:
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
    """按策略派发单值处理（供 Polars map_elements 调用）。"""
    if strategy == "mask":
        return _mask_single(rule, value)
    if strategy == "pseudo":
        if pepper is None:
            raise ValueError(
                "pseudo 策略激活但未提供 --pepper（或 MASKIT_PEPPER），拒绝静默执行"
            )
        return _pseudo_single(rule, value, pepper)
    raise ValueError(f"非法策略: {strategy}")


def apply_rules(
    df: pl.DataFrame,
    ruleset: RuleSet,
    pepper: str | None,
) -> pl.DataFrame:
    """对 DataFrame 应用规则集，返回脱敏后的 DataFrame。

    - 映射列按规则/策略处理
    - 未映射列原样透传
    - null 保持 null
    """
    out = df
    for spec in ruleset.specs:
        if spec.column not in out.columns:
            raise ValueError(f"规则引用了不存在的列: {spec.column!r}")
        rule = ruleset.defs.get(spec.rule)
        if rule is None:
            raise ValueError(f"规则 {spec.rule!r} 未定义")
        if rule.default_disabled:
            raise ValueError(f"规则 {spec.rule!r} 默认关闭，请在 YAML 中显式启用")

        col = pl.col(spec.column)
        expr = col.map_elements(
            # B023：用默认参数绑定循环变量，避免闭包捕获引用导致迭代串值
            lambda v, r=rule, s=spec: _apply_single(
                r, v if v is not None else "", s.strategy, pepper
            ),
            return_dtype=pl.Utf8,
        )
        out = out.with_columns(expr.alias(spec.column))
    return out


def validate_ruleset(ruleset: RuleSet) -> None:
    """校验规则集：列映射引用的规则都存在、策略合法。"""
    for spec in ruleset.specs:
        spec.validate(set(ruleset.defs.keys()))
