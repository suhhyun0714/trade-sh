"""한빛식당(가상) 밥 예보 페이지 — 실습 C 안내서 「5. 감 검증」 · 「6. 페이지 규칙」.

workbench/day3/outputs/lunch_clean.csv 를 읽어 계산하고
workbench/day3/outputs/hanbit_lunch.html 한 장을 쓴다(같은 입력이면 같은 페이지).
지금 구역: 머리 · 영양사님 감 검증
실행: uv run python scripts/lunch_page.py
"""

import html
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "workbench/day3/outputs/lunch_clean.csv"
MEMO = ROOT / "labs/day3/lab-c/nutritionist_memo.md"
OUT = ROOT / "workbench/day3/outputs/hanbit_lunch.html"

GAP = 2.0  # 100명당 2명 — 사람이 정한 '차이 있음' 선
CHART_JS = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"


# ---------------------------------------------------------------- 데이터
def load_clean() -> pd.DataFrame:
    df = pd.read_csv(CLEAN, encoding="utf-8-sig", keep_default_na=False)
    df["행사"] = df["행사"].astype(str).str.strip()
    df["최고기온"] = pd.to_numeric(df["최고기온"].replace("", None), errors="coerce")
    df["per100"] = df["식수"] / df["출근예정"] * 100  # 출근 100명당 식수
    return df


def memo_beliefs() -> list[str]:
    """감 노트의 '제가 믿는 다섯 가지' 글(번호 순)."""
    text = MEMO.read_text(encoding="utf-8")
    found = re.findall(r"^\d\.\s+\*\*(.+?)\*\*\s*(.*)$", text, flags=re.M)
    return [f"{a} {b}".strip() for a, b in found][:5]


def group(sub: pd.DataFrame, label: str) -> dict:
    return {"label": label, "value": round(float(sub["per100"].mean()), 1),
            "raw": float(sub["per100"].mean()), "days": int(len(sub))}


def verdict(expected_higher: dict, expected_lower: dict) -> str:
    """믿음은 'expected_higher가 더 많다'. 2명 이상 그쪽이면 맞음, 반대로 2명 이상이면 틀림."""
    diff = expected_higher["raw"] - expected_lower["raw"]
    if diff >= GAP:
        return "맞음"
    if diff <= -GAP:
        return "틀림"
    return "반만"


def belief_check(df: pd.DataFrame) -> dict:
    base = df[(df["행사"] == "") & (df["월급날"] == 0)]  # 행사 없고 월급날 아닌 날
    beliefs = memo_beliefs()
    cards = []

    # 믿음 1 비 오는 날 > 맑은 날
    rain, sunny = group(base[base["날씨"] == "비"], "비 오는 날"), group(base[base["날씨"] == "맑음"], "맑은 날")
    cards.append({"no": 1, "kind": "pair", "groups": [rain, sunny], "badge": verdict(rain, sunny)})

    # 믿음 2 금요일 < 월–목
    fri = group(base[base["요일"] == "금"], "금요일")
    mon_thu = group(base[base["요일"].isin(["월", "화", "수", "목"])], "월–목")
    cards.append({"no": 2, "kind": "pair", "groups": [fri, mon_thu], "badge": verdict(mon_thu, fri)})

    # 믿음 3 메뉴별(높은 순) — 돈가스 1등이고 2등보다 2명 이상 많으면 맞음
    menus = [group(g, m) for m, g in base.groupby("메인메뉴")]
    menus.sort(key=lambda g: (-g["raw"], g["label"]))
    top, second = menus[0], menus[1]
    donkatsu = next(g for g in menus if g["label"] == "돈가스")
    if top["label"] == "돈가스" and top["raw"] - second["raw"] >= GAP:
        b3 = "맞음"
    elif top["raw"] - donkatsu["raw"] < GAP:  # 1등이 아니어도 1등과 2명 안쪽, 또는 1등이지만 2등과 2명 안쪽
        b3 = "반만"
    else:
        b3 = "틀림"
    rank = [g["label"] for g in menus].index("돈가스") + 1
    cards.append({"no": 3, "kind": "menu", "groups": menus, "badge": b3,
                  "note": f"돈가스는 {len(menus)}개 메뉴 중 {rank}등"})

    # 믿음 4 31도 이상 < 25도 이상 31도 미만
    t = base["최고기온"]
    hot = group(base[t >= 31], "31도 이상")
    warm = group(base[(t >= 25) & (t < 31)], "25–31도 미만")
    cards.append({"no": 4, "kind": "pair", "groups": [hot, warm], "badge": verdict(warm, hot),
                  "note": f"31도 이상인 날 {hot['days']}일"})

    # 믿음 5 월요일 < 화–목
    mon = group(base[base["요일"] == "월"], "월요일")
    tue_thu = group(base[base["요일"].isin(["화", "수", "목"])], "화–목")
    cards.append({"no": 5, "kind": "pair", "groups": [mon, tue_thu], "badge": verdict(tue_thu, mon)})

    for c in cards:
        c["text"] = beliefs[c["no"] - 1]

    # 메모에 없던 규칙: 월급날(모두) vs 보통 날
    pay = group(df[df["월급날"] == 1], "월급날")
    normal = group(base, "보통 날")
    d = pay["raw"] - normal["raw"]
    pay_label = "차이 있음 · 더 많음" if d >= GAP else ("차이 있음 · 더 적음" if d <= -GAP else "차이 작음")
    payday = {"kind": "pair", "groups": [pay, normal], "badge": pay_label,
              "text": "월급날에는 식수가 달라질까?"}

    return {"cards": cards, "payday": payday, "base_days": int(len(base))}


