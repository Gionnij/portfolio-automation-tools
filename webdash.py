#!/usr/bin/env python3
"""webdash.py - interactive local dashboard for the whole monthly ritual.

    python webdash.py          # opens http://127.0.0.1:8642 in your browser

From the page you can:
  * pick Paper (port 4002) or LIVE (port 4001)  - host fixed to 127.0.0.1
  * set contribution / deploy / min-order
  * "Preview my plan" -> runs fetch_prices.py + rebalance.py DRY RUN, shows the
    staged orders, weights vs target, regime and compliance checklist
  * tick/untick individual orders, type the confirmation phrase, "Execute"
    -> places ONLY the ticked orders (rebalance.py --execute --yes)
  * Account tools -> discard an unsubmitted preview or review a tracking reset

Safety model (same human gate as the terminal, different skin):
  * server binds to 127.0.0.1 only - nothing is reachable from outside
  * nothing is ever sent to IBKR without you typing the confirmation phrase:
       paper account:  EXECUTE
       live  account:  EXECUTE LIVE     (page turns red in live mode)
  * per-order approval = the checkboxes; unticked orders are never sent
  * Gateway's own Read-Only API toggle stays your hardware-level safety

Requires: standard library only (rebalance.py itself needs pandas/ib_async).
"""

import json
import hashlib
import math
import re
from datetime import datetime, timezone
import shutil
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import workspace

HERE = Path(__file__).resolve().parent
PY = sys.executable or "python3"
# One folder serves BOTH accounts: every stateful file is namespaced, so the
# paper account's memory can never be read or written by a live run.
PORTS = {"paper": 4002, "live": 4001}
CONFIRM = {"paper": "EXECUTE", "live": "EXECUTE LIVE"}


def P(acct):
    """Per-account file paths."""
    a = "live" if acct == "live" else "paper"
    return dict(
        state=HERE / f"state.{a}.json",
        undo=HERE / f"state.{a}.undo.json",
        pending=HERE / f"state.{a}.pending",
        orders=HERE / f"orders.{a}.json",
        approved=HERE / f"orders_approved.{a}.json",
        result=HERE / f"orders_result.{a}.json",
        report=HERE / f"prep_report.{a}.md",
    )


def _pending(acct):
    try:
        return P(acct)["pending"].read_text().strip() == "1"
    except Exception:
        return False


def _uncertain(acct):
    try:
        return P(acct)["pending"].read_text().strip() == "2"
    except OSError:
        return False


def restore_preview(pp):
    # An empty backup records that no tracking state existed before this preview.
    if pp["undo"].read_bytes():
        shutil.copy(pp["undo"], pp["state"])
    else:
        pp["state"].unlink(missing_ok=True)


SERVER_PORT = 8642
ACTION_LOCK = threading.Lock()


# ------------------------------------------------------------------ helpers

