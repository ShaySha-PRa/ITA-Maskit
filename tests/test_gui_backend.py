"""GUI 优化对应的后端函数测试：preview_rule / discover_files / ruleset_info。"""
import pytest

from maskit.io import discover_files
from maskit.rules.engine import preview_rule
from maskit.rules.loader import _build_rule_def


@pytest.fixture
def user_rules_env(tmp_path, monkeypatch):
    """隔离规则集目录 + 当前规则集。"""
    monkeypatch.setenv("MASKIT_RULESETS_DIR", str(tmp_path / "rulesets"))
    monkeypatch.setenv("MASKIT_CURRENT_RS", str(tmp_path / "current"))
    return tmp_path


def _id_card_rule():
    return _build_rule_def(
        "id_card",
        {"match": r"\d{17}[\dX]", "mask": "{head:6}****{tail:4}", "pseudo": "ID-{hash:8}"},
    )


# --- preview_rule ---

def test_preview_rule_mask():
    """mask 预览：身份证被遮盖。"""
    r = preview_rule(_id_card_rule(), "110101199003077777")
    assert r["original"] == "110101199003077777"
    assert r["masked"] == "110101****7777"
    assert r["changed"] == 1
    assert r["strategy"] == "mask"


def test_preview_rule_pseudo():
    """pseudo 预览：确定性伪名化。"""
    r = preview_rule(_id_card_rule(), "110101199003077777", "pseudo", "pep")
    assert r["changed"] == 1
    assert r["masked"] != "110101199003077777"
    assert r["masked"].startswith("ID-")


def test_preview_rule_empty_value():
    """空值：不变化。"""
    r = preview_rule(_id_card_rule(), "")
    assert r["changed"] == 0


def test_preview_rule_short_value():
    """短值：mask 模板仍会处理（真实行为，预览展示给用户看）。"""
    r = preview_rule(_id_card_rule(), "沪")
    assert r["masked"] != ""  # 模板会重写，用户能看到效果


# --- discover_files ---

def test_discover_single_file(tmp_path):
    """单文件输入 → 返回该文件。"""
    f = tmp_path / "a.csv"
    f.write_text("x")
    assert discover_files(str(f)) == [str(f)]


def test_discover_folder_recursive(tmp_path):
    """文件夹递归扫描支持的扩展名，忽略不支持。"""
    (tmp_path / "a.csv").write_text("x")
    (tmp_path / "b.xlsx").write_bytes(b"x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.pdf").write_bytes(b"x")
    (sub / "ignore.txt").write_text("x")
    files = discover_files(str(tmp_path))
    assert len(files) == 3
    assert any(f.endswith("a.csv") for f in files)
    assert any(f.endswith("c.pdf") for f in files)
    assert not any(f.endswith("ignore.txt") for f in files)


def test_discover_missing_path():
    """路径不存在 → 报错。"""
    with pytest.raises(ValueError, match="不存在"):
        discover_files("/nonexistent/path/xyz")


def test_discover_empty_folder(tmp_path):
    """空文件夹 → 空列表。"""
    assert discover_files(str(tmp_path)) == []


# --- ruleset_info ---

def test_ruleset_info_builtin(user_rules_env):
    """内置默认规则集信息。"""
    from maskit.rules.user_rules import ruleset_info

    info = ruleset_info("内置默认")
    assert info["name"] == "内置默认"
    assert info["rule_count"] >= 10
    assert info["custom_count"] == 0


def test_ruleset_info_custom(user_rules_env):
    """带自定义规则的规则集信息。"""
    from maskit.rules.defs import BUILTIN_RULE_DEFS
    from maskit.rules.user_rules import ruleset_info, save_ruleset

    defs = {n: dict(r) for n, r in BUILTIN_RULE_DEFS.items()}
    defs["车牌号"] = {"version": "1.0", "match": r"^[京津沪][A-Z]\d{5}$", "mask": "{first}*", "pseudo": "PL"}
    save_ruleset("测试集", defs)
    info = ruleset_info("测试集")
    assert info["custom_count"] == 1
    assert "车牌号" in info["custom_rules"]