# ---------------------------------------------------------------- 페이지 조각
def esc(s) -> str:
    return html.escape(str(s))


BADGE_CLASS = {"맞음": "ok", "반만": "half", "틀림": "bad"}


def card_html(c: dict, cid: str, extra_badge_class: str | None = None) -> str:
    badge_cls = extra_badge_class or BADGE_CLASS[c["badge"]]
    title = f"믿음 {c['no']}" if "no" in c else "메모에 없던 규칙"
    if c["kind"] == "pair":
        a, b = c["groups"]
        nums = (f'<div class="nums">'
                f'<div><span class="n">{a["value"]:.1f}</span><span class="l">{esc(a["label"])} · {a["days"]}일</span></div>'
                f'<div class="vs">vs</div>'
                f'<div><span class="n">{b["value"]:.1f}</span><span class="l">{esc(b["label"])} · {b["days"]}일</span></div>'
                f'</div>')
        diff = a["value"] - b["value"]
        diff_line = f'<p class="diff">차이 {abs(diff):.1f}명 (출근 100명당)</p>'
        height = 96
    else:  # menu
        top = c["groups"][0]
        dk = next(g for g in c["groups"] if g["label"] == "돈가스")
        nums = (f'<div class="nums">'
                f'<div><span class="n">{dk["value"]:.1f}</span><span class="l">돈가스 · {dk["days"]}일</span></div>'
                f'<div class="vs">vs</div>'
                f'<div><span class="n">{top["value"]:.1f}</span><span class="l">1등 {esc(top["label"])} · {top["days"]}일</span></div>'
                f'</div>')
        diff_line = ""
        height = 26 * len(c["groups"]) + 20
    note = f'<p class="note">{esc(c["note"])}</p>' if c.get("note") else ""
    return (f'<article class="card">'
            f'<div class="card-top"><span class="tag">{title}</span>'
            f'<span class="badge {badge_cls}">{esc(c["badge"])}</span></div>'
            f'<p class="belief">{esc(c["text"])}</p>'
            f'{nums}{diff_line}{note}'
            f'<div class="chart" style="height:{height}px"><canvas id="{cid}" aria-label="{esc(title)} 막대 그래프"></canvas></div>'
            f'</article>')


def section_belief(bc: dict) -> str:
    cards = [card_html(c, f"belief{c['no']}") for c in bc["cards"]]
    cards.append(card_html(bc["payday"], "payday", extra_badge_class="half"))
    return (f'<section id="belief">'
            f'<h2>영양사님 감 검증</h2>'
            f'<p class="lead">출근 인원이 다른 날도 견줄 수 있게 <b>출근 100명당 식수</b>(식수 ÷ 출근예정 × 100, 날마다 구해 평균)로 비교했습니다. '
            f'행사가 없고 월급날이 아닌 날 {bc["base_days"]}일만 썼습니다. 100명당 {GAP:.0f}명 이상 차이 나면 \'차이 있음\'으로 봅니다.</p>'
            f'<div class="grid">{"".join(cards)}</div>'
            f'</section>')


def head_html(df: pd.DataFrame) -> str:
    start, end = df["날짜"].min(), df["날짜"].max()
    return (f'<header>'
            f'<h1>한빛식당 밥 예보</h1>'
            f'<p>(가상) 한빛정밀(주) 본사 구내식당 · 기록 기간 <span class="nw">{start}</span> – <span class="nw">{end}</span> · 만든 사람 총무팀 최 대리(가상)</p>'
            f'</header>')


