"""
Mô phỏng Kịch bản 1 – FCFS (First Come First Served)
Sân bay Tân Sơn Nhất (VVTS) – Đường băng 25R / 25L
======================================================
Input : arrivals.csv  (ACID, Type, Wake, OccupyTime)
        departures.csv (ACID, Type, Wake, ReqTime, SID, Priority, Gate)
Output: ket_qua_kich_ban1.html
"""

import csv
import math
from pathlib import Path

# ─────────────────────────────────────────────────
# 1. HẰNG SỐ
# ─────────────────────────────────────────────────
T_ATC   = 15    # cấp phép cất cánh (thoại) – giây
T_PUSH  = 180   # pushback + khởi động – giây
T_TAXI_C = 10   # cấp phép lăn (thoại) – giây
T_LUP   = 30    # lineup – giây

ROT_DEP = {'L': 40, 'M': 45, 'H': 50, 'S': 50}
ROT_ARR = {'L': 50, 'M': 55, 'H': 60, 'S': 60}

# Thời gian taxi từ gate đến holding point (giây)
TAXI_TABLE = {
    22: 180, 21: 180,
    20: 240, 19: 240,
    18: 300, 17: 300,
    16: 360,
    15: 480, 14: 480, 13: 480, 12: 480,
    11: 540, 10: 540, 9: 540,
    8:  480,
    7:  540, 6: 540,
    5:  600,
    4:  660,
    3:  720,
    2:  780,
    1:  840,
}

# T_xfer (chuyển đường băng, chỉ dùng khi Transfer_to_DEP = True)
T_XFER = {'L': 86, 'M': 103, 'H': 114, 'S': 129}

# Phân cách DEP→DEP (giây)
SEP_DD = {
    ('S','H'): 120, ('S','M'): 180, ('S','L'): 240,
    ('H','M'): 120, ('H','L'): 180,
    ('M','L'): 180,
}
SEP_DD_DEFAULT = 90

# Phân cách ARR→ARR (giây)
SEP_AA = {
    ('S','H'): 180, ('S','M'): 240, ('S','L'): 240,
    ('H','M'): 180, ('H','L'): 180,
    ('M','L'): 120,
}
SEP_AA_DEFAULT = 120

# Phân cách ARR→DEP
SEP_AD = 30

# Phân cách DEP→ARR (không thuộc scenario nhưng cần xử lý)
SEP_DA = 60  # dự phòng – thực tế hiếm gặp


# ─────────────────────────────────────────────────
# 2. TIỆN ÍCH
# ─────────────────────────────────────────────────
BASE = 8 * 3600  # 08:00:00 = 0 giây

def to_sec(t_str: str) -> int:
    """'08:04:00' → giây từ 08:00:00"""
    t_str = t_str.strip()
    parts = t_str.split(':')
    h, m, s = int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0
    return h * 3600 + m * 60 + s - BASE

def fmt_sec(sec: int) -> str:
    """giây → 'HH:MM:SS' (UTC+7)"""
    total = sec + BASE
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def fmt_dur(sec: int) -> str:
    """giây → '2m30s' hoặc '45s'"""
    if sec < 0:
        return "0s"
    m = sec // 60
    s = sec % 60
    if m > 0:
        return f"{m}p{s:02d}s"
    return f"{s}s"

def separation(prev_type: str, prev_wake: str,
               curr_type: str, curr_wake: str) -> int:
    """Tính phân cách an toàn giữa hai sự kiện liên tiếp cùng đường băng."""
    if prev_type == 'DEP' and curr_type == 'DEP':
        return SEP_DD.get((prev_wake, curr_wake), SEP_DD_DEFAULT)
    if prev_type == 'ARR' and curr_type == 'ARR':
        return SEP_AA.get((prev_wake, curr_wake), SEP_AA_DEFAULT)
    if prev_type == 'ARR' and curr_type == 'DEP':
        return SEP_AD
    # DEP → ARR
    return SEP_DA


