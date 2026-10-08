"""
Continuous Health Monitor for Tesouraria-SOMA.
Runs locally on the server (e.g. via systemd timer every 1 minute).

Checks:
- appextrato.service status
- actions.runner...service (GitHub Runner) status
- Scheduler staleness (WARNING > 120s, ERROR > 180s)
- Health file state & process consecutive failures
- Disk usage (WARNING >= 80%, ERROR >= 90%)
- Memory usage (WARNING >= 85%, ERROR >= 95%)
- Sends NTFY notifications on state change with deduplication & recovery alerts.

NOTE: This monitor does NOT attempt auto-restarts (read-only detection & alerting).
"""

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add scripts directory to path for send_ntfy import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from send_ntfy import send_ntfy

HEALTH_FILE = Path("/home/opc/AppExtrato/data/orchestrator-health.json")
STATE_FILE = Path("/home/opc/AppExtrato/data/monitor-state.json")

# Thresholds
SCHEDULER_WARN_SEC = 120
SCHEDULER_ERR_SEC = 180
DISK_WARN_PCT = 80.0
DISK_ERR_PCT = 90.0
MEM_WARN_PCT = 85.0
MEM_ERR_PCT = 95.0


def parse_iso_to_timestamp(iso_str: str) -> float:
    if not iso_str:
        return 0.0
    try:
        s = iso_str.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return 0.0


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_json(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving state to {path}: {e}", file=sys.stderr)


def get_service_active_state(service_name: str) -> str:
    """Check systemd service active state."""
    try:
        proc = subprocess.run(
            ["systemctl", "is-active", service_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5
        )
        return proc.stdout.strip() or "failed"
    except Exception:
        return "unknown"


def check_system_resources() -> tuple[float, float, str, float, str]:
    """Return (disk_pct, disk_status, mem_pct, mem_status)."""
    # Disk
    disk_pct = 0.0
    disk_st = "OK"
    try:
        stat = shutil.disk_usage("/")
        disk_pct = round((stat.used / stat.total) * 100, 1)
        if disk_pct >= DISK_ERR_PCT:
            disk_st = "ERROR"
        elif disk_pct >= DISK_WARN_PCT:
            disk_st = "WARNING"
    except Exception:
        pass

    # Memory
    mem_pct = 0.0
    mem_st = "OK"
    try:
        if os.path.exists("/proc/meminfo"):
            mem_info = {}
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        k = parts[0].strip()
                        v = parts[1].strip().split()[0]
                        if v.isdigit():
                            mem_info[k] = int(v)
            total = mem_info.get("MemTotal", 0)
            free = mem_info.get("MemFree", 0)
            buffers = mem_info.get("Buffers", 0)
            cached = mem_info.get("Cached", 0)
            available = mem_info.get("MemAvailable", free + buffers + cached)
            used = total - available
            if total > 0:
                mem_pct = round((used / total) * 100, 1)
                if mem_pct >= MEM_ERR_PCT:
                    mem_st = "ERROR"
                elif mem_pct >= MEM_WARN_PCT:
                    mem_st = "WARNING"
    except Exception:
        pass

    return disk_pct, disk_st, mem_pct, mem_st


def check_health(
    health_path: Path = HEALTH_FILE,
    state_path: Path = STATE_FILE,
    dry_run: bool = False,
    ntfy_env: str = "/etc/appextrato/ntfy.env"
) -> dict:
    health_data = load_json(health_path)
    state_data = load_json(state_path)

    now = time.time()
    hostname = os.uname().nodename if hasattr(os, "uname") else "servidor-tesouraria-v2"

    actions = []

    # 1. CHECK APPEXTRATO SERVICE
    appextrato_st = get_service_active_state("appextrato.service")
    appextrato_alerted = state_data.get("appextrato_alerted", False)

    if appextrato_st != "active":
        if not appextrato_alerted:
            title = "❌ TESOURARIA — AppExtrato parado"
            msg = (
                f"Host: {hostname}\n"
                f"Service: appextrato.service\n"
                f"Status: {appextrato_st}\n"
                f"Hora: {datetime.now(timezone.utc).isoformat()}"
            )
            actions.append(("APPEXTRATO_DOWN", title, msg, "high", ["alert", "x"]))
            if not dry_run:
                send_ntfy(title, msg, priority="high", tags=["alert", "x"], env_path=ntfy_env)
                state_data["appextrato_alerted"] = True
    else:
        if appextrato_alerted:
            title = "✅ TESOURARIA — AppExtrato recuperado"
            msg = (
                f"Host: {hostname}\n"
                f"Service: appextrato.service\n"
                f"Status: active\n"
                f"Hora: {datetime.now(timezone.utc).isoformat()}"
            )
            actions.append(("APPEXTRATO_RECOVERED", title, msg, "default", ["white_check_mark"]))
            if not dry_run:
                send_ntfy(title, msg, priority="default", tags=["white_check_mark"], env_path=ntfy_env)
                state_data["appextrato_alerted"] = False

    # 2. CHECK GITHUB RUNNER SERVICE
    runner_svc_name = "actions.runner.Geniolle-Tesouraria-SOMA.servidor-tesouraria-runner.service"
    runner_st = get_service_active_state(runner_svc_name)
    runner_alerted = state_data.get("runner_alerted", False)

    if runner_st != "active":
        if not runner_alerted:
            title = "⚠️ TESOURARIA — GitHub Runner offline"
            msg = (
                f"Host: {hostname}\n"
                f"Service: GitHub Actions Runner\n"
                f"Status: {runner_st}\n"
                f"Hora: {datetime.now(timezone.utc).isoformat()}"
            )
            actions.append(("RUNNER_DOWN", title, msg, "high", ["warning", "octocat"]))
            if not dry_run:
                send_ntfy(title, msg, priority="high", tags=["warning", "octocat"], env_path=ntfy_env)
                state_data["runner_alerted"] = True
    else:
        if runner_alerted:
            title = "✅ TESOURARIA — GitHub Runner recuperado"
            msg = (
                f"Host: {hostname}\n"
                f"Service: GitHub Actions Runner\n"
                f"Status: active\n"
                f"Hora: {datetime.now(timezone.utc).isoformat()}"
            )
            actions.append(("RUNNER_RECOVERED", title, msg, "default", ["white_check_mark"]))
            if not dry_run:
                send_ntfy(title, msg, priority="default", tags=["white_check_mark"], env_path=ntfy_env)
                state_data["runner_alerted"] = False

    # 3. CHECK SCHEDULER STALENESS & PROCESS FAILURES
    processes = health_data.get("processes", {})
    extrato = processes.get("Extrato", {})

    failures = extrato.get("consecutive_failures", 0)
    last_error = (extrato.get("last_error") or "")[:200]
    last_check_str = extrato.get("last_check_at") or health_data.get("last_tick") or ""

    last_check_ts = parse_iso_to_timestamp(last_check_str)
    seconds_since_check = now - last_check_ts if last_check_ts > 0 else 0

    stale_alerted = state_data.get("scheduler_stale_alerted", False)
    if last_check_ts > 0 and seconds_since_check > SCHEDULER_WARN_SEC:
        if not stale_alerted:
            minutes_stale = int(seconds_since_check // 60)
            title = "⚠️ TESOURARIA — Scheduler sem atividade"
            msg = (
                f"Host: {hostname}\n"
                f"Tempo sem atividade: {minutes_stale} min ({int(seconds_since_check)}s)\n"
                f"Última verificação: {last_check_str}"
            )
            actions.append(("SCHEDULER_STALE", title, msg, "high", ["clock", "warning"]))
            if not dry_run:
                send_ntfy(title, msg, priority="high", tags=["clock", "warning"], env_path=ntfy_env)
                state_data["scheduler_stale_alerted"] = True
    else:
        if stale_alerted:
            title = "✅ TESOURARIA — Scheduler recuperado"
            msg = f"Host: {hostname}\nÚltimo check: {last_check_str}"
            actions.append(("SCHEDULER_RECOVERED", title, msg, "default", ["white_check_mark"]))
            if not dry_run:
                send_ntfy(title, msg, priority="default", tags=["white_check_mark"], env_path=ntfy_env)
                state_data["scheduler_stale_alerted"] = False

    # 4. PROCESS CONSECUTIVE FAILURES (failures >= 3)
    functional_alerted = state_data.get("functional_failure_alerted", False)
    if failures >= 3:
        if not functional_alerted:
            title = "🚨 TESOURARIA — Falha Funcional em Processo"
            msg = (
                f"Host: {hostname}\n"
                f"Falhas consecutivas: {failures}\n"
                f"Último Erro: {last_error}"
            )
            actions.append(("FUNCTIONAL_FAIL", title, msg, "high", ["warning", "alert"]))
            if not dry_run:
                send_ntfy(title, msg, priority="high", tags=["warning", "alert"], env_path=ntfy_env)
                state_data["functional_failure_alerted"] = True
    else:
        if functional_alerted:
            title = "✅ TESOURARIA — Processos recuperados"
            msg = f"Host: {hostname}\nTodas as tarefas operacionais normais."
            actions.append(("FUNCTIONAL_RECOVERED", title, msg, "default", ["white_check_mark"]))
            if not dry_run:
                send_ntfy(title, msg, priority="default", tags=["white_check_mark"], env_path=ntfy_env)
                state_data["functional_failure_alerted"] = False

    # 5. DISK & MEMORY THRESHOLDS
    disk_pct, disk_st, mem_pct, mem_st = check_system_resources()

    disk_alerted = state_data.get("disk_alerted", False)
    if disk_st in ("WARNING", "ERROR"):
        if not disk_alerted:
            title = f"⚠️ TESOURARIA — Disco em nível crítico ({disk_pct}%)"
            msg = f"Host: {hostname}\nUso do disco principal: {disk_pct}%"
            actions.append(("DISK_WARN", title, msg, "high", ["floppy_disk", "warning"]))
            if not dry_run:
                send_ntfy(title, msg, priority="high", tags=["floppy_disk", "warning"], env_path=ntfy_env)
                state_data["disk_alerted"] = True
    else:
        if disk_alerted:
            state_data["disk_alerted"] = False

    mem_alerted = state_data.get("mem_alerted", False)
    if mem_st in ("WARNING", "ERROR"):
        if not mem_alerted:
            title = f"⚠️ TESOURARIA — Memória em nível alto ({mem_pct}%)"
            msg = f"Host: {hostname}\nUso de RAM: {mem_pct}%"
            actions.append(("MEM_WARN", title, msg, "high", ["warning"]))
            if not dry_run:
                send_ntfy(title, msg, priority="high", tags=["warning"], env_path=ntfy_env)
                state_data["mem_alerted"] = True
    else:
        if mem_alerted:
            state_data["mem_alerted"] = False

    if not dry_run:
        save_json(state_path, state_data)

    return {
        "appextrato_status": appextrato_st,
        "runner_status": runner_st,
        "seconds_since_check": round(seconds_since_check, 1),
        "consecutive_failures": failures,
        "disk_percent": disk_pct,
        "mem_percent": mem_pct,
        "actions": actions,
        "state_saved": state_data
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Tesouraria Local Health Watchdog")
    parser.add_argument("--health-file", type=Path, default=HEALTH_FILE)
    parser.add_argument("--state-file", type=Path, default=STATE_FILE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    res = check_health(args.health_file, args.state_file, args.dry_run)
    print(json.dumps(res, indent=2))
