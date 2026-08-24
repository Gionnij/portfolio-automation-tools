#!/usr/bin/env python3
"""dashboard.py - one-command monthly run with a readable report in the browser.

    python dashboard.py --contribute 600 --ib 127.0.0.1:4002
    python dashboard.py --contribute 600 --deploy 1050 --ib 127.0.0.1:4002
    python dashboard.py --view                 # just re-render the last report

What it does:
  1. runs fetch_prices.py   (fills prices.csv from justETF/Yahoo)
  2. runs rebalance.py      (DRY RUN - stages orders, never executes)
  3. renders prep_report.md + orders.json + state.json into report.html
     and opens it in your default browser.

Executing orders stays a deliberate terminal step - by design (manual rule:
human confirmation per order). The page shows you the exact command.

Requires: nothing beyond the standard library (pandas only via rebalance.py).
"""

import argparse
import html
import json
import re
import subprocess
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable or "python3"

STATUS_COLORS = {"PASS": "#1a7f37", "CHECK": "#b35900", "HUMAN": "#4a5568",
                 "FAIL": "#c0392b"}
REGIME_COLORS = {"Calm": "#1a7f37", "Correction": "#b35900", "Crash": "#c0392b"}


# ---------------------------------------------------------------- run steps

def run_step(args_list):
    """Run a child script, stream nothing, capture everything."""
    p = subprocess.run([PY] + args_list, cwd=HERE, capture_output=True,
                       text=True)
    out = (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
    return p.returncode == 0, out.strip()


# ---------------------------------------------------------------- md parsing

def parse_report(md_text):
    """Split the prep report into title, meta line and named sections."""
    lines = md_text.splitlines()
    title = lines[0].lstrip("# ").strip() if lines else "Portfolio prep report"
    meta = lines[1].strip() if len(lines) > 1 else ""
    sections, current, buf = {}, None, []
    for ln in lines[2:]:
        if ln.startswith("## "):
            if current:
                sections[current] = buf
            current, buf = ln[3:].strip(), []
        else:
            buf.append(ln)
    if current:
        sections[current] = buf
    return title, meta, sections


def parse_table(section_lines):
    """Markdown table -> (headers, rows). Ignores non-table lines."""
    rows = [ln for ln in section_lines if ln.strip().startswith("|")]
    out = []
    for ln in rows:
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if cells and not all(set(c) <= {"-", " ", ":"} for c in cells):
            out.append(cells)
    if not out:
        return [], []
    return out[0], out[1:]


def section_by_prefix(sections, prefix):
    for k, v in sections.items():
        if k.lower().startswith(prefix.lower()):
            return v
    return []


# ---------------------------------------------------------------- rendering

def esc(s):
    return html.escape(str(s))


def chip(text, color):
    return (f'<span style="background:{color};color:#fff;padding:2px 10px;'
            f'border-radius:10px;font-size:12px;font-weight:600">{esc(text)}'
            f'</span>')


def weights_html(headers, rows):
    if not rows:
        return "<p class='muted'>no data</p>"
    try:
        scale = max(max(float(r[1]), float(r[2])) for r in rows) or 1.0
    except (ValueError, IndexError):
        scale = 100.0
    out = ["<table class='w'><tr><th>Sleeve</th><th style='width:45%'>"
           "Current vs target</th><th>Cur %</th><th>Tgt %</th>"
           "<th>Gap EUR</th><th>Routed EUR</th></tr>"]
    for r in rows:
        t = r[0]
        try:
            cur, tgt = float(r[1]), float(r[2])
        except ValueError:
            cur = tgt = 0.0
        wc, wt = 100 * cur / scale, 100 * tgt / scale
        bar = (f"<div class='track'>"
               f"<div class='tgt' style='width:{wt:.1f}%'></div>"
               f"<div class='cur' style='width:{wc:.1f}%'></div></div>")
        gap = r[3] if len(r) > 3 else ""
        routed = r[4] if len(r) > 4 else ""
        hot = " style='font-weight:700'" if routed not in ("0", "", "0.0") \
            else ""
        out.append(f"<tr{hot}><td>{esc(t)}</td><td>{bar}</td>"
                   f"<td>{cur:.2f}</td><td>{tgt:.1f}</td>"
                   f"<td>{esc(gap)}</td><td>{esc(routed)}</td></tr>")
    out.append("</table>")
    out.append("<p class='muted'>light bar = target &nbsp;|&nbsp; "
               "dark bar = current &nbsp;|&nbsp; bold row = money routed "
               "this run</p>")
    return "\n".join(out)


def orders_html(orders, execute_cmd):
    if not orders:
        return "<p class='muted'>None this month.</p>"
    total = sum(o.get("qty", 0) * o.get("est_price", 0)
                for o in orders if o.get("side") == "BUY")
    out = ["<table class='w'><tr><th>Side</th><th>Ticker</th><th>Qty</th>"
           "<th>Est. price</th><th>Est. EUR</th></tr>"]
    for o in orders:
        side = o.get("side", "?")
        col = "#1a7f37" if side == "BUY" else "#c0392b"
        est = o.get("qty", 0) * o.get("est_price", 0)
        out.append(f"<tr><td>{chip(side, col)}</td>"
                   f"<td><b>{esc(o.get('ticker', ''))}</b></td>"
                   f"<td>{esc(o.get('qty', ''))}</td>"
                   f"<td>{esc(o.get('est_price', ''))}</td>"
                   f"<td>{est:,.0f}</td></tr>")
    out.append(f"<tr><td colspan='4' style='text-align:right'>"
               f"<b>total buys</b></td><td><b>{total:,.0f}</b></td></tr>")
    out.append("</table>")
    out.append(f"<div class='cmd'>These orders are <b>staged only</b>. "
               f"To execute (asks per order):<br>"
               f"<code>{esc(execute_cmd)}</code></div>")
    return "\n".join(out)


def checklist_html(headers, rows):
    if not rows:
        return "<p class='muted'>no data</p>"
    out = ["<table class='w'><tr><th>&sect;</th><th>Criterion</th>"
           "<th>Status</th><th>Detail</th></tr>"]
    for r in rows:
        para = r[0] if len(r) > 0 else ""
        crit = r[1] if len(r) > 1 else ""
        stat = r[2] if len(r) > 2 else ""
        det = r[3] if len(r) > 3 else ""
        col = STATUS_COLORS.get(stat, "#4a5568")
        if len(det) > 110:
            det_html = (f"<details><summary>{esc(det[:90])}&hellip;"
                        f"</summary>{esc(det)}</details>")
        else:
            det_html = esc(det)
        out.append(f"<tr><td>{esc(para)}</td><td>{esc(crit)}</td>"
                   f"<td>{chip(stat, col)}</td>"
                   f"<td class='muted'>{det_html}</td></tr>")
    out.append("</table>")
    return "\n".join(out)


def sparkline_html(history):
    """Tiny inline SVG of the unit price history from state.json."""
    pts = [h.get("unit", 0) or 0 for h in history]
    pts = [p for p in pts if p > 0]
    if len(pts) < 2:
        return ("<p class='muted'>unit-price history appears here once the "
                "portfolio has NAV (needs &ge; 2 non-zero points)</p>")
    lo, hi = min(pts), max(pts)
    rng = (hi - lo) or 1.0
    W, H = 560, 80
    step = W / (len(pts) - 1)
    coords = " ".join(f"{i*step:.1f},{H-8-((p-lo)/rng)*(H-16):.1f}"
                      for i, p in enumerate(pts))
    return (f"<svg width='{W}' height='{H}' style='overflow:visible'>"
            f"<polyline points='{coords}' fill='none' stroke='#2b6cb0' "
            f"stroke-width='2'/></svg>"
            f"<p class='muted'>equity unit price, {len(pts)} runs "
            f"(min {lo:.2f} / max {hi:.2f})</p>")


CSS = """
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
     background:#f5f6f8;color:#1a202c;margin:0;padding:32px 16px}
.wrap{max-width:900px;margin:0 auto}
.card{background:#fff;border-radius:12px;padding:20px 24px;margin-bottom:18px;
      box-shadow:0 1px 3px rgba(0,0,0,.08)}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:15px;text-transform:uppercase;letter-spacing:.06em;color:#4a5568;
   margin:0 0 14px}
.muted{color:#718096;font-size:13px}
table.w{width:100%;border-collapse:collapse;font-size:14px}
table.w th{text-align:left;color:#718096;font-weight:600;font-size:12px;
           text-transform:uppercase;letter-spacing:.04em;
           padding:6px 8px;border-bottom:2px solid #e2e8f0}
table.w td{padding:7px 8px;border-bottom:1px solid #edf2f7;vertical-align:top}
.track{position:relative;height:16px;background:#edf2f7;border-radius:8px}
.tgt{position:absolute;top:0;left:0;height:16px;background:#bee3f8;
     border-radius:8px}
.cur{position:absolute;top:3px;left:0;height:10px;background:#2b6cb0;
     border-radius:5px}
.cmd{margin-top:14px;padding:12px;background:#f7fafc;border:1px solid #e2e8f0;
     border-radius:8px;font-size:13px}
code{background:#edf2f7;padding:2px 6px;border-radius:4px;font-size:12.5px}
details summary{cursor:pointer}
.badges span{margin-right:8px}
pre{background:#1a202c;color:#e2e8f0;padding:14px;border-radius:8px;
    font-size:12px;overflow-x:auto;white-space:pre-wrap}
"""


def build_html(title, meta, sections, orders, history, run_logs, execute_cmd):
    regime_txt = " ".join(section_by_prefix(sections, "Regime"))
    m = re.search(r"D = ([\-\d.]+)%.*?(Calm|Correction|Crash)", regime_txt)
    d_val, regime = (m.group(1), m.group(2)) if m else ("?", "?")
    rcol = REGIME_COLORS.get(regime, "#4a5568")

    wh, wr = parse_table(section_by_prefix(sections, "Current vs target"))
    ch, cr = parse_table(section_by_prefix(sections, "Manual compliance"))

    n_pass = sum(1 for r in cr if len(r) > 2 and r[2] == "PASS")
    n_check = sum(1 for r in cr if len(r) > 2 and r[2] == "CHECK")
    n_fail = sum(1 for r in cr if len(r) > 2 and r[2] == "FAIL")

    logs = "\n\n".join(f"$ {esc(c)}\n{esc(o)}" for c, o in run_logs)

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>{esc(title)}</title><style>{CSS}</style></head><body><div class="wrap">

<div class="card">
  <h1>{esc(title)}</h1>
  <p class="muted">{esc(meta)} &nbsp;&middot;&nbsp; rendered
     {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
  <p class="badges">{chip(f"Regime: {regime}", rcol)}
     {chip(f"D = {d_val}%", "#2b6cb0")}
     {chip(f"{n_pass} PASS", STATUS_COLORS['PASS'])}
     {chip(f"{n_check} CHECK", STATUS_COLORS['CHECK']) if n_check else ""}
     {chip(f"{n_fail} FAIL", STATUS_COLORS['FAIL']) if n_fail else ""}</p>
</div>

<div class="card"><h2>Staged orders</h2>{orders_html(orders, execute_cmd)}</div>

<div class="card"><h2>Current vs target</h2>{weights_html(wh, wr)}</div>

<div class="card"><h2>Compliance checklist</h2>{checklist_html(ch, cr)}</div>

<div class="card"><h2>Unit price history</h2>{sparkline_html(history)}</div>

<div class="card"><h2>Run log</h2>
<details><summary class="muted">terminal output of this run</summary>
<pre>{logs or 'no run this time (--view)'}</pre></details></div>

</div></body></html>"""


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contribute", type=float, default=None)
    ap.add_argument("--deploy", type=float, default=None)
    ap.add_argument("--ib", default="127.0.0.1:4002")
    ap.add_argument("--min-order", type=float, default=None)
    ap.add_argument("--view", action="store_true",
                    help="only re-render the existing report, run nothing")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    run_logs = []
    if not args.view:
        if args.contribute is None:
            sys.exit("need --contribute (or use --view)")
        if not args.skip_fetch:
            ok, out = run_step(["fetch_prices.py"])
            run_logs.append(("python fetch_prices.py", out))
            print(out)
            if not ok:
                print("\n(fetch had misses - continuing; rebalance has "
                      "its own fallbacks)\n")
        cmd = ["rebalance.py", "--contribute", str(args.contribute),
               "--ib", args.ib]
        if args.deploy is not None:
            cmd += ["--deploy", str(args.deploy)]
        if args.min_order is not None:
            cmd += ["--min-order", str(args.min_order)]
        ok, out = run_step(cmd)
        run_logs.append(("python " + " ".join(cmd), out))
        print(out)
        if not ok:
            sys.exit("\nrebalance failed - fix the error above, then rerun")

    md_path = HERE / "prep_report.md"
    if not md_path.exists():
        sys.exit("no prep_report.md found - run without --view first")
    title, meta, sections = parse_report(md_path.read_text())

    try:
        orders = json.loads((HERE / "orders.json").read_text())
    except Exception:
        orders = []
    try:
        history = json.loads((HERE / "state.json").read_text()).get(
            "history", [])
    except Exception:
        history = []

    execute_cmd = f"python rebalance.py --execute orders.json --ib {args.ib}"
    out_path = HERE / "report.html"
    out_path.write_text(build_html(title, meta, sections, orders, history,
                                   run_logs, execute_cmd))
    print(f"\nreport: {out_path}")
    if not args.no_open:
        try:
            webbrowser.open(out_path.as_uri())
        except Exception:
            pass


if __name__ == "__main__":
    main()