# ─────────────────────────────────────────────────
# 3. ĐỌC DỮ LIỆU
# ─────────────────────────────────────────────────
def load_arrivals(path: str) -> list:
    rows = []
    with open(path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for r in reader:
            acid  = r['ACID'].strip()
            wake  = r['Wake'].strip().upper()
            t_occ = to_sec(r['OccupyTime'].strip())
            rwy   = r.get('Rwy', '25R').strip() or '25R'  # mặc định 25R
            rows.append({
                'event_type': 'ARR',
                'acid': acid,
                'ac_type': r['Type'].strip(),
                'wake': wake,
                'ready_time': t_occ,
                'rwy': rwy,
                'transfer_to_dep': False,
                'rot': ROT_ARR[wake],
            })
    return rows

def load_departures(path: str) -> list:
    rows = []
    with open(path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for r in reader:
            acid  = r['ACID'].strip()
            wake  = r['Wake'].strip().upper()
            t_req = to_sec(r['ReqTime'].strip() if r['ReqTime'].strip().count(':') == 2
                           else r['ReqTime'].strip() + ':00')
            gate  = int(r['Gate'].strip())
            rwy   = r.get('Rwy', '25L').strip() or '25L'  # mặc định 25L
            trans = r.get('Transfer_to_DEP', 'FALSE').strip().upper() == 'TRUE'

            taxi  = TAXI_TABLE.get(gate, 600)
            t_hp  = t_req + T_ATC + T_PUSH + taxi + T_TAXI_C
            ready = t_hp + T_LUP

            rows.append({
                'event_type': 'DEP',
                'acid': acid,
                'ac_type': r['Type'].strip(),
                'wake': wake,
                'req_time': t_req,
                'gate': gate,
                'sid': r.get('SID', '').strip(),
                'priority': r.get('Priority', 'Normal').strip(),
                'rwy': rwy,
                'transfer_to_dep': trans,
                't_hp': t_hp,
                'ready_time': ready,
                'rot': ROT_DEP[wake],
                'taxi_time': taxi,
            })
    return rows


# ─────────────────────────────────────────────────
# 4. THUẬT TOÁN FCFS
# ─────────────────────────────────────────────────
def run_fcfs(arrivals: list, departures: list) -> list:
    # Gộp và sắp xếp theo ready_time (FCFS thuần)
    all_events = arrivals + departures
    all_events.sort(key=lambda e: (e['ready_time'], 0 if e['event_type'] == 'ARR' else 1))

    # Trạng thái mỗi đường băng
    rwy_state = {
        '25R': {'free': 0, 'last_type': None, 'last_wake': None},
        '25L': {'free': 0, 'last_type': None, 'last_wake': None},
    }

    results = []
    prev_actual = {}   # rwy → T_actual của sự kiện trước (cho tính GAP)

    for ev in all_events:
        rwy = ev['rwy']
        st  = rwy_state[rwy]

        ready  = ev['ready_time']
        rot    = ev['rot']

        if st['last_type'] is None:
            # Sự kiện đầu tiên trên đường băng này
            t_actual = ready
        else:
            sep   = separation(st['last_type'], st['last_wake'],
                                ev['event_type'], ev['wake'])
            safe  = st['free'] + sep
            t_actual = max(ready, safe)

        wait = t_actual - ready
        gap  = t_actual - prev_actual.get(rwy, t_actual)  # GAP so với sự kiện trước cùng rwy

        # Lưu kết quả
        record = dict(ev)
        record['t_actual']  = t_actual
        record['wait']      = wait
        record['gap']       = gap if st['last_type'] is not None else 0
        record['t_rwy_end'] = t_actual + rot
        results.append(record)

        # Cập nhật trạng thái đường băng
        st['free']      = t_actual + rot
        st['last_type'] = ev['event_type']
        st['last_wake'] = ev['wake']
        prev_actual[rwy] = t_actual

    return results


# ─────────────────────────────────────────────────
# 5. XUẤT HTML
# ─────────────────────────────────────────────────
WAKE_LABEL = {'S': 'SUPER', 'H': 'HEAVY', 'M': 'MEDIUM', 'L': 'LIGHT'}

def build_html(results: list) -> str:
    # ── KPIs ──
    dep_results = [r for r in results if r['event_type'] == 'DEP']
    arr_results = [r for r in results if r['event_type'] == 'ARR']

    avg_wait_dep = sum(r['wait'] for r in dep_results) / len(dep_results) if dep_results else 0
    avg_wait_arr = sum(r['wait'] for r in arr_results) / len(arr_results) if arr_results else 0
    max_wait     = max((r['wait'] for r in results), default=0)
    total_events = len(results)

    # ── Throughput per runway ──
    rwy_counts = {}
    for r in results:
        rwy_counts[r['rwy']] = rwy_counts.get(r['rwy'], 0) + 1

    # ── Rows ──
    rows_html = ''
    for i, r in enumerate(results, 1):
        ev_class = 'dep' if r['event_type'] == 'DEP' else 'arr'
        wake_full = WAKE_LABEL.get(r['wake'], r['wake'])

        wait_class = ''
        if r['wait'] > 600:
            wait_class = 'wait-high'
        elif r['wait'] > 300:
            wait_class = 'wait-med'

        dep_extra = ''
        if r['event_type'] == 'DEP':
            dep_extra = f"""
                <td>{r.get('gate','–')}</td>
                <td>{fmt_sec(r.get('req_time', r['ready_time'] - T_LUP))}</td>
                <td>{fmt_sec(r.get('t_hp', 0))}</td>
                <td>{r.get('sid','–')}</td>
            """
        else:
            dep_extra = '<td colspan="4" class="na-cell">— hạ cánh —</td>'

        rows_html += f"""
        <tr class="{ev_class}">
            <td class="seq-col">{i}</td>
            <td><span class="badge {ev_class}">{r['event_type']}</span></td>
            <td class="acid-col">{r['acid']}</td>
            <td>{r['ac_type']}</td>
            <td><span class="wake-badge wake-{r['wake'].lower()}">{wake_full}</span></td>
            <td class="rwy-col">{r['rwy']}</td>
            <td>{fmt_sec(r['ready_time'])}</td>
            {dep_extra}
            <td class="highlight">{fmt_sec(r['t_actual'])}</td>
            <td class="{wait_class}">{fmt_dur(r['wait'])}</td>
            <td>{fmt_dur(r['gap'])}</td>
            <td>{fmt_sec(r['t_rwy_end'])}</td>
        </tr>"""

    # ── KPI cards ──
    kpi_html = f"""
        <div class="kpi-card">
            <div class="kpi-value">{total_events}</div>
            <div class="kpi-label">Tổng sự kiện</div>
        </div>
        <div class="kpi-card arr-card">
            <div class="kpi-value">{len(arr_results)}</div>
            <div class="kpi-label">Chuyến hạ cánh (ARR)</div>
        </div>
        <div class="kpi-card dep-card">
            <div class="kpi-value">{len(dep_results)}</div>
            <div class="kpi-label">Chuyến cất cánh (DEP)</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-value">{fmt_dur(int(avg_wait_dep))}</div>
            <div class="kpi-label">Chờ TB (DEP)</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-value">{fmt_dur(int(avg_wait_arr))}</div>
            <div class="kpi-label">Chờ TB (ARR)</div>
        </div>
        <div class="kpi-card warn-card">
            <div class="kpi-value">{fmt_dur(max_wait)}</div>
            <div class="kpi-label">Chờ tối đa</div>
        </div>
    """

    # ── Throughput ──
    tp_html = ''.join(
        f'<div class="tp-item"><span class="tp-rwy">{k}</span> : <strong>{v}</strong> chuyến</div>'
        for k, v in sorted(rwy_counts.items())
    )

    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mô phỏng Kịch bản 1 – FCFS | VVTS 25R/25L</title>
<style>
  :root {{
    --blue-dark:  #0d2137;
    --blue-mid:   #1a4a7a;
    --blue-light: #2e7bcf;
    --dep-bg:     #e8f4fd;
    --dep-border: #2e7bcf;
    --arr-bg:     #edfbf0;
    --arr-border: #28a745;
    --yellow:     #ffc107;
    --red:        #dc3545;
    --grey-light: #f5f7fa;
    --grey-mid:   #dde3ea;
    --text-dark:  #1a1a2e;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: #0b1a2b;
    color: #e0eaf5;
    min-height: 100vh;
  }}

  /* ── Header ── */
  header {{
    background: linear-gradient(135deg, #0d2137 0%, #1a4a7a 100%);
    padding: 28px 40px 22px;
    border-bottom: 3px solid #2e7bcf;
    display: flex; align-items: center; gap: 20px;
  }}
  .logo-circle {{
    width: 56px; height: 56px; border-radius: 50%;
    background: #2e7bcf;
    display: flex; align-items: center; justify-content: center;
    font-size: 26px; flex-shrink: 0;
  }}
  header h1 {{ font-size: 1.5rem; font-weight: 700; }}
  header p  {{ font-size: 0.85rem; color: #8ab4d8; margin-top: 4px; }}

  /* ── Main wrapper ── */
  main {{ padding: 28px 40px; }}

  /* ── Section titles ── */
  .section-title {{
    font-size: 1rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: .08em; color: #8ab4d8;
    margin-bottom: 14px; margin-top: 28px;
    display: flex; align-items: center; gap: 8px;
  }}
  .section-title::before {{
    content: ''; display: inline-block;
    width: 4px; height: 18px; border-radius: 2px;
    background: #2e7bcf;
  }}

  /* ── KPI cards ── */
  .kpi-grid {{
    display: flex; flex-wrap: wrap; gap: 14px;
    margin-bottom: 8px;
  }}
  .kpi-card {{
    background: #12263f;
    border: 1px solid #1e3f62;
    border-radius: 10px;
    padding: 16px 22px;
    min-width: 140px; flex: 1;
    text-align: center;
    border-top: 4px solid #2e7bcf;
  }}
  .dep-card  {{ border-top-color: #2e7bcf; }}
  .arr-card  {{ border-top-color: #28a745; }}
  .warn-card {{ border-top-color: #ffc107; }}
  .kpi-value {{
    font-size: 1.9rem; font-weight: 800; color: #fff;
    line-height: 1.1;
  }}
  .kpi-label {{ font-size: 0.78rem; color: #7a9bb8; margin-top: 5px; }}

  /* ── Throughput ── */
  .tp-bar {{
    display: flex; gap: 16px;
    background: #12263f; border: 1px solid #1e3f62;
    border-radius: 8px; padding: 12px 20px;
    margin-bottom: 8px;
  }}
  .tp-item {{ font-size: 0.9rem; }}
  .tp-rwy  {{ color: #2e7bcf; font-weight: 700; }}

  /* ── Legend ── */
  .legend {{
    display: flex; gap: 20px; flex-wrap: wrap;
    font-size: 0.82rem; margin-bottom: 16px;
  }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; }}
  .legend-dot  {{ width: 12px; height: 12px; border-radius: 3px; }}

  /* ── Table wrapper ── */
  .table-wrapper {{
    overflow-x: auto;
    border-radius: 10px;
    border: 1px solid #1e3f62;
    box-shadow: 0 4px 24px rgba(0,0,0,.4);
  }}
  table {{
    width: 100%; border-collapse: collapse;
    font-size: 0.84rem; min-width: 1000px;
  }}
  thead tr {{
    background: #0d2137;
    color: #8ab4d8;
    font-size: 0.75rem; text-transform: uppercase; letter-spacing: .06em;
  }}
  thead th {{
    padding: 11px 12px; text-align: center;
    border-bottom: 2px solid #2e7bcf;
    white-space: nowrap;
  }}
  tbody tr {{ border-bottom: 1px solid #1a3251; }}
  tbody tr:hover {{ background: #162d48 !important; }}

  tbody tr.dep {{ background: #0e2236; }}
  tbody tr.arr {{ background: #0b1f16; }}

  td {{ padding: 9px 12px; text-align: center; vertical-align: middle; }}

  .seq-col  {{ color: #555e70; font-size: 0.78rem; width: 36px; }}
  .acid-col {{ font-weight: 700; font-family: monospace; font-size: 0.9rem; color: #e8f4fd; }}
  .rwy-col  {{ font-weight: 700; color: #f0c040; }}
  .highlight {{ font-weight: 800; color: #5bc8ff; font-size: 0.95rem; }}

  .na-cell  {{ color: #3a5570; font-style: italic; font-size: 0.8rem; }}

  .wait-high {{ color: #ff6b6b; font-weight: 700; }}
  .wait-med  {{ color: #ffc107; font-weight: 600; }}

  /* ── Badges ── */
  .badge {{
    display: inline-block; padding: 2px 9px;
    border-radius: 4px; font-weight: 700; font-size: 0.78rem;
    letter-spacing: .04em;
  }}
  .badge.dep {{ background: #1a4a7a; color: #7bc8ff; border: 1px solid #2e7bcf; }}
  .badge.arr {{ background: #0d3320; color: #5fe89a; border: 1px solid #28a745; }}

  .wake-badge {{
    display: inline-block; padding: 1px 7px;
    border-radius: 3px; font-size: 0.74rem; font-weight: 600;
  }}
  .wake-h {{ background: #4a1a1a; color: #ff8888; }}
  .wake-m {{ background: #1a3a4a; color: #88d0ff; }}
  .wake-l {{ background: #1a3a1a; color: #88e888; }}
  .wake-s {{ background: #3a1a4a; color: #cc88ff; }}

  /* ── Footer ── */
  footer {{
    text-align: center; font-size: 0.75rem; color: #3a5570;
    padding: 20px 40px 28px;
  }}
</style>
</head>
<body>

<header>
  <div class="logo-circle">✈</div>
  <div>
    <h1>Mô phỏng Kịch bản 1 – FCFS</h1>
    <p>Sân bay Quốc tế Tân Sơn Nhất (VVTS) &nbsp;|&nbsp; Đường băng 25R / 25L &nbsp;|&nbsp;
       Thuật toán: <strong>First Come First Served</strong></p>
  </div>
</header>

<main>

  <div class="section-title">Tổng quan</div>
  <div class="kpi-grid">
    {kpi_html}
  </div>

  <div class="section-title" style="margin-top:18px">Thông lượng theo đường băng</div>
  <div class="tp-bar">{tp_html}</div>

  <div class="section-title">Kết quả chi tiết</div>
  <div class="legend">
    <div class="legend-item">
      <div class="legend-dot" style="background:#1a4a7a;border:1px solid #2e7bcf"></div> DEP – Cất cánh
    </div>
    <div class="legend-item">
      <div class="legend-dot" style="background:#0d3320;border:1px solid #28a745"></div> ARR – Hạ cánh
    </div>
    <div class="legend-item">
      <div class="legend-dot" style="background:#ff6b6b"></div> Chờ &gt; 10 phút
    </div>
    <div class="legend-item">
      <div class="legend-dot" style="background:#ffc107"></div> Chờ &gt; 5 phút
    </div>
  </div>

  <div class="table-wrapper">
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Loại</th>
          <th>Chuyến bay</th>
          <th>Tàu bay</th>
          <th>Wake</th>
          <th>Đường băng</th>
          <th>Ready Time</th>
          <th>Gate</th>
          <th>T_req</th>
          <th>T_HP (DEP)</th>
          <th>SID</th>
          <th>T_actual ✈</th>
          <th>Chờ</th>
          <th>GAP</th>
          <th>RWY Free</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </div>

</main>

<footer>
  Kịch bản 1 – FCFS &nbsp;|&nbsp; Phân cách theo tiêu chuẩn Wake Turbulence Việt Nam &nbsp;|&nbsp;
  Thời gian tính từ mốc 08:00:00 UTC+7
</footer>

</body>
</html>"""
    return html


# ─────────────────────────────────────────────────
# 6. MAIN
# ─────────────────────────────────────────────────
if __name__ == '__main__':
    BASE_DIR = Path(__file__).parent

    arr_file = BASE_DIR / 'arrivals.csv'
    dep_file = BASE_DIR / 'departures.csv'
    out_file = BASE_DIR / 'ket_qua_kich_ban1.html'

    arrivals   = load_arrivals(str(arr_file))
    departures = load_departures(str(dep_file))

    results = run_fcfs(arrivals, departures)

    html = build_html(results)
    out_file.write_text(html, encoding='utf-8')
    print(f"✅ Xong! Kết quả đã lưu tại: {out_file}")
    print(f"   Tổng sự kiện : {len(results)}")
    print(f"   ARR          : {sum(1 for r in results if r['event_type']=='ARR')}")
    print(f"   DEP          : {sum(1 for r in results if r['event_type']=='DEP')}")