"""
Mô phỏng Kịch bản 2 – ACDM + DCL/PDC + DMAN
Sân bay Tân Sơn Nhất (VVTS) – Đường băng 25R / 25L
=====================================================
Input : arrivals.csv  (ACID, Type, Wake, OccupyTime)
        departures.csv (ACID, Type, Wake, ReqTime, SID, Priority, Gate)
Output: ket_qua_kich_ban2.html
"""

import csv
from pathlib import Path

# ─────────────────────────────────────────────────
# 1. HẰNG SỐ KB2 (khác KB1)
# ─────────────────────────────────────────────────
T_DCL       = 2     # cấp phép cất cánh datalink – giây  (KB1: 15s)
T_PUSH      = 180   # pushback + khởi động – giây (giữ nguyên)
T_TAXI_C_DCL = 2    # cấp phép lăn datalink – giây  (KB1: 10s)
T_LUP       = 30    # lineup – giây (giữ nguyên)

# Bonus ưu tiên DMAN
DMAN_BONUS  = {'Normal': 0, 'VIP': -120, 'Medical': -180}

ROT_DEP = {'L': 40, 'M': 45, 'H': 50, 'S': 50}
ROT_ARR = {'L': 50, 'M': 55, 'H': 60, 'S': 60}

TAXI_TABLE = {
    22: 180, 21: 180,
    20: 240, 19: 240,
    18: 300, 17: 300,
    16: 360,
    15: 480, 14: 480, 13: 480, 12: 480,
    11: 540, 10: 540,  9: 540,
     8: 480,
     7: 540,  6: 540,
     5: 600,
     4: 660,
     3: 720,
     2: 780,
     1: 840,
}

T_XFER = {'L': 86, 'M': 103, 'H': 114, 'S': 129}

# ── Hằng số mở rộng (chưa dùng trong mô hình KB2, dùng cho mở rộng sau) ──
T_CROSS    = 26                               # băng qua một đường băng (giây) – mọi loại tàu
T_TAXI_DAI = {'L': 280, 'M': 320, 'H': 350, 'S': 380}  # vacated → NS (giây)

# Phân cách KB2 – DEP→DEP (giảm ~8% so KB1)
SEP_DD_KB2 = {
    ('S','H'): 110, ('S','M'): 165, ('S','L'): 220,
    ('H','M'): 110, ('H','L'): 165,
    ('M','L'): 165,
}
SEP_DD_KB2_DEFAULT = 80

# Phân cách KB2 – ARR→ARR
SEP_AA_KB2 = {
    ('S','H'): 165, ('S','M'): 220, ('S','L'): 220,
    ('H','M'): 165, ('H','L'): 165,
    ('M','L'): 110,
}
SEP_AA_KB2_DEFAULT = 110

SEP_AD = 30   # ARR→DEP (không đổi)
SEP_DA = 60   # DEP→ARR (dự phòng)


# ─────────────────────────────────────────────────
# 2. TIỆN ÍCH
# ─────────────────────────────────────────────────
BASE = 8 * 3600

def to_sec(t_str: str) -> int:
    t_str = t_str.strip()
    parts = t_str.split(':')
    h = int(parts[0])
    m = int(parts[1])
    s = int(parts[2]) if len(parts) > 2 else 0
    return h * 3600 + m * 60 + s - BASE

def fmt_sec(sec: int) -> str:
    total = sec + BASE
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def fmt_dur(sec: int) -> str:
    if sec <= 0:
        return "0s"
    m = sec // 60
    s = sec % 60
    return f"{m}p{s:02d}s" if m > 0 else f"{s}s"

def separation_kb2(prev_type, prev_wake, curr_type, curr_wake) -> int:
    if prev_type == 'DEP' and curr_type == 'DEP':
        return SEP_DD_KB2.get((prev_wake, curr_wake), SEP_DD_KB2_DEFAULT)
    if prev_type == 'ARR' and curr_type == 'ARR':
        return SEP_AA_KB2.get((prev_wake, curr_wake), SEP_AA_KB2_DEFAULT)
    if prev_type == 'ARR' and curr_type == 'DEP':
        return SEP_AD
    return SEP_DA

