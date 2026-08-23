"""Person-list Trie must match Python iter_person_list_spans_ref."""

from __future__ import annotations

import pytest

from maskit.native import get_backend, native_available, native_unavailable_reason
from maskit.native.fallback import PythonReferenceBackend
from maskit.rules.name_company import iter_person_list_spans_ref

CASES = [
    ({"张伟", "司马光"}, "经办张伟复核", [(2, 4, "张伟")]),
    ({"张伟", "司马光"}, "张伟达", []),
    ({"张伟", "司马光"}, "司马光华不是清单名", []),
    ({"司马光", "司马光华"}, "司马光华不是清单名", [(0, 4, "司马光华")]),
    ({"司马光", "司马光华"}, "司马光", [(0, 3, "司马光")]),
    ({"张伟"}, "东方不败工作室来函", []),
    ({"东方不败"}, "东方不败工作室来函", []),
    ({"张伟", "李娜"}, "张伟和李娜均出席", [(0, 2, "张伟"), (3, 5, "李娜")]),
    ({"张伟"}, "", []),
    ({"张伟"}, "😀张伟ok", [(1, 3, "张伟")]),
    (set(), "张伟", []),
    ({"张伟"}, "见张伟。", [(1, 3, "张伟")]),
    ({"Alice Chen"}, "Ask Alice Chen today", [(4, 14, "Alice Chen")]),
]


@pytest.mark.parametrize("names,text,expected", CASES)
def test_python_reference_cases(names, text, expected):
    assert iter_person_list_spans_ref(text, names) == expected


@pytest.mark.skipif(not native_available(), reason=native_unavailable_reason() or "no native")
@pytest.mark.parametrize("names,text,expected", CASES)
def test_native_matches_reference(names, text, expected):
    py = PythonReferenceBackend().match_person_list(text, names)
    nt = get_backend("native").match_person_list(text, names)
    assert py == expected
    assert nt == py


@pytest.mark.skipif(not native_available(), reason=native_unavailable_reason() or "no native")
def test_compare_backend_and_batch():
    names = {"张伟", "李娜", "司马光", "司马光华"}
    texts = [c[1] for c in CASES]
    be = get_backend("compare")
    assert be.match_person_list_batch(texts, names) == [
        PythonReferenceBackend().match_person_list(t, names) for t in texts
    ]


@pytest.mark.skipif(not native_available(), reason=native_unavailable_reason() or "no native")
def test_duplicate_names_compile_once():
    import maskit._native as ext

    compiled = ext.compile_person_list(["张伟", "张伟", ""])
    assert compiled.size() == 1
    assert compiled.match("见张伟。") == [(1, 3, "张伟")]


@pytest.mark.skipif(not native_available(), reason=native_unavailable_reason() or "no native")
def test_large_list_and_wired_entry():
    names = {f"测名{i:04d}" for i in range(4000)}
    names.update({"张伟", "司马光华"})
    text = "经办张伟复核，司马光华到场。"
    py = iter_person_list_spans_ref(text, names)
    nt = get_backend("native").match_person_list(text, names)
    assert py == nt
    from maskit.rules.name_company import iter_person_list_spans

    assert iter_person_list_spans(text, names) == py