def run_step(args_list):
    p = subprocess.run([PY] + args_list, cwd=HERE, capture_output=True,
                       text=True)
    out = (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
    return p.returncode == 0, out.strip()


def parse_report(md_text):
    lines = md_text.splitlines()
    title = lines[0].lstrip("# ").strip() if lines else ""
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
    rows = []
    for ln in section_lines:
        if not ln.strip().startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if cells and not all(set(c) <= {"-", " ", ":"} for c in cells):
            rows.append(cells)
    return (rows[0], rows[1:]) if rows else ([], [])


def section_by_prefix(sections, prefix):
    for k, v in sections.items():
        if k.lower().startswith(prefix.lower()):
            return v
    return []


def plan_id(acct):
    """Bind approval to exactly the snapshot, orders and policy reviewed."""
    digest = hashlib.sha256(acct.encode())
    for path in (P(acct)["report"], P(acct)["orders"], HERE / "manual.json"):
        if not path.exists():
            return None
        digest.update(path.read_bytes())
        digest.update(str(path.stat().st_mtime_ns).encode())
    return digest.hexdigest()


def report_payload(acct, run_logs):
    """Structured, source-backed display data; estimates exclude broker fees."""
    pp = P(acct)
    try:
        cfg = json.loads((HERE / "manual.json").read_text())
    except (OSError, ValueError):
        cfg = {}
    base = {"ok": True, "account": acct, "has_report": pp["report"].exists(),
            "submission_uncertain": _uncertain(acct),
            "funds": cfg.get("sleeves", {}),
            "min_order": cfg.get("rules", {}).get("min_order_eur", 100),
            "log": "\n\n".join(f"$ {c}\n{o}" for c, o in run_logs)}
    if not base["has_report"]:
        return base
    title, meta, sections = parse_report(pp["report"].read_text())
    regime_lines = section_by_prefix(sections, "Regime")
    regime_txt = " ".join(regime_lines)
    m = re.search(r"D = ([\-\d.]+)%.*?(Calm|Correction|Crash)", regime_txt)
    dm = re.search(r"\*\*DRIFT:\*\*\s*(.+)", regime_txt)
    _, wrows = parse_table(section_by_prefix(sections, "Current vs target"))
    _, crows = parse_table(section_by_prefix(sections, "Manual compliance"))
    try:
        orders = json.loads(pp["orders"].read_text())
    except (OSError, ValueError):
        orders = []
    try:
        history = json.loads(pp["state"].read_text()).get("history", [])
    except (OSError, ValueError):
        history = []
    try:
        results = json.loads(pp["result"].read_text())
    except (OSError, ValueError):
        results = []
    def amount(pattern):
        found = re.search(pattern, meta)
        return float(found.group(1).replace(",", "")) if found else None
    contribution = amount(r"contribution EUR ([\d,.-]+)")
    buys = round(sum(o["qty"] * o["est_price"] for o in orders if o["side"] == "BUY"), 2)
    sells = round(sum(o["qty"] * o["est_price"] for o in orders if o["side"] == "SELL"), 2)
    date_match = re.search(r"\d{4}-\d{2}-\d{2}", title)
    return dict(base, title=title, meta=meta,
                d=float(m.group(1)) if m else None,
                regime=m.group(2) if m else None,
                orders=orders, weights=wrows, checklist=crows,
                units=[h.get("unit", 0) for h in history], history=history[-20:],
                drift=dm.group(1).strip() if dm else None,
                notes=[ln[2:].strip() for ln in regime_lines if ln.startswith("- ")],
                held_back=[ln.strip() for ln in section_by_prefix(sections, "Staged orders")
                           if ln.startswith(("Held back", "Reason:", "Skipped"))],
                pending=_pending(acct), plan_id=plan_id(acct),
                snapshot_date=date_match.group() if date_match else None,
                updated_at=datetime.fromtimestamp(pp["report"].stat().st_mtime, timezone.utc).isoformat(),
                nav=amount(r"NAV EUR ([\d,.-]+)"), contribution=contribution,
                estimates={"buys": buys, "sells": sells,
                           "cash_left": round(contribution + sells - buys, 2) if contribution is not None else None},
                results=results,
                results_at=datetime.fromtimestamp(pp["result"].stat().st_mtime, timezone.utc).isoformat()
                           if results and pp["result"].exists() else None)


# ------------------------------------------------------------------ actions

def api_prepare(p):
    account = "live" if p.get("account") == "live" else "paper"
    for key in ("contribute", "deploy", "min_order"):
        value = p.get(key)
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
            raise ValueError("Enter a valid, non-negative euro amount.")
    pp, port = P(account), PORTS[account]
    if _uncertain(account):
        raise ValueError("The previous submission was interrupted. Check IBKR orders and holdings before resetting tracking in Account tools. Planning is paused until its starting point is reconciled.")
    # state hygiene: a previous prepare that was never executed gets rolled
    # back before we run again, so previews don't stack up in state
    if _pending(account) and pp["undo"].exists():
        restore_preview(pp)
    if pp["state"].exists():
        shutil.copy(pp["state"], pp["undo"])
    else:
        pp["undo"].write_bytes(b"")

    pp["pending"].write_text("0")  # failed previews cannot leave old orders approvable
    logs = []
    if p.get("fetch", True):
        ok, out = run_step(["fetch_prices.py"])
        logs.append(("python fetch_prices.py", out))
    cmd = ["rebalance.py", "--contribute", str(p.get("contribute", 0) or 0),
           "--ib", f"127.0.0.1:{port}",
           "--expect-account", account,          # hard account verification
           "--state", str(pp["state"]),
           "--orders-out", str(pp["orders"]),
           "--out", str(pp["report"])]
    if p.get("deploy"):
        cmd += ["--deploy", str(p["deploy"])]
    if p.get("min_order") is not None:      # 0 is a valid value, not "unset"
        cmd += ["--min-order", str(p["min_order"])]
    ok, out = run_step(cmd)
    logs.append(("python " + " ".join(cmd), out))
    if not ok:
        return {"ok": False, "account": account,
                "log": "\n\n".join(f"$ {c}\n{o}" for c, o in logs)}
    payload = report_payload(account, logs)
    if payload.get("ok"):
        # a "pending preview" only exists when something was actually staged
        pp["pending"].write_text("1" if payload.get("orders") else "0")
        payload["pending"] = _pending(account)
    return payload


def api_execute(p):
    account = "live" if p.get("account") == "live" else "paper"
    pp, port = P(account), PORTS[account]
    phrase = (p.get("confirm") or "").strip()
    if phrase != CONFIRM[account]:
        return {"ok": False, "not_submitted": True, "log": f"confirmation phrase wrong - type "
                                    f"exactly: {CONFIRM[account]}"}
    if not _pending(account) or not p.get("plan_id") or p["plan_id"] != plan_id(account):
        return {"ok": False, "not_submitted": True, "log": "This preview has changed or is no longer active. Create a new preview before approving orders."}
    try:
        orders = json.loads(pp["orders"].read_text())
    except Exception:
        return {"ok": False, "not_submitted": True, "log": "no staged orders found"}
    sel = p.get("selected", [])
    if not isinstance(sel, list) or any(type(i) is not int or i < 0 or i >= len(orders) for i in sel):
        return {"ok": False, "not_submitted": True, "log": "Choose valid orders from this preview."}
    chosen = [o for i, o in enumerate(orders) if i in sel]
    if not chosen:
        return {"ok": False, "not_submitted": True, "log": "no orders selected"}
    pp["approved"].write_text(json.dumps(chosen, indent=1))
    pp["result"].write_text("[]")            # clear stale results
    # Mark submission in progress durably. If it aborts, optimistic preview
    # units cannot be trusted: require a deliberate tracking reconciliation.
    # Normal filled/partial/working/failed order results exit successfully and
    # are reconciled by the existing engine; this guard is for process failure.
    pp["pending"].write_text("2")
    ok, out = run_step(["rebalance.py", "--execute", str(pp["approved"]),
                        "--ib", f"127.0.0.1:{port}", "--yes",
                        "--expect-account", account,
                        "--state", str(pp["state"]),
                        "--result-out", str(pp["result"])])
    # These exact engine messages occur before any order placement. Restore
    # the preview backup so ordinary preflight refusals preserve the market
    # reference and remain retryable, without requiring a baseline reset.
    preflight_prefixes = ("CANNOT REACH IB GATEWAY on ",
                          "ACCOUNT MISMATCH - nothing was done.",
                          "!! REFUSING to execute - orders are still open at the broker:",
                          "ib_async is not installed - ")
    not_submitted = not ok and any(line.startswith(preflight_prefixes)
                                   for line in out.splitlines())
    if not_submitted and pp["undo"].exists():
        restore_preview(pp)
        pp["pending"].write_text("0")
    elif ok:
        pp["pending"].write_text("0")        # state reflects executed orders
    try:
        results = json.loads(pp["result"].read_text())
    except Exception:
        results = []
    return {"ok": ok, "not_submitted": not_submitted, "log": out, "results": results, "account": account,
            "sent": len(chosen), "total": len(orders)}


def api_resync(p):
    """Re-baseline: today's portfolio becomes the reference (D back to 0)."""
    account = "live" if p.get("account") == "live" else "paper"
    pp, port = P(account), PORTS[account]
    ok, out = run_step(["rebalance.py", "--contribute", "0",
                        "--ib", f"127.0.0.1:{port}", "--reset-baseline",
                        "--expect-account", account,
                        "--state", str(pp["state"]),
                        "--orders-out", str(pp["orders"]),
                        "--out", str(pp["report"])])
    if not ok:
        return {"ok": False, "account": account, "log": out}
    pp["pending"].write_text("0")
    payload = report_payload(account, [("resync baseline", out)])
    payload["pending"] = _pending(account)
    return payload


def api_undo(p):
    account = "live" if p.get("account") == "live" else "paper"
    pp = P(account)
    if not _pending(account):
        return {"ok": False, "log": "There is no unsubmitted preview to discard."}
    if pp["undo"].exists():
        restore_preview(pp)
        pp["pending"].write_text("0")
        return {"ok": True, "log": f"{account} state restored from before "
                                   f"the last prepare"}
    return {"ok": False, "log": f"no undo snapshot for the {account} account"}


# ------------------------------------------------------------------ server

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):                       # quiet console
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html", "/rebalance"):
            body = (HERE / ("investing.html" if self.path == "/rebalance" else "workspace.html")).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._json({"ok": False, "log": "not found"}, 404)

    def do_POST(self):
        # Reject cross-site posts to this localhost app, including requests to
        # order endpoints. Same-origin browser calls and local CLI calls work.
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if host not in (f"127.0.0.1:{SERVER_PORT}", f"localhost:{SERVER_PORT}") or (
                origin and urlsplit(origin).netloc != host):
            self._json({"ok": False, "error": "Cross-origin request refused."}, 403)
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json":
            self._json({"ok": False, "error": "Use application/json."}, 415)
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if not 0 <= n <= 256000:
                raise ValueError()
        except ValueError:
            self._json({"ok": False, "error": "Request too large or invalid length."}, 413)
            return
        try:
            payload = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(payload, dict):
                raise ValueError()
        except Exception:
            self._json({"ok": False, "error": "Expected a JSON object."}, 400)
            return
        try:
            if self.path.startswith("/api/workspace/"):
                self._json(workspace.api(self.path.rsplit("/", 1)[-1], payload))
            elif self.path in ("/api/prepare", "/api/execute", "/api/resync", "/api/undo"):
                if not ACTION_LOCK.acquire(blocking=False):
                    self._json({"ok": False, "log": "Another investing action is running. Wait for it to finish."}, 409)
                    return
                try:
                    action = {"/api/prepare": api_prepare, "/api/execute": api_execute,
                              "/api/resync": api_resync, "/api/undo": api_undo}[self.path]
                    self._json(action(payload))
                finally:
                    ACTION_LOCK.release()
            elif self.path == "/api/where":
                self._json({"ok": True, "folder": HERE.name,
                            "path": str(HERE)})
            elif self.path == "/api/last":
                self._json(report_payload(
                    "live" if payload.get("account") == "live" else "paper",
                    []))
            else:
                self._json({"ok": False, "log": "unknown endpoint"}, 404)
        except ValueError as e:
            self._json({"ok": False, "error": str(e)}, 400)
        except Exception as e:
            self._json({"ok": False, "log": f"server error: {e}"}, 500)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", SERVER_PORT), Handler)
    url = f"http://127.0.0.1:{SERVER_PORT}"
    print(f"dashboard running at {url}   (Ctrl-C to stop)")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
