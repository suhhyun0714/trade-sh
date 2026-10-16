"""한빛식당(가상) 점심 기록 데이터 진단 — 실습 C 안내서 「3. 데이터 진단」.

원본 labs/day3/lab-c/hanbit_lunch_log.csv 는 읽기만 하고,
진단 결과를 workbench/day3/outputs/lunch_quality.md 에 쓴다.
실행: uv run python scripts/lunch_quality.py
"""

import re
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "labs/day3/lab-c/hanbit_lunch_log.csv"
OUT = ROOT / "workbench/day3/outputs/lunch_quality.md"

WEEKDAY = {  # 적힌 요일 → 0(월)–4(금)
    "월": 0, "화": 1, "수": 2, "목": 3, "금": 4,
    "월요일": 0, "화요일": 1, "수요일": 2, "목요일": 3, "금요일": 4,
    "Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4,
}
WEATHER_OK = {"맑음", "흐림", "비", "눈"}
MENU_VARIANTS = ["돈까스", "카레라이스", "제육", "치킨마요덮밥", "김치 찌개"]
EVENT_VARIANTS = ["외부손님", "전사교육"]


def parse_date(s: str):
    """진단용 날짜 해석. (date, 형식 이름) — 못 읽으면 (None, '알 수 없음')."""
    s = s.strip()
    if m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s):
        fmt = "YYYY-MM-DD"
        y, mo, d = map(int, m.groups())
    elif m := re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", s):
        fmt = "YYYY/MM/DD"
        y, mo, d = map(int, m.groups())
    elif m := re.fullmatch(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", s):
        fmt = "YYYY.M.D"
        y, mo, d = map(int, m.groups())
    elif m := re.fullmatch(r"(\d{1,2})월\s*(\d{1,2})일", s):
        fmt = "M월 D일(연도 없음)"
        mo, d = map(int, m.groups())
        y = 2025 if mo >= 10 else 2026
    else:
        return None, "알 수 없음"
    try:
        return date(y, mo, d), fmt
    except ValueError:
        return None, "알 수 없음"


def to_int(s: str):
    s = s.strip()
    return int(s) if re.fullmatch(r"-?\d+", s) else None


def examples(sub: pd.DataFrame, col: str, n: int = 2) -> str:
    """예시 n개 — 원본 글자 그대로 `날짜 → 값`."""
    out = []
    for _, r in sub.head(n).iterrows():
        v = r[col]
        shown = "(빈칸)" if v == "" else v
        out.append(f"`{r['날짜']}`" if col == "날짜" else f"`{r['날짜']}` → `{shown}`")
    return " · ".join(out) if out else "-"


def counts_text(series: pd.Series) -> str:
    vc = series.replace("", "(빈칸)").value_counts()
    return ", ".join(f"`{k}` {v}" for k, v in vc.items())


def main() -> None:
    df = pd.read_csv(SRC, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    n_rows = len(df)

    parsed = df["날짜"].map(parse_date)
    df["_date"] = parsed.map(lambda t: t[0])
    df["_fmt"] = parsed.map(lambda t: t[1])
    df["_att"] = df["출근예정"].map(to_int)
    df["_meal"] = df["식수"].map(to_int)
    holiday = df["비고"].str.strip() == "휴무"
    work = df[~holiday]

    valid_dates = df["_date"].dropna()
    unparsed = df[df["_date"].isna()]

    rows = []  # (종류, 줄 수, 예시, 덧붙임)

    # 날짜 형식 섞임
    bad_date = df[df["_fmt"] != "YYYY-MM-DD"]
    rows.append(("날짜 형식 섞임", len(bad_date), examples(bad_date, "날짜"),
                 "형식별: " + counts_text(bad_date["_fmt"])))

    # 요일 표기 섞임
    bad_wd = df[~df["요일"].isin(["월", "화", "수", "목", "금"])]
    rows.append(("요일 표기 섞임", len(bad_wd), examples(bad_wd, "요일"),
                 "표기별: " + counts_text(bad_wd["요일"])))

    # 적힌 요일 ≠ 실제 요일
    def wd_mismatch(r):
        written = WEEKDAY.get(r["요일"].strip())
        return r["_date"] is not None and written is not None and written != r["_date"].weekday()

    mism = df[df.apply(wd_mismatch, axis=1)]
    rows.append(("(요일) 적힌 요일 ≠ 날짜의 실제 요일", len(mism), examples(mism, "요일"),
                 "표기만 다른 줄(`월요일` · `Mon` 등)은 세지 않음"))

    # 같은 날짜가 두 줄
    dated = df[df["_date"].notna()]
    dup = dated[dated.duplicated("_date", keep=False)]
    dup_dates = dup["_date"].nunique()
    body_cols = [c for c in df.columns if not c.startswith("_") and c != "날짜"]
    exact = sum(1 for _, g in dup.groupby("_date") if len(g[body_cols].drop_duplicates()) == 1)
    rows.append(("같은 날짜가 두 줄", len(dup), examples(dup, "식수"),
                 f"날짜 {dup_dates}개 — 완전히 같은 줄 {exact}개 날짜 · 내용이 다른 줄 {dup_dates - exact}개 날짜"))

    # 휴무 줄
    hol = df[holiday]
    rows.append(("휴무 줄", len(hol), examples(hol, "비고"), "출근예정 · 식수 0"))

    # 식수 빈칸
    meal_blank = df[df["식수"].str.strip() == ""]
    rows.append(("식수 빈칸", len(meal_blank), examples(meal_blank, "식수"),
                 "비고: " + counts_text(meal_blank["비고"])))

    # 불가능해 보이는 식수 (휴무 아닌 줄, 출근예정 · 식수 둘 다 있는 줄)
    both = work[work["_att"].notna() & work["_meal"].notna()]
    too_many = both[both["_meal"] > both["_att"]]
    too_few = both[both["_meal"] < both["_att"] * 0.2]
    impossible = pd.concat([too_many, too_few]).sort_index()
    rows.append(("불가능해 보이는 식수", len(impossible), examples(impossible, "식수"),
                 f"출근예정보다 많음 {len(too_many)} · 출근예정의 20% 미만 {len(too_few)}"))

    # 날씨 표기 섞임 (휴무 줄 제외)
    bad_w = work[~work["날씨"].isin(WEATHER_OK)]
    rows.append(("날씨 표기 섞임", len(bad_w), examples(bad_w, "날씨"),
                 "값별: " + counts_text(bad_w["날씨"])))

    # 최고기온 단위 · 빈칸 (휴무 줄 제외)
    t = work["최고기온"]
    t_c1 = work[t.str.contains("℃", regex=False)]
    t_c2 = work[t.str.contains("°C", regex=False)]
    t_blank = work[t.str.strip() == ""]
    rows.append(("최고기온 단위 `℃`", len(t_c1), examples(t_c1, "최고기온"), ""))
    rows.append(("최고기온 단위 `°C`", len(t_c2), examples(t_c2, "최고기온"), "숫자와 `°C` 사이 공백 포함"))
    rows.append(("최고기온 빈칸", len(t_blank), examples(t_blank, "최고기온"), "휴무 줄 제외"))

    # 메뉴 · 행사 이름 섞임
    bad_menu = df[df["메인메뉴"].isin(MENU_VARIANTS)]
    bad_event = df[df["행사"].isin(EVENT_VARIANTS)]
    rows.append(("메뉴 이름 섞임", len(bad_menu), examples(bad_menu, "메인메뉴"),
                 "이름별: " + counts_text(bad_menu["메인메뉴"])))
    rows.append(("행사 이름 섞임", len(bad_event), examples(bad_event, "행사"),
                 "이름별: " + counts_text(bad_event["행사"])))

    # 출근예정 빈칸
    att_blank = df[df["출근예정"].str.strip() == ""]
    rows.append(("출근예정 빈칸", len(att_blank), examples(att_blank, "출근예정"), ""))

    # 비고
    memo = df[df["비고"].str.strip() != ""]["비고"].value_counts()

    # ---- 보고서 ----
    L = []
    L.append("# 한빛식당(가상) 점심 기록 — 데이터 진단")
    L.append("")
    L.append(f"- 원본: `labs/day3/lab-c/hanbit_lunch_log.csv` (읽기만 함, 고치지 않음)")
    L.append(f"- 만든 코드: `scripts/lunch_quality.py` — 숫자는 모두 이 코드가 센 값")
    L.append("")
    L.append("## 1. 줄 수 · 열 이름 · 날짜 범위")
    L.append("")
    L.append("| 항목 | 값 |")
    L.append("|---|---|")
    L.append(f"| 줄 수(머리 줄 제외) | {n_rows} |")
    L.append(f"| 열 이름({len(df.columns) - 4}개) | " + " · ".join(f"`{c}`" for c in df.columns if not c.startswith("_")) + " |")
    L.append(f"| 날짜 범위 | {min(valid_dates)} – {max(valid_dates)} |")
    L.append(f"| 날짜를 못 읽은 줄 | {len(unparsed)}" + (" (확인 필요)" if len(unparsed) else "") + " |")
    L.append("")
    L.append("날짜 범위는 진단용 해석 기준(연도 없는 `M월 D일`은 10–12월 → 2025년, 1–9월 → 2026년)입니다.")
    L.append("")
    L.append("## 2. 엉망인 곳 — 종류별")
    L.append("")
    L.append("예시는 원본 글자 그대로 `날짜` → `그 칸의 값`입니다.")
    L.append("")
    L.append("| 종류 | 줄 수 | 예시 2개(원본 그대로) | 덧붙임 |")
    L.append("|---|---:|---|---|")
    for kind, n, ex, note in rows:
        L.append(f"| {kind} | {n} | {ex} | {note} |")
    L.append("")
    L.append("## 3. 비고 열에 나오는 글")
    L.append("")
    L.append("| 비고 | 줄 수 |")
    L.append("|---|---:|")
    for k, v in memo.items():
        L.append(f"| {k} | {v} |")
    L.append("")
    L.append("## 4. 사람이 정해야 할 줄")
    L.append("")
    L.append("식수가 출근예정보다 많거나 출근예정의 20% 미만인 줄입니다. 지울지 고칠지는 다음 단계(정제 R6)에서 사람이 정합니다.")
    L.append("")
    L.append("| 날짜 | 출근예정 | 식수 | 비고 | 왜 이상한가 |")
    L.append("|---|---:|---:|---|---|")
    for idx, r in impossible.iterrows():
        why = "출근예정보다 많음" if idx in too_many.index else "출근예정의 20% 미만"
        L.append(f"| {r['날짜']} | {r['출근예정']} | {r['식수']} | {r['비고'] or '(빈칸)'} | {why} |")
    L.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    print(f"\n[저장] {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