# Phân cách KB1 để so sánh
SEP_DD_KB1 = {('S','H'):120,('S','M'):180,('S','L'):240,('H','M'):120,('H','L'):180,('M','L'):180}
SEP_AA_KB1 = {('S','H'):180,('S','M'):240,('S','L'):240,('H','M'):180,('H','L'):180,('M','L'):120}
SEP_DD_KB1_DEF = 90
SEP_AA_KB1_DEF = 120

def separation_kb1(prev_type, prev_wake, curr_type, curr_wake) -> int:
    if prev_type == 'DEP' and curr_type == 'DEP':
        return SEP_DD_KB1.get((prev_wake, curr_wake), SEP_DD_KB1_DEF)
    if prev_type == 'ARR' and curr_type == 'ARR':
        return SEP_AA_KB1.get((prev_wake, curr_wake), SEP_AA_KB1_DEF)
    if prev_type == 'ARR' and curr_type == 'DEP':
        return SEP_AD
    return SEP_DA


# ─────────────────────────────────────────────────
# 3. ĐỌC DỮ LIỆU
# ─────────────────────────────────────────────────
def load_arrivals(path: str) -> list:
    rows = []
    with open(path, newline='', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            wake  = r['Wake'].strip().upper()
            t_occ = to_sec(r['OccupyTime'].strip())
            rwy   = r.get('Rwy', '25R').strip() or '25R'
            rows.append({
                'event_type': 'ARR',
                'acid': r['ACID'].strip(),
                'ac_type': r['Type'].strip(),
                'wake': wake,
                'ready_time': t_occ,
                'rwy': rwy,
                'priority': 'Normal',
                'rot': ROT_ARR[wake],
                'dman_index': None,
            })
    return rows

def load_departures(path: str) -> list:
    rows = []
    with open(path, newline='', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            wake     = r['Wake'].strip().upper()
            priority = r.get('Priority', 'Normal').strip()
            t_req_raw = r['ReqTime'].strip()
            if t_req_raw.count(':') == 1:
                t_req_raw += ':00'
            t_req    = to_sec(t_req_raw)
            gate     = int(r['Gate'].strip())
            rwy      = r.get('Rwy', '25L').strip() or '25L'
            trans    = r.get('Transfer_to_DEP', 'FALSE').strip().upper() == 'TRUE'

            taxi     = TAXI_TABLE.get(gate, 600)
            # KB2: dùng T_DCL + T_TAXI_C_DCL (datalink)
            t_hp     = t_req + T_DCL + T_PUSH + taxi + T_TAXI_C_DCL
            ready    = t_hp + T_LUP
            bonus    = DMAN_BONUS.get(priority, 0)
            dman_idx = t_hp + bonus

            rows.append({
                'event_type': 'DEP',
                'acid': r['ACID'].strip(),
                'ac_type': r['Type'].strip(),
                'wake': wake,
                'req_time': t_req,
                'gate': gate,
                'sid': r.get('SID', '').strip(),
                'priority': priority,
                'rwy': rwy,
                'transfer_to_dep': trans,
                't_hp': t_hp,
                'ready_time': ready,
                'rot': ROT_DEP[wake],
                'taxi_time': taxi,
                'dman_index': dman_idx,
                'bonus': bonus,
            })
    return rows


def apply_transfer_to_dep(arrivals: list, departures: list) -> list:
    """
    Xử lý Transfer_to_DEP = True:
    Với DEP có cùng ACID với một ARR, tính lại:
      ready_time  = T_occupy_ARR + ROT_ARR + T_xfer(wake) + T_lup
      dman_index  = T_occupy_ARR + ROT_ARR + T_xfer(wake) + bonus
      t_hp        = T_occupy_ARR + ROT_ARR + T_xfer(wake)   (không có DCL/taxi vì đến thẳng)
    """
    import copy
    arr_map = {a['acid']: a for a in arrivals}   # ACID → ARR record
    result  = []
    for dep in departures:
        d = copy.deepcopy(dep)
        if d['transfer_to_dep']:
            acid = d['acid']
            arr  = arr_map.get(acid)
            if arr:
                t_occ      = arr['ready_time']          # T_occupy của ARR
                rot_arr    = arr['rot']                  # ROT_ARR theo loại tàu
                t_xfer_val = T_XFER[d['wake']]
                bonus      = d['bonus']

                t_hp_xfer  = t_occ + rot_arr + t_xfer_val
                d['t_hp']        = t_hp_xfer
                d['ready_time']  = t_hp_xfer + T_LUP
                d['dman_index']  = t_hp_xfer + bonus
                d['transfer_note'] = (
                    f"Transfer từ ARR {acid}: "
                    f"T_occ={fmt_sec(t_occ)} + ROT_ARR={rot_arr}s + T_xfer={t_xfer_val}s"
                )
            else:
                d['transfer_note'] = f"⚠️ Không tìm thấy ARR ghép cặp cho {acid}"
        result.append(d)
    return result


# ─────────────────────────────────────────────────
# 4. THUẬT TOÁN KB2: ACDM + DCL + DMAN
# ─────────────────────────────────────────────────
def run_acdm(arrivals: list, departures: list) -> list:
    # Bước 0: Xử lý Transfer_to_DEP trước khi tính DMAN Index
    departures = apply_transfer_to_dep(arrivals, departures)

    # Bước 1: Sắp xếp DEP theo DMAN_Index tăng dần → in ra để kiểm tra
    sorted_deps = sorted(departures, key=lambda e: e['dman_index'])
    print("\n── DMAN Index – thứ tự đề xuất cất cánh ──")
    print(f"  {'#':>3}  {'ACID':<10}  {'Priority':<8}  {'DMAN Index':>12}  {'Bonus':>6}  {'Transfer':>8}")
    print("  " + "─" * 60)
    for i, d in enumerate(sorted_deps, 1):
        xfer_flag = "✔ xfer" if d.get('transfer_to_dep') else ""
        print(f"  {i:>3}  {d['acid']:<10}  {d['priority']:<8}  "
              f"{fmt_sec(d['dman_index']):>12}  {d['bonus']:>+6}s  {xfer_flag}")
    print()

    # Bước 2: Gộp với ARR, sort theo ready_time (ARR ưu tiên hơn DEP nếu bằng)
    all_events = arrivals + sorted_deps
    all_events.sort(key=lambda e: (e['ready_time'], 0 if e['event_type'] == 'ARR' else 1))

    rwy_state = {
        '25R': {'free': 0, 'last_type': None, 'last_wake': None},
        '25L': {'free': 0, 'last_type': None, 'last_wake': None},
    }
    prev_actual = {}
    results = []

    for ev in all_events:
        rwy  = ev['rwy']
        st   = rwy_state[rwy]
        ready = ev['ready_time']
        rot   = ev['rot']

        if st['last_type'] is None:
            t_actual = ready
        else:
            sep      = separation_kb2(st['last_type'], st['last_wake'],
                                      ev['event_type'], ev['wake'])
            safe     = st['free'] + sep
            t_actual = max(ready, safe)

        wait = t_actual - ready
        gap  = t_actual - prev_actual.get(rwy, t_actual) if st['last_type'] else 0

        record = dict(ev)
        record['t_actual']  = t_actual
        record['wait']      = wait
        record['gap']       = gap
        record['t_rwy_end'] = t_actual + rot
        results.append(record)

        st['free']       = t_actual + rot
        st['last_type']  = ev['event_type']
        st['last_wake']  = ev['wake']
        prev_actual[rwy] = t_actual

    return results

# Chạy lại KB1 để so sánh (dùng T_ATC=15, T_TAXIC=10, sep KB1)
T_ATC_KB1   = 15
T_TAXI_C_KB1 = 10

def run_fcfs_for_compare(arrivals: list, departures_orig: list) -> dict:
    """Tính T_actual KB1 từ dữ liệu gốc, trả về dict acid→t_actual."""
    import copy
    deps = []
    for r in departures_orig:
        d = copy.deepcopy(r)
        taxi  = TAXI_TABLE.get(d['gate'], 600)
        t_req = d['req_time']
        t_hp  = t_req + T_ATC_KB1 + T_PUSH + taxi + T_TAXI_C_KB1
        d['t_hp']       = t_hp
        d['ready_time'] = t_hp + T_LUP
        # Cập nhật bonus để apply_transfer_to_dep dùng đúng (KB1 không có bonus, =0)
        d['bonus'] = 0
        deps.append(d)

    # Xử lý Transfer_to_DEP với tham số KB1
    deps = apply_transfer_to_dep(arrivals, deps)

    all_ev = list(arrivals) + deps
    all_ev.sort(key=lambda e: (e['ready_time'], 0 if e['event_type'] == 'ARR' else 1))

    state = {'25R': {'free':0,'last_type':None,'last_wake':None},
             '25L': {'free':0,'last_type':None,'last_wake':None}}
    prev_a = {}
    kb1_map = {}

    for ev in all_ev:
        rwy = ev['rwy']
        st  = state[rwy]
        ready = ev['ready_time']
        rot   = ev['rot']
        if st['last_type'] is None:
            t_actual = ready
        else:
            sep      = separation_kb1(st['last_type'], st['last_wake'],
                                      ev['event_type'], ev['wake'])
            safe     = st['free'] + sep
            t_actual = max(ready, safe)
        kb1_map[ev['acid']] = t_actual
        st['free']      = t_actual + rot
        st['last_type'] = ev['event_type']
        st['last_wake'] = ev['wake']
        prev_a[rwy]     = t_actual

    return kb1_map


# ─────────────────────────────────────────────────
# 5. XUẤT HTML
# ─────────────────────────────────────────────────
WAKE_LABEL = {'S':'SUPER','H':'HEAVY','M':'MEDIUM','L':'LIGHT'}

PRIORITY_STYLE = {
    'Medical': {'row_class':'row-medical','badge':'🏥 Khẩn cấp','hint':'Khẩn cấp – ưu tiên cất trước'},
    'VIP':     {'row_class':'row-vip',    'badge':'★ VIP',       'hint':'VIP – đề xuất cất sớm'},
    'Normal':  {'row_class':'',           'badge':'',             'hint':''},
}

def build_html(results: list, kb1_map: dict) -> str:
    dep_r = [r for r in results if r['event_type'] == 'DEP']
    arr_r = [r for r in results if r['event_type'] == 'ARR']

    avg_wait_dep = sum(r['wait'] for r in dep_r) / len(dep_r) if dep_r else 0
    avg_wait_arr = sum(r['wait'] for r in arr_r) / len(arr_r) if arr_r else 0
    max_wait     = max((r['wait'] for r in results), default=0)

    # Tiết kiệm thời gian so với KB1
    savings = []
    for r in results:
        kb1_t = kb1_map.get(r['acid'])
        if kb1_t is not None:
            savings.append(kb1_t - r['t_actual'])
    total_saving = sum(savings) if savings else 0
    avg_saving   = total_saving // len(savings) if savings else 0

    rwy_counts = {}
    for r in results:
        rwy_counts[r['rwy']] = rwy_counts.get(r['rwy'], 0) + 1

    # ── Table rows ──
    rows_html = ''
    for i, r in enumerate(results, 1):
        ev_class = 'dep' if r['event_type'] == 'DEP' else 'arr'
        pstyle   = PRIORITY_STYLE.get(r.get('priority','Normal'), PRIORITY_STYLE['Normal'])
        row_cls  = f"{ev_class} {pstyle['row_class']}"
        wake_full = WAKE_LABEL.get(r['wake'], r['wake'])

        wait_class = ''
        if r['wait'] > 600:   wait_class = 'wait-high'
        elif r['wait'] > 300: wait_class = 'wait-med'

        # So sánh với KB1
        kb1_t = kb1_map.get(r['acid'])
        if kb1_t is not None:
            delta = kb1_t - r['t_actual']
            if delta > 0:
                delta_html = f'<span class="delta-better">▼ {fmt_dur(delta)}</span>'
            elif delta < 0:
                delta_html = f'<span class="delta-worse">▲ {fmt_dur(-delta)}</span>'
            else:
                delta_html = '<span class="delta-same">–</span>'
        else:
            delta_html = '<span class="delta-same">–</span>'

        if r['event_type'] == 'DEP':
            pri_badge = f'<span class="pri-badge pri-{r["priority"].lower()}">{pstyle["badge"]}</span>' if pstyle['badge'] else ''
            xfer_badge = '<span class="xfer-badge">⇄ Transfer</span>' if r.get('transfer_to_dep') else ''
            # Gợi ý ATC: ưu tiên + transfer note
            hint_text = pstyle["hint"]
            if r.get('transfer_note') and 'Transfer từ ARR' in r.get('transfer_note',''):
                xfer_short = r['transfer_note'].split(':')[1].strip() if ':' in r['transfer_note'] else r['transfer_note']
                hint_text  = (hint_text + ' · ' if hint_text else '') + f'⇄ {xfer_short}'
            hint_cell = f'<td class="hint-cell">{hint_text}</td>'
            dman_html = fmt_sec(r['dman_index']) if r.get('dman_index') is not None else '–'
            dep_extra = f"""
                <td>{r.get('gate','–')}</td>
                <td>{fmt_sec(r.get('req_time', 0))}</td>
                <td>{fmt_sec(r.get('t_hp', 0))}</td>
                <td class="dman-col">{dman_html}</td>
                <td>{r.get('sid','–')}</td>
                {hint_cell}
            """
        else:
            pri_badge  = ''
            xfer_badge = ''
            dep_extra  = '<td colspan="6" class="na-cell">— hạ cánh —</td>'

        rows_html += f"""
        <tr class="{row_cls}">
            <td class="seq-col">{i}</td>
            <td><span class="badge {ev_class}">{r['event_type']}</span></td>
            <td class="acid-col">{r['acid']} {pri_badge} {xfer_badge if r['event_type']=='DEP' and r.get('transfer_to_dep') else ''}</td>
            <td>{r['ac_type']}</td>
            <td><span class="wake-badge wake-{r['wake'].lower()}">{wake_full}</span></td>
            <td class="rwy-col">{r['rwy']}</td>
            <td>{fmt_sec(r['ready_time'])}</td>
            {dep_extra}
            <td class="highlight">{fmt_sec(r['t_actual'])}</td>
            <td class="{wait_class}">{fmt_dur(r['wait'])}</td>
            <td>{fmt_dur(r['gap'])}</td>
            <td>{fmt_sec(r['t_rwy_end'])}</td>
            <td>{delta_html}</td>
        </tr>"""

    # ── KPI ──
    kpi_html = f"""
        <div class="kpi-card"><div class="kpi-value">{len(results)}</div><div class="kpi-label">Tổng sự kiện</div></div>
        <div class="kpi-card arr-card"><div class="kpi-value">{len(arr_r)}</div><div class="kpi-label">Chuyến hạ cánh</div></div>
        <div class="kpi-card dep-card"><div class="kpi-value">{len(dep_r)}</div><div class="kpi-label">Chuyến cất cánh</div></div>
        <div class="kpi-card"><div class="kpi-value">{fmt_dur(int(avg_wait_dep))}</div><div class="kpi-label">Chờ TB (DEP)</div></div>
        <div class="kpi-card"><div class="kpi-value">{fmt_dur(int(avg_wait_arr))}</div><div class="kpi-label">Chờ TB (ARR)</div></div>
        <div class="kpi-card warn-card"><div class="kpi-value">{fmt_dur(max_wait)}</div><div class="kpi-label">Chờ tối đa</div></div>
        <div class="kpi-card save-card"><div class="kpi-value">▼ {fmt_dur(abs(avg_saving))}</div><div class="kpi-label">Tiết kiệm TB/chuyến vs KB1</div></div>
    """

    tp_html = ''.join(
        f'<div class="tp-item"><span class="tp-rwy">{k}</span>: <strong>{v}</strong> chuyến</div>'
        for k, v in sorted(rwy_counts.items())
    )

    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mô phỏng Kịch bản 2 – ACDM + DCL/PDC + DMAN | VVTS 25R/25L</title>
<style>
  :root {{
    --blue-dark:  #0d2137;
    --blue-mid:   #1a4a7a;
    --blue-light: #2e7bcf;
    --dep-bg:     #0e2236;
    --arr-bg:     #0b1f16;
    --yellow:     #ffc107;
    --red:        #dc3545;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: #0b1a2b; color: #e0eaf5; min-height: 100vh;
  }}

  /* ── Header ── */
  header {{
    background: linear-gradient(135deg, #0d2137 0%, #1a3f1a 50%, #1a4a7a 100%);
    padding: 28px 40px 22px;
    border-bottom: 3px solid #28a745;
    display: flex; align-items: center; gap: 20px;
  }}
  .logo-circle {{
    width: 56px; height: 56px; border-radius: 50%;
    background: linear-gradient(135deg, #28a745, #2e7bcf);
    display: flex; align-items: center; justify-content: center;
    font-size: 26px; flex-shrink: 0;
  }}
  header h1 {{ font-size: 1.5rem; font-weight: 700; }}
  header p  {{ font-size: 0.85rem; color: #8ab4d8; margin-top: 4px; }}
  .kb2-tag {{
    margin-left: 12px; padding: 3px 12px; border-radius: 20px;
    background: linear-gradient(90deg,#1a5c2a,#1a4a7a);
    border: 1px solid #28a745; font-size: 0.78rem; font-weight: 700;
    color: #5fe89a; letter-spacing: .05em;
  }}

  main {{ padding: 28px 40px; }}

  .section-title {{
    font-size: 1rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: .08em; color: #8ab4d8;
    margin-bottom: 14px; margin-top: 28px;
    display: flex; align-items: center; gap: 8px;
  }}
  .section-title::before {{
    content: ''; display: inline-block;
    width: 4px; height: 18px; border-radius: 2px;
    background: linear-gradient(#28a745, #2e7bcf);
  }}

  /* ── Diff banner KB1 vs KB2 ── */
  .diff-banner {{
    background: #0c1f30; border: 1px solid #2e7bcf;
    border-left: 4px solid #28a745;
    border-radius: 8px; padding: 14px 20px; margin-bottom: 10px;
    display: flex; flex-wrap: wrap; gap: 24px;
  }}
  .diff-item {{ font-size: 0.83rem; }}
  .diff-label {{ color: #7a9bb8; }}
  .diff-old {{ color: #ff7777; text-decoration: line-through; margin: 0 4px; }}
  .diff-new {{ color: #5fe89a; font-weight: 700; }}

  /* ── KPI ── */
  .kpi-grid {{ display: flex; flex-wrap: wrap; gap: 14px; margin-bottom: 8px; }}
  .kpi-card {{
    background: #12263f; border: 1px solid #1e3f62; border-radius: 10px;
    padding: 16px 22px; min-width: 130px; flex: 1; text-align: center;
    border-top: 4px solid #2e7bcf;
  }}
  .dep-card  {{ border-top-color: #2e7bcf; }}
  .arr-card  {{ border-top-color: #28a745; }}
  .warn-card {{ border-top-color: #ffc107; }}
  .save-card {{ border-top-color: #5fe89a; background: #0c2018; }}
  .kpi-value {{ font-size: 1.8rem; font-weight: 800; color: #fff; line-height:1.1; }}
  .kpi-label {{ font-size: 0.78rem; color: #7a9bb8; margin-top: 5px; }}

  .tp-bar {{
    display: flex; gap: 16px; background: #12263f;
    border: 1px solid #1e3f62; border-radius: 8px; padding: 12px 20px; margin-bottom: 8px;
  }}
  .tp-item {{ font-size: 0.9rem; }}
  .tp-rwy  {{ color: #2e7bcf; font-weight: 700; }}

  .legend {{
    display: flex; gap: 20px; flex-wrap: wrap;
    font-size: 0.82rem; margin-bottom: 16px;
  }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; }}
  .legend-dot  {{ width: 12px; height: 12px; border-radius: 3px; }}

  /* ── Table ── */
  .table-wrapper {{
    overflow-x: auto; border-radius: 10px;
    border: 1px solid #1e3f62;
    box-shadow: 0 4px 24px rgba(0,0,0,.4);
  }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; min-width: 1200px; }}
  thead tr {{
    background: #0d2137; color: #8ab4d8;
    font-size: 0.73rem; text-transform: uppercase; letter-spacing: .05em;
  }}
  thead th {{
    padding: 11px 10px; text-align: center;
    border-bottom: 2px solid #28a745; white-space: nowrap;
  }}
  tbody tr {{ border-bottom: 1px solid #1a3251; }}
  tbody tr:hover {{ filter: brightness(1.18); }}

  tbody tr.dep     {{ background: #0e2236; }}
  tbody tr.arr     {{ background: #0b1f16; }}
  tbody tr.row-medical {{ background: #7f1014 !important; color: #fff9f9; border-left: 4px solid #ff717d; }}
  tbody tr.row-medical td {{ color: #fff9f9; }}
  tbody tr.row-medical td.dman-col {{ background: rgba(255, 255, 255, 0.14); color: #fff9f9; font-weight: 700; border-radius: 4px; }}
  tbody tr.row-vip     {{ background: #b57f00 !important; color: #2b1700; border-left: 4px solid #ffe066; }}
  tbody tr.row-vip td {{ color: #2b1700; }}
  tbody tr.row-vip td.dman-col {{ background: rgba(255, 255, 0, 0.18); color: #2b1700; font-weight: 700; border-radius: 4px; }}

  td {{ padding: 8px 10px; text-align: center; vertical-align: middle; }}
  .seq-col  {{ color: #555e70; font-size: 0.76rem; width: 32px; }}
  .acid-col {{ font-weight: 700; font-family: monospace; font-size: 0.88rem; color: #e8f4fd; }}
  .rwy-col  {{ font-weight: 700; color: #f0c040; }}
  .highlight {{ font-weight: 800; color: #5bc8ff; font-size: 0.93rem; }}
  .na-cell  {{ color: #3a5570; font-style: italic; font-size: 0.78rem; }}
  .hint-cell {{ color: #ffc107; font-size: 0.78rem; text-align: left; }}
  .wait-high {{ color: #ff6b6b; font-weight: 700; }}
  .wait-med  {{ color: #ffc107; font-weight: 600; }}

  .delta-better {{ color: #5fe89a; font-weight: 700; }}
  .delta-worse  {{ color: #ff7777; }}
  .delta-same   {{ color: #555e70; }}

  /* ── Badges ── */
  .badge {{ display: inline-block; padding: 2px 9px; border-radius: 4px; font-weight: 700; font-size: 0.76rem; }}
  .badge.dep {{ background: #1a4a7a; color: #7bc8ff; border: 1px solid #2e7bcf; }}
  .badge.arr {{ background: #0d3320; color: #5fe89a; border: 1px solid #28a745; }}

  .wake-badge {{ display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 0.72rem; font-weight: 600; }}
  .wake-h {{ background: #4a1a1a; color: #ff8888; }}
  .wake-m {{ background: #1a3a4a; color: #88d0ff; }}
  .wake-l {{ background: #1a3a1a; color: #88e888; }}
  .wake-s {{ background: #3a1a4a; color: #cc88ff; }}

  .pri-badge {{ display: inline-block; padding: 1px 7px; border-radius: 10px; font-size: 0.72rem; font-weight: 700; margin-left: 5px; }}
  .pri-medical {{ background: #5a0015; color: #ff8899; border: 1px solid #ff4466; }}
  .pri-vip     {{ background: #3a2a00; color: #ffd966; border: 1px solid #ffc107; }}
  .pri-normal  {{ display: none; }}

  .xfer-badge {{
    display: inline-block; padding: 1px 6px; border-radius: 10px;
    font-size: 0.68rem; font-weight: 700; margin-left: 4px;
    background: #1a2a4a; color: #88ccff; border: 1px solid #3a7abf;
  }}

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
    <h1>Mô phỏng Kịch bản 2 – ACDM + DCL/PDC + DMAN
        <span class="kb2-tag">KB2</span></h1>
    <p>Sân bay Quốc tế Tân Sơn Nhất (VVTS) &nbsp;|&nbsp; Đường băng 25R / 25L &nbsp;|&nbsp;
       Datalink clearance · Ưu tiên VIP/Medical · Tối ưu hoá thứ tự bằng DMAN</p>
  </div>
</header>

<main>

  <div class="section-title">Thay đổi so với Kịch bản 1 (FCFS)</div>
  <div class="diff-banner">
    <div class="diff-item">
      <span class="diff-label">Cấp phép cất cánh</span>
      <span class="diff-old">15s thoại</span> →
      <span class="diff-new">2s datalink</span>
    </div>
    <div class="diff-item">
      <span class="diff-label">Cấp phép lăn</span>
      <span class="diff-old">10s thoại</span> →
      <span class="diff-new">2s datalink</span>
    </div>
    <div class="diff-item">
      <span class="diff-label">Sắp xếp DEP</span>
      <span class="diff-old">FCFS (ready_time)</span> →
      <span class="diff-new">DMAN Index (ưu tiên VIP/Medical)</span>
    </div>
    <div class="diff-item">
      <span class="diff-label">Phân cách DEP→DEP</span>
      <span class="diff-old">90–240s</span> →
      <span class="diff-new">80–220s</span>
    </div>
    <div class="diff-item">
      <span class="diff-label">Phân cách ARR→ARR</span>
      <span class="diff-old">120–240s</span> →
      <span class="diff-new">110–220s</span>
    </div>
  </div>

  <div class="section-title">Tổng quan</div>
  <div class="kpi-grid">{kpi_html}</div>

  <div class="section-title" style="margin-top:18px">Thông lượng theo đường băng</div>
  <div class="tp-bar">{tp_html}</div>

  <div class="section-title">Kết quả chi tiết – DMAN Queue</div>
  <div class="legend">
    <div class="legend-item"><div class="legend-dot" style="background:#1a4a7a;border:1px solid #2e7bcf"></div> DEP – Cất cánh</div>
    <div class="legend-item"><div class="legend-dot" style="background:#0d3320;border:1px solid #28a745"></div> ARR – Hạ cánh</div>
    <div class="legend-item"><div class="legend-dot" style="background:#2a0a12;border:1px solid #ff4466"></div> 🏥 Medical – Ưu tiên cao nhất</div>
    <div class="legend-item"><div class="legend-dot" style="background:#2a2000;border:1px solid #ffc107"></div> ★ VIP – Ưu tiên cao</div>
    <div class="legend-item"><div class="legend-dot" style="background:#5fe89a"></div> ▼ Cải thiện so KB1</div>
    <div class="legend-item"><div class="legend-dot" style="background:#ff7777"></div> ▲ Trễ hơn KB1 (do đổi thứ tự)</div>
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
          <th>DMAN Index</th>
          <th>SID</th>
          <th>Gợi ý ATC</th>
          <th>T_actual ✈</th>
          <th>Chờ</th>
          <th>GAP</th>
          <th>RWY Free</th>
          <th>vs KB1</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </div>

</main>

<footer>
  Kịch bản 2 – ACDM + DCL/PDC + DMAN &nbsp;|&nbsp; Phân cách giảm nhẹ theo tiêu chuẩn tối ưu hoá &nbsp;|&nbsp;
  Thời gian tính từ mốc 08:00:00 UTC+7 &nbsp;|&nbsp; Quyết định cuối thuộc về kiểm soát viên không lưu
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
    out_file = BASE_DIR / 'ket_qua_kich_ban2.html'

    arrivals   = load_arrivals(str(arr_file))
    departures = load_departures(str(dep_file))

    results  = run_acdm(arrivals, departures)
    kb1_map  = run_fcfs_for_compare(load_arrivals(str(arr_file)),
                                    load_departures(str(dep_file)))

    html = build_html(results, kb1_map)
    out_file.write_text(html, encoding='utf-8')

    print(f"✅ Xong! Kết quả đã lưu tại: {out_file}")
    print(f"   Tổng sự kiện : {len(results)}")
    print(f"   ARR          : {sum(1 for r in results if r['event_type']=='ARR')}")
    print(f"   DEP          : {sum(1 for r in results if r['event_type']=='DEP')}")

    print("\n── Chi tiết DMAN queue (DEP) ──")
    for r in results:
        if r['event_type'] == 'DEP':
            kb1_t  = kb1_map.get(r['acid'])
            delta  = (kb1_t - r['t_actual']) if kb1_t else 0
            sign   = f"▼{fmt_dur(delta)}" if delta > 0 else (f"▲{fmt_dur(-delta)}" if delta < 0 else "–")
            pri    = r.get('priority','Normal')
            dman   = fmt_sec(r['dman_index'])
            print(f"  {pri:8s} {r['acid']:10s} DMAN={dman} actual={fmt_sec(r['t_actual'])} wait={fmt_dur(r['wait'])} vs_KB1={sign}")