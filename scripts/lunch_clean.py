"""한빛식당(가상) 점심 기록 정제 — 실습 C 안내서 「4. 정제 규칙」.

규칙 표: workbench/day3/outputs/lunch_rules.md (이 코드는 그 표 그대로, 그 순서대로)
원본 labs/day3/lab-c/hanbit_lunch_log.csv 는 읽기만 한다.
결과: workbench/day3/outputs/lunch_clean.csv · lunch_clean_log.md
실행: uv run python scripts/lunch_clean.py
"""

import math
import re
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "labs/day3/lab-c/hanbit_lunch_log.csv"
OUT_CSV = ROOT / "workbench/day3/outputs/lunch_clean.csv"
OUT_LOG = ROOT / "workbench/day3/outputs/lunch_clean_log.md"

# R6 '수기 집계' 줄 — 수강생 결정: 뺀다 (`뺀다` 또는 `×10 보정`)
MANUAL_DECISION = "뺀다"

COLS = ["날짜", "요일", "날씨", "최고기온", "메인메뉴", "행사", "월급날", "출근예정", "식수", "비고"]
WD_NAMES = ["월", "화", "수", "목", "금", "토", "일"]
WRITTEN_WD = {
    "월": 0, "화": 1, "수": 2, "목": 3, "금": 4,
    "월요일": 0, "화요일": 1, "수요일": 2, "목요일": 3, "금요일": 4,
    "Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4,
}
WEATHER_MAP = {
    "맑음": "맑음", "맑": "맑음", "sunny": "맑음",
    "흐림": "흐림", "구름많음": "흐림", "cloudy": "흐림",
    "비": "비", "rain": "비", "우천": "비", "소나기": "비", "흐리고 비": "비",
    "눈": "눈", "snow": "눈",
    "": "모름",
}
MENU_MAP = {"돈까스": "돈가스", "카레라이스": "카레", "제육": "제육볶음",
            "치킨마요덮밥": "치킨마요", "김치 찌개": "김치찌개"}
EVENT_MAP = {"외부손님": "외부 손님 방문", "전사교육": "전사 교육"}


def parse_date(s: str) -> date:
    s = s.strip()
    if m := re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s):
        y, mo, d = map(int, m.groups())
    elif m := re.fullmatch(r"(\d{1,2})월\s*(\d{1,2})일", s):
        mo, d = map(int, m.groups())
        y = 2025 if mo >= 10 else 2026
    else:
        raise ValueError(f"날짜를 읽을 수 없음: {s!r}")
    return date(y, mo, d)


def round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def main() -> None:
    df = pd.read_csv(SRC, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    n_start = len(df)
    log = []  # (순서, 번호, 할 일, 고친(뺀) 줄 수, 남은 줄 수)

    def record(order, rule, what, n):
        log.append((order, rule, what, n, len(df)))

    # 1. R1 날짜 → YYYY-MM-DD
    new_date = df["날짜"].map(lambda s: parse_date(s).isoformat())
    n = int((new_date != df["날짜"]).sum())
    df["날짜"] = new_date
    record(1, "R1", "날짜를 YYYY-MM-DD로", n)

    # 2. R2 요일을 날짜에서 다시 계산 (실제 요일과 달랐던 줄만 센다)
    actual = df["날짜"].map(lambda s: date.fromisoformat(s).weekday())
    written = df["요일"].str.strip().map(WRITTEN_WD)
    n = int((written != actual).sum())
    df["요일"] = actual.map(lambda i: WD_NAMES[i])
    record(2, "R2", "요일을 날짜에서 다시 계산(실제와 달랐던 줄)", n)

    # 3. R3 휴무 줄 빼기
    drop = df["비고"].str.strip() == "휴무"
    df = df[~drop].copy()
    record(3, "R3", "휴무 줄 빼기", int(drop.sum()))

    # 4. R4 같은 날짜 두 줄 → '재집계' 줄, 없으면 나중 줄
    df["_order"] = range(len(df))
    df["_re"] = df["비고"].str.contains("재집계", regex=False).astype(int)
    keep = (df.sort_values(["날짜", "_re", "_order"])
              .drop_duplicates("날짜", keep="last").index)
    n = len(df) - len(keep)
    df = df.loc[sorted(keep, key=lambda i: df.at[i, "_order"])].drop(columns=["_order", "_re"])
    record(4, "R4", "같은 날짜 두 줄 정리(재집계 줄, 없으면 나중 줄)", n)

    # 5. R5 식수 빈칸 빼기
    drop = df["식수"].str.strip() == ""
    df = df[~drop].copy()
    record(5, "R5", "식수 빈칸 줄 빼기", int(drop.sum()))

    # 6. R10 출근예정 빈칸 → 같은 요일 바로 앞 기록 4개의 median(반올림)
    df = df.sort_values("날짜", kind="stable")
    filled = []
    for idx in df.index[df["출근예정"].str.strip() == ""]:
        d, wd = df.at[idx, "날짜"], df.at[idx, "요일"]
        prev = df[(df["날짜"] < d) & (df["요일"] == wd) & (df["출근예정"].str.strip() != "")]
        last4 = prev.sort_values("날짜")["출근예정"].tail(4).astype(int)
        if len(last4) < 4:
            raise ValueError(f"{d}: 같은 요일 앞 기록이 4개보다 적음 — 확인 필요")
        value = round_half_up(last4.median())
        df.at[idx, "출근예정"] = str(value)
        filled.append((d, wd, list(last4), value))
    record(6, "R10", "출근예정 빈칸 채우기(같은 요일 앞 4개 median)", len(filled))

    # 7. R6 불가능한 식수 빼기 · '수기 집계' 줄은 수강생 결정대로
    att = df["출근예정"].astype(int)
    meal = df["식수"].astype(int)
    manual = df["비고"].str.strip() == "수기 집계"
    manual_rows = df[manual][["날짜", "출근예정", "식수", "비고"]].copy()
    if MANUAL_DECISION == "×10 보정":
        df.loc[manual, "식수"] = (meal[manual] * 10).astype(str)
        meal = df["식수"].astype(int)
        n_manual = int(manual.sum())
        bad = (~manual) & ((meal > att) | (meal < att * 0.2))
    elif MANUAL_DECISION == "뺀다":
        n_manual = int(manual.sum())
        bad = manual | (meal > att) | (meal < att * 0.2)
    else:
        raise ValueError("'수기 집계' 줄 결정이 없음 — 수강생에게 묻는다")
    other_rows = df[bad & ~manual][["날짜", "출근예정", "식수", "비고"]].copy()
    n_bad = int(bad.sum())
    df = df[~bad].copy()
    record(7, "R6", f"불가능한 식수 빼기('수기 집계' 줄: {MANUAL_DECISION})", n_bad)

    # 8. R7 날씨 네 가지로
    before = df["날씨"].str.strip()
    unknown = sorted(set(before) - set(WEATHER_MAP))
    if unknown:
        raise ValueError(f"표에 없는 날씨 표기: {unknown} — 확인 필요")
    df["날씨"] = before.map(WEATHER_MAP)
    record(8, "R7", "날씨를 맑음 · 흐림 · 비 · 눈(빈칸 → 모름)으로", int((df["날씨"] != before).sum()))

    # 9. R8 최고기온 단위 · 공백 떼기
    before = df["최고기온"]
    after = before.str.replace("℃", "", regex=False).str.replace("°C", "", regex=False).str.replace(" ", "", regex=False)
    bad_num = after[(after != "") & ~after.str.fullmatch(r"-?\d+(\.\d+)?")]
    if len(bad_num):
        raise ValueError(f"숫자가 아닌 최고기온: {list(bad_num)} — 확인 필요")
    df["최고기온"] = after
    record(9, "R8", "최고기온 단위 · 공백 떼기", int((after != before).sum()))

    # 10. R9 메뉴 · 행사 이름 통일 (따로 세어 더한다)
    n_menu = int(df["메인메뉴"].isin(MENU_MAP).sum())
    n_event = int(df["행사"].isin(EVENT_MAP).sum())
    df["메인메뉴"] = df["메인메뉴"].replace(MENU_MAP)
    df["행사"] = df["행사"].replace(EVENT_MAP)
    record(10, "R9", f"메뉴 · 행사 이름 통일(메뉴 {n_menu} + 행사 {n_event})", n_menu + n_event)

    # 마지막 정리
    df["월급날"] = df["월급날"].str.strip().map({"Y": 1, "": 0})
    if df["월급날"].isna().any():
        raise ValueError("월급날에 Y · 빈칸 말고 다른 값 — 확인 필요")
    df["월급날"] = df["월급날"].astype(int)
    df["출근예정"] = df["출근예정"].astype(int)
    df["식수"] = df["식수"].astype(int)
    df = df.sort_values("날짜", kind="stable")[COLS]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    # ---- 줄 수 기록 ----
    L = ["# 한빛식당(가상) 점심 기록 — 정제 기록", ""]
    L.append(f"- 원본 `labs/day3/lab-c/hanbit_lunch_log.csv` **{n_start}줄** → 깨끗한 표 `workbench/day3/outputs/lunch_clean.csv` **{len(df)}줄**")
    L.append(f"- 규칙 표: `workbench/day3/outputs/lunch_rules.md` · 코드: `scripts/lunch_clean.py`")
    L.append("- 세는 법: 그 규칙을 적용할 때 남아 있는 줄에서 센다. R2는 실제 요일과 달랐던 줄만, R9는 메뉴 + 행사.")
    L.append("")
    L.append("| 순서 | 규칙 | 할 일 | 고친(뺀) 줄 수 | 적용 뒤 남은 줄 수 |")
    L.append("|---:|---|---|---:|---:|")
    for order, rule, what, n, left in log:
        L.append(f"| {order} | {rule} | {what} | {n} | {left} |")
    L.append("")
    L.append("## R10 채운 출근예정")
    L.append("")
    L.append("| 날짜 | 요일 | 같은 요일 앞 기록 4개 | median 반올림 |")
    L.append("|---|---|---|---:|")
    for d, wd, vals, v in filled:
        L.append(f"| {d} | {wd} | {' · '.join(map(str, vals))} | {v} |")
    L.append("")
    L.append(f"## R6 뺀 줄 — '수기 집계' {n_manual}줄({MANUAL_DECISION}) · 그 밖 {len(other_rows)}줄")
    L.append("")
    L.append("| 날짜 | 출근예정 | 식수 | 비고 | 처리 |")
    L.append("|---|---:|---:|---|---|")
    for _, r in manual_rows.iterrows():
        L.append(f"| {r['날짜']} | {r['출근예정']} | {r['식수']} | {r['비고']} | 수강생 결정: {MANUAL_DECISION} |")
    for _, r in other_rows.iterrows():
        L.append(f"| {r['날짜']} | {r['출근예정']} | {r['식수']} | {r['비고'] or '(빈칸)'} | 출근예정보다 많거나 20% 미만 → 뺌 |")
    L.append("")
    OUT_LOG.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    print(f"[저장] {OUT_CSV.relative_to(ROOT)} · {OUT_LOG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