CSS = """
:root{--bg:#f5f6f8;--card:#ffffff;--ink:#1f2328;--ink2:#57606a;--line:#e3e6ea;
--accent:#1f6feb;--warn:#d1495b;--gray:#8c959f;--grayfill:#c9ced4}
*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--bg);color:var(--ink);font-family:'Noto Sans KR',sans-serif;
font-size:16px;line-height:1.6;word-break:keep-all;overflow-wrap:break-word}
.wrap{max-width:1080px;margin:0 auto;padding:24px 16px 48px}
header h1{margin:0 0 4px;font-size:28px}
header p{margin:0;color:var(--ink2);font-size:15px}
section{margin-top:32px}
h2{font-size:22px;margin:0 0 8px}
.lead{color:var(--ink2);font-size:15px;margin:0 0 16px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;min-width:0}
.card-top{display:flex;justify-content:space-between;align-items:center;gap:8px}
.tag{font-size:14px;color:var(--ink2);font-weight:700}
.badge{font-size:14px;font-weight:700;padding:2px 12px;border-radius:999px;color:#fff;white-space:nowrap}
.badge.ok{background:var(--accent)}
.badge.half{background:var(--gray)}
.badge.bad{background:var(--warn)}
.belief{font-weight:700;margin:8px 0 12px}
.nums{display:flex;align-items:flex-end;gap:12px;flex-wrap:wrap}
.nums>div:not(.vs){display:flex;flex-direction:column}
.n{font-size:28px;font-weight:700;line-height:1.2;font-variant-numeric:tabular-nums}
.l{font-size:14px;color:var(--ink2)}
.vs{color:var(--ink2);font-size:14px;padding-bottom:4px}
.diff,.note{margin:8px 0 0;font-size:14px;color:var(--ink2)}
.chart{position:relative;margin-top:12px;width:100%}
.nw{white-space:nowrap}
"""

JS = """
const D = JSON.parse(document.getElementById('page-data').textContent);
const css = getComputedStyle(document.documentElement);
const C = n => css.getPropertyValue(n).trim();
Chart.defaults.font.family = "'Noto Sans KR', sans-serif";
Chart.defaults.font.size = 14;
Chart.defaults.color = C('--ink2');
function bars(id, groups, highlight){
  const el = document.getElementById(id); if(!el) return;
  new Chart(el, {type:'bar',
    data:{labels:groups.map(g=>g.label),
      datasets:[{data:groups.map(g=>g.value),
        backgroundColor:groups.map(g=>highlight(g)?C('--accent'):C('--grayfill')),
        borderRadius:4, borderSkipped:'start', barThickness:16}]},
    options:{indexAxis:'y', responsive:true, maintainAspectRatio:false, animation:false,
      plugins:{legend:{display:false},
        tooltip:{callbacks:{label:c=>`100명당 ${c.parsed.x.toFixed(1)}명 · ${groups[c.dataIndex].days}일`}}},
      scales:{x:{beginAtZero:true, max:100, grid:{color:C('--line')}, ticks:{maxTicksLimit:5}},
              y:{grid:{display:false}}}}});
}
D.belief.cards.forEach(c=>{
  if(c.kind==='menu') bars('belief'+c.no, c.groups, g=>g.label==='돈가스');
  else bars('belief'+c.no, c.groups, (g)=>g===c.groups[0]);
});
bars('payday', D.belief.payday.groups, g=>g===D.belief.payday.groups[0]);
"""


def build_page(df: pd.DataFrame, bc: dict) -> str:
    data = {"belief": {"cards": bc["cards"], "payday": bc["payday"]}}
    data_json = json.dumps(data, ensure_ascii=False, sort_keys=True).replace("</", "<\\/")
    sections = [section_belief(bc)]  # 다음 단계에서 구역을 더한다
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>한빛식당 밥 예보</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
{head_html(df)}
{''.join(sections)}
</div>
<script id="page-data" type="application/json">{data_json}</script>
<script src="{CHART_JS}"></script>
<script>{JS}</script>
</body>
</html>
"""


def main() -> None:
    df = load_clean()
    bc = belief_check(df)
    OUT.write_text(build_page(df, bc), encoding="utf-8")

    print(f"감 검증 — 기준 날(행사 없고 월급날 아님) {bc['base_days']}일, 출근 100명당 식수")
    for c in bc["cards"]:
        if c["kind"] == "pair":
            a, b = c["groups"]
            print(f"믿음 {c['no']}: {a['label']} {a['value']:.1f}({a['days']}일) vs {b['label']} {b['value']:.1f}({b['days']}일) "
                  f"→ {c['badge']}" + (f" · {c['note']}" if c.get("note") else ""))
        else:
            print(f"믿음 {c['no']}: " + " > ".join(f"{g['label']} {g['value']:.1f}({g['days']}일)" for g in c["groups"])
                  + f" → {c['badge']} · {c['note']}")
    a, b = bc["payday"]["groups"]
    print(f"월급날: {a['value']:.1f}({a['days']}일) vs 보통 날 {b['value']:.1f}({b['days']}일) → {bc['payday']['badge']}")
    print(f"[저장] {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
