"""生成大量带期望标签的检测压力集（合成数据，不是现场语料）。

标签是「期望行为」而不是「当前实现」：日期不当电话、空格证号是身份证、
固定电话在文档里仍应识别、ISO-8601 不当工号。跑评测才能暴露误伤/漏检。

用法（仓库根目录）:
  python3 scripts/gen_stress_gold.py
  python3 -m maskit.detection.eval_gold benchmark/stress.jsonl --errors 40
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

ROOT = Path(__file__).resolve().parents[1]
OUT_JSONL = ROOT / "benchmark" / "stress.jsonl"
OUT_DIR = ROOT / "testdata" / "stress"
SEED = 20260821

_ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_ID_CHECK = "10X98765432"

PHONE_HEADS = (
    "130", "131", "132", "133", "135", "136", "137", "138", "139",
    "150", "151", "152", "157", "158", "159", "186", "187", "188", "189", "191",
)
EMAIL_USERS = (
    "alice", "bob.liu", "nina.wu", "ops+oncall", "eva.li", "david.zhang",
    "carol", "oncall.duty",
)
EMAIL_DOMAINS = ("corp.example", "audit.example", "internal.local", "mail.cn.example")
AREAS = ("110101", "310101", "440301", "440106", "320102", "510107")
PEOPLE = ["张伟", "李娜", "司马光", "上官婉儿", "诸葛孔明", "刘洋", "王芳", "Alice Chen"]
OUT_OF_LIST = ["赵磊", "黄敏", "周杰"]
DEPTS = ("财务部", "审计部", "人事处", "法务科", "运维组")
COMPANIES = ("亚玛芬体育", "小菜园集团", "MayAir", "华为", "腾讯")
LOOKALIKE_IDS = (
    "ISO-8601", "RFC-2119", "CVE-2024", "GB-18030", "UTF-16", "E2E-2024",
    "JIRA-1001", "PR-2026", "DOC-0001", "ITIL-2011",
)


def id_check(body17: str) -> str:
    total = sum(int(body17[i]) * _ID_WEIGHTS[i] for i in range(17))
    return _ID_CHECK[total % 11]


def make_id(rng: random.Random) -> str:
    area = rng.choice(AREAS)
    y = rng.randint(1968, 2004)
    m = rng.randint(1, 12)
    d = rng.randint(1, 28)
    seq = f"{rng.randint(0, 999):03d}"
    body = f"{area}{y}{m:02d}{d:02d}{seq}"
    return body + id_check(body)


def space_id(value: str) -> str:
    return f"{value[:6]} {value[6:14]} {value[14:]}"


def luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def make_bank(rng: random.Random, length: int = 16) -> str:
    prefix = "622202"
    mid_len = length - 7
    while True:
        mid = "".join(rng.choice("0123456789") for _ in range(mid_len))
        for d in "0123456789":
            cand = prefix + mid + d
            if luhn_ok(cand):
                return cand


def dash_bank(value: str) -> str:
    parts = [value[i : i + 4] for i in range(0, len(value), 4)]
    return "-".join(parts)


def space_bank(value: str) -> str:
    return dash_bank(value).replace("-", " ")


def make_phone(rng: random.Random) -> str:
    return rng.choice(PHONE_HEADS) + "".join(rng.choice("0123456789") for _ in range(8))


def fmt_phone(phone: str, style: str) -> str:
    if style == "dash":
        return f"{phone[:3]}-{phone[3:7]}-{phone[7:]}"
    if style == "space":
        return f"{phone[:3]} {phone[3:7]} {phone[7:]}"
    if style == "plus":
        return f"+86 {phone[:3]}-{phone[3:7]}-{phone[7:]}"
    if style == "fullwidth":
        return to_fullwidth(phone)
    return phone


def make_landline(rng: random.Random) -> str:
    kind = rng.choice(["010", "021", "0755"])
    if kind == "0755":
        return f"0755-{rng.randint(1000000, 9999999)}"
    return f"{kind}-{rng.randint(10000000, 99999999)}"


def make_email(rng: random.Random) -> str:
    return f"{rng.choice(EMAIL_USERS)}@{rng.choice(EMAIL_DOMAINS)}"


def make_ip(rng: random.Random) -> str:
    a = rng.choice((10, 172, 192))
    if a == 10:
        return f"10.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
    if a == 172:
        return f"172.{rng.randint(16, 31)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
    return f"192.168.{rng.randint(0, 255)}.{rng.randint(1, 254)}"


def make_date(rng: random.Random) -> str:
    y = rng.randint(2019, 2026)
    m = rng.randint(1, 12)
    d = rng.randint(1, 28)
    sep = rng.choice([".", "-", "/", "."])
    if rng.random() < 0.25:
        return f"{y}{sep}{m}{sep}{d}"
    return f"{y}{sep}{m:02d}{sep}{d:02d}"


def to_fullwidth(s: str) -> str:
    out = []
    for ch in s:
        o = ord(ch)
        if o == 0x20:
            out.append("\u3000")
        elif 0x21 <= o <= 0x7E:
            out.append(chr(o + 0xFEE0))
        else:
            out.append(ch)
    return "".join(out)


def _case(
    cid: str,
    path: str,
    text: str,
    entities: list[dict],
    *,
    family: str,
    mapped_rule: str | None = None,
    person_list: list[str] | None = None,
    scan_names: bool | None = None,
) -> dict:
    row: dict = {
        "id": cid,
        "path": path,
        "text": text,
        "family": family,
        "entities": entities,
    }
    if mapped_rule:
        row["mapped_rule"] = mapped_rule
    if person_list is not None:
        row["person_list"] = person_list
    if scan_names is not None:
        row["scan_names"] = scan_names
    return row


def _ent(typ: str, value: str) -> dict:
    return {"type": typ, "value": value}


def build_cases(seed: int = SEED) -> list[dict]:
    rng = random.Random(seed)
    cases: list[dict] = []
    n = 0

    def add(path, text, entities, family, **kw):
        nonlocal n
        n += 1
        cases.append(_case(f"{family}-{n:04d}", path, text, entities, family=family, **kw))

    # --- structured negatives ---
    for _ in range(80):
        d = make_date(rng)
        add("structured", d, [], "s-neg-date")
    for amount in ("2.5", "0.5", "1999.99", "3.14", "10.00", "1000.5"):
        for _ in range(8):
            add("structured", amount, [], "s-neg-decimal")
    for fml in ("=SUM(A1:A9)", "=H13*1.13", "=TODAY()"):
        add("structured", fml, [], "s-neg-formula")
    for _ in range(40):
        add("structured", f"{rng.choice(PEOPLE)}负责审批", [], "s-neg-prose")
    for _ in range(20):
        add("structured", rng.choice(DEPTS), [], "s-neg-dept", mapped_rule="company")
    for _ in range(20):
        add("structured", "v10.20.30.40", [], "s-neg-version-ip")
    for _ in range(40):
        add("structured", make_phone(rng), [], "s-phone-nocol")
    for _ in range(30):
        add(
            "structured",
            make_date(rng),
            [],
            "s-mapped-phone-date",
            mapped_rule="phone",
        )
    for _ in range(20):
        add(
            "structured",
            make_date(rng),
            [],
            "s-mapped-ver-date",
            mapped_rule="app_version",
        )

    # --- structured positives ---
    for _ in range(80):
        e = make_email(rng)
        add("structured", e, [_ent("email", e)], "s-email")
    for _ in range(60):
        ip = make_ip(rng)
        add("structured", ip, [_ent("ip", ip)], "s-ip")
    for _ in range(50):
        i = make_id(rng)
        add("structured", i, [_ent("id_card", i)], "s-id")
    for _ in range(30):
        i = make_id(rng)
        s = space_id(i)
        add("structured", f"身份证 {s}", [_ent("id_card", s)], "s-id-spaced")
    for _ in range(50):
        b = make_bank(rng)
        add("structured", b, [_ent("bank_card", b)], "s-bank")
    for _ in range(30):
        b = make_bank(rng)
        d = dash_bank(b)
        add("structured", f"卡号 {d}", [_ent("bank_card", d)], "s-bank-dash")
    for name in PEOPLE[:5]:
        add("structured", name, [_ent("name", name)], "s-name-heu")
        add(
            "structured",
            name,
            [_ent("name", name)],
            "s-name-list",
            person_list=PEOPLE,
        )
    for name in OUT_OF_LIST:
        add("structured", name, [], "s-name-out", person_list=["李娜"])
    for co in COMPANIES:
        add("structured", co, [_ent("company", co)], "s-col-company", mapped_rule="company")
    for _ in range(40):
        e = make_email(rng)
        add(
            "structured",
            f"联系邮箱 {e}，请审批。",
            [_ent("email", e)],
            "s-in-email",
        )
    for _ in range(30):
        ip = make_ip(rng)
        add(
            "structured",
            f"故障主机 IP 为 {ip}，值班。",
            [_ent("ip", ip)],
            "s-in-ip",
        )
    for _ in range(20):
        add("structured", "v1.2.3", [_ent("app_version", "v1.2.3")], "s-col-ver", mapped_rule="app_version")

    # --- document: the phone/date traps we just fixed ---
    for _ in range(100):
        d = make_date(rng)
        add("document", f"截止日期 {d} 请准时。", [], "d-neg-date")
    for _ in range(40):
        add("document", f"金额 {rng.choice(['2.5', '0.8', '3.14'])} 元已核。", [], "d-neg-amount")
    for _ in range(30):
        add("document", "请@全体成员 查看附件。", [], "d-neg-at")
    for _ in range(20):
        add("document", "见 https://corp.example/users/alice 说明。", [], "d-neg-url")
    for look in LOOKALIKE_IDS:
        add("document", f"格式参考 {look} ，勿改编号规则。", [], "d-neg-lookalike-eid")
    for _ in range(20):
        add("document", f"公式保护 =SUM(H13:H17) 不改，日期 {make_date(rng)}。", [], "d-neg-formula")

    # phones
    for style in ("compact", "dash", "space", "plus", "fullwidth"):
        for _ in range(30):
            raw = make_phone(rng)
            shown = fmt_phone(raw, style)
            add("document", f"手机 {shown} 已登记", [_ent("phone", shown)], "d-phone")

    # landline: 期望仍识别为电话（当前文档正则会漏）
    for _ in range(60):
        land = make_landline(rng)
        add("document", f"值班座机 {land} 勿外拨客户。", [_ent("phone", land)], "d-landline")

    # id / bank
    for _ in range(50):
        i = make_id(rng)
        s = space_id(i)
        add("document", f"身份证 {s} 已归档", [_ent("id_card", s)], "d-id-spaced")
    for _ in range(30):
        i = make_id(rng)
        add("document", f"证件号{i}与档案一致", [_ent("id_card", i)], "d-id-compact")
    for _ in range(40):
        b = make_bank(rng)
        d = dash_bank(b)
        add("document", f"卡号 {d} 已核", [_ent("bank_card", d)], "d-bank-dash")
    for _ in range(20):
        b = make_bank(rng)
        s = space_bank(b)
        add("document", f"卡号 {s} 已核", [_ent("bank_card", s)], "d-bank-space")

    # ip / version
    for _ in range(40):
        ip = make_ip(rng)
        add(
            "document",
            f"客户端 v10.20.30.40 发布，主机 {ip}",
            [_ent("ip", ip)],
            "d-ip-not-version",
        )
    for _ in range(25):
        add(
            "document",
            "客户端版本 v1.2.3 发布于内部环境。",
            [_ent("app_version", "v1.2.3")],
            "d-appver",
        )
    for _ in range(20):
        add(
            "document",
            f"客户端版本 v1.2.3 发布于 {make_date(rng)} 金额 2.5",
            [_ent("app_version", "v1.2.3")],
            "d-appver-date-amount",
        )

    # fullwidth email
    for _ in range(25):
        e = make_email(rng)
        fw = to_fullwidth(e)
        add("document", f"邮箱：{fw}", [_ent("email", fw)], "d-fw-email")

    # employee id true positives
    for _ in range(30):
        eid = f"EID-{rng.randint(1000, 9999)}"
        add("document", f"工号 {eid} 已入职", [_ent("employee_id", eid)], "d-eid")

    # names
    for name in PEOPLE:
        add(
            "document",
            f"申请人：{name} 已提交",
            [_ent("name", name)],
            "d-name-prefix",
            scan_names=True,
        )
        add(
            "document",
            f"申请人：{name} 已提交",
            [],
            "d-name-noscan",
            scan_names=False,
        )
        add(
            "document",
            f"经办{name}复核完毕",
            [_ent("name", name)],
            "d-name-list",
            scan_names=True,
            person_list=PEOPLE,
        )
    add("document", "选手张伟达获奖", [], "d-name-longer", scan_names=True, person_list=["张伟"])
    add(
        "document",
        "司马光华不是清单名",
        [],
        "d-name-3cut",
        scan_names=True,
        person_list=["司马光"],
    )
    add("document", "经办赵磊复核", [], "d-name-out", scan_names=True, person_list=["李娜"])

    # mixed audit-like sentences
    for _ in range(200):
        e = make_email(rng)
        p = fmt_phone(make_phone(rng), rng.choice(["compact", "dash", "space"]))
        ip = make_ip(rng)
        i = make_id(rng)
        d = make_date(rng)
        amt = rng.choice(["2.5", "13.08", "1000"])
        text = (
            f"截止日期 {d}，金额 {amt} 元。"
            f"联系 {e} 或手机 {p}，主机 {ip}。"
            f"证件 {space_id(i)}。客户端 v10.20.30.40 勿改。"
        )
        add(
            "document",
            text,
            [
                _ent("email", e),
                _ent("phone", p),
                _ent("ip", ip),
                _ent("id_card", space_id(i)),
            ],
            "d-mixed",
        )

    for _ in range(40):
        e = make_email(rng)
        b = dash_bank(make_bank(rng))
        name = rng.choice(PEOPLE)
        text = (
            f'JSON {{"email":"{e}","card":"{b}"}} HTML <p>联系人：{name}</p>'
        )
        ents = [_ent("email", e), _ent("bank_card", b), _ent("name", name)]
        add("document", text, ents, "d-json-html", scan_names=True, person_list=PEOPLE)

    for _ in range(30):
        e = make_email(rng)
        add(
            "document",
            f"真邮箱无空格联系人李娜邮箱{e}请批",
            [_ent("email", e), _ent("name", "李娜")],
            "d-glue",
            scan_names=True,
            person_list=PEOPLE,
        )

    return cases


def write_jsonl(cases: list[dict], path: Path = OUT_JSONL) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write("# generated by scripts/gen_stress_gold.py; labels = desired behavior\n")
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")


def build_excel(rng: random.Random) -> Workbook:
    wb = Workbook()
    notes = wb.active
    notes.title = "混乱备注"
    notes.append(["序号", "事项", "备注"])
    for c in notes[1]:
        c.font = Font(bold=True)
    for i in range(1, 401):
        kind = i % 10
        if kind == 0:
            body = f"截止日期 {make_date(rng)} 请准时，金额 2.5 元。"
        elif kind == 1:
            p = fmt_phone(make_phone(rng), "dash")
            body = f"手机 {p} 已登记"
        elif kind == 2:
            body = f"身份证 {space_id(make_id(rng))} 已归档"
        elif kind == 3:
            body = f"卡号 {dash_bank(make_bank(rng))} 已核"
        elif kind == 4:
            body = f"联系 {make_email(rng)}，主机 {make_ip(rng)}"
        elif kind == 5:
            body = f"值班座机 {make_landline(rng)} 勿外拨"
        elif kind == 6:
            body = f"格式参考 {rng.choice(LOOKALIKE_IDS)} ，客户端 v10.20.30.40"
        elif kind == 7:
            body = f"申请人：{rng.choice(PEOPLE)} 工号 EID-{rng.randint(1000,9999)}"
        elif kind == 8:
            body = f"JSON {{\"email\":\"{make_email(rng)}\"}}"
        else:
            body = f"{rng.choice(PEOPLE)}负责审批，部门{rng.choice(DEPTS)}"
        notes.append([i, "抽查", body])
    notes.column_dimensions["C"].width = 70

    phone_col = wb.create_sheet("电话列日期")
    phone_col.append(["电话", "说明"])
    for i in range(40):
        phone_col.append([make_date(rng), "列名会绑 phone，值却是日期"])
    for i in range(20):
        phone_col.append([make_phone(rng), "真手机"])

    return wb


def write_readme(path: Path, n_cases: int) -> None:
    path.write_text(
        f"""# 检测压力集（stress）

