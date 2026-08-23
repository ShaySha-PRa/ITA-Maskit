"""Unit tests for unified phone / employee_id / app_version / name / bind modes."""

import polars as pl
import pytest

from maskit.detection.employee import looks_like_employee_id
from maskit.detection.phone import classify_phone, is_date_like, is_phone_value
from maskit.detection.pipeline import detect_cell, detect_text
from maskit.detection.scope import DEFAULT_EMPLOYEE_PREFIXES
from maskit.detection.version import is_app_version_value
from maskit.rules.defs import RuleSet, RuleSpec
from maskit.rules.engine import apply_rules
from maskit.rules.loader import load_ruleset
from maskit.rules.name_company import iter_person_list_spans


def _types(hits) -> set[str]:
    return {h.entity_type for h in hits}


def test_amount_not_app_version():
    rs = load_ruleset()
    for raw in ("金额 2.5 元", "0.8", "13.08"):
        assert "app_version" not in _types(detect_text(raw, ruleset=rs))


def test_version_context_and_v_prefix():
    rs = load_ruleset()
    assert "app_version" in _types(detect_text("Version 2.5 released", ruleset=rs))
    assert "app_version" in _types(detect_text("客户端版本 v2.5 发布", ruleset=rs))
    assert "app_version" in _types(detect_text("build 13.08 已出", ruleset=rs))
    hits = detect_text("v2.5", ruleset=rs)
    assert "app_version" in _types(hits)


def test_landline_is_phone_not_employee_id():
    rs = load_ruleset()
    for raw in ("010-12989966", "0755-5707154"):
        hits = detect_text(f"值班座机 {raw} 勿外拨", ruleset=rs)
        assert "phone" in _types(hits)
        assert "employee_id" not in _types(hits)
        assert classify_phone(raw, column_mode=False)[0] == "landline"


def test_standards_not_employee_id():
    rs = load_ruleset()
    for raw in ("ISO-8601", "RFC-2119", "CVE-2024", "JIRA-1001"):
        hits = detect_text(f"格式参考 {raw} ，勿改", ruleset=rs)
        assert "employee_id" not in _types(hits)
        assert not looks_like_employee_id(raw, DEFAULT_EMPLOYEE_PREFIXES)


def test_phone_column_dates_not_masked():
    rs = load_ruleset()
    phone = rs.defs["phone"]
    for d in ("2019.06.22", "2022-02-28", "2024/8/13"):
        assert is_date_like(d)
        assert not is_phone_value(d, column_mode=True)
        assert detect_cell(d, ruleset=rs, mapped_rule=phone) == []
    df = pl.DataFrame({"phone": ["2019.06.22", "2022-02-28", "2024/8/13", "13800138000"]})
    subset = RuleSet(
        defs=rs.defs,
        specs=[RuleSpec(column="phone", rule="phone", strategy="mask")],
    )
    masked, n = apply_rules(df, subset, None)
    rows = masked["phone"].to_list()
    assert rows[0] == "2019.06.22"
    assert rows[1] == "2022-02-28"
    assert rows[2] == "2024/8/13"
    assert rows[3] != "13800138000"
    assert n == 1


def test_explicit_force_phone_column_masks_non_phone():
    rs = load_ruleset()
    forced = RuleSet(
        defs=rs.defs,
        specs=[RuleSpec(column="phone", rule="phone", strategy="mask", bind_mode="force")],
    )
    df = pl.DataFrame({"phone": ["2019.06.22"]})
    masked, n = apply_rules(df, forced, None)
    assert n == 1
    assert masked["phone"].to_list()[0] != "2019.06.22"


def test_name_action_boundary_and_no_truncate():
    people = {"张伟", "司马光"}
    assert iter_person_list_spans("经办张伟复核", people) == [(2, 4, "张伟")]
    assert iter_person_list_spans("张伟达", people) == []
    assert iter_person_list_spans("司马光华不是清单名", people) == []
    longer = {"司马光", "司马光华"}
    spans = iter_person_list_spans("司马光华不是清单名", longer)
    assert spans == [(0, 4, "司马光华")]


def test_column_version_skips_date_allows_token():
    assert not is_app_version_value("2024.1.1", column_mode=True)
    assert is_app_version_value("v1.2.3", column_mode=True)
    assert is_app_version_value("1.4.2", column_mode=True)


@pytest.mark.parametrize(
    "raw",
    [
        "13800138000",
        "138-0013-8000",
        "138 0013 8000",
        "+86 13800138000",
        "0086-13800138000",
        "１３８００１３８０００",
    ],
)
def test_mobile_formats_same_entity(raw):
    rs = load_ruleset()
    hits = detect_text(f"手机 {raw}", ruleset=rs)
    assert "phone" in _types(hits)
    subtype, canon = classify_phone(raw, column_mode=True)
    assert subtype == "mobile"
    assert canon.endswith("13800138000") or "13800138000" in canon.replace("+86", "")