合成数据，seed={SEED}，jsonl {n_cases} 条。标签是期望行为。

| 文件 | 用途 |
|------|------|
| `../../benchmark/stress.jsonl` | detect_cell / detect_text 实体级评测 |
| `../../benchmark/stress-report.md` | 最近一次评分（误伤/漏检） |
| `notes.xlsx` | 400 行混乱备注 + 电话列塞日期 |
| `people.csv` | 人员清单 |

```bash
python3 scripts/gen_stress_gold.py
python3 -m maskit.detection.eval_gold benchmark/stress.jsonl --errors 40
```
""",
        encoding="utf-8",
    )


def main() -> None:
    rng = random.Random(SEED)
    cases = build_cases(SEED)
    write_jsonl(cases)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "people.csv").write_text("name\n" + "\n".join(PEOPLE) + "\n", encoding="utf-8")
    build_excel(rng).save(OUT_DIR / "notes.xlsx")
    write_readme(OUT_DIR / "README.md", len(cases))
    families: dict[str, int] = {}
    for c in cases:
        families[c["family"]] = families.get(c["family"], 0) + 1
    print(f"wrote {OUT_JSONL} ({len(cases)} cases)")
    print(f"wrote {OUT_DIR}")
    for name in sorted(families):
        print(f"  {name}: {families[name]}")


if __name__ == "__main__":
    main()
