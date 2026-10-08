"""
Server Diagnostics Script for Tesouraria-SOMA.
Runs comprehensive read-only diagnostics on the production server.
Outputs human-readable text to stdout and structured JSON to data/server-diagnostics.json.
Exit codes:
  0 = OK
  1 = WARNING
  2 = ERROR
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Force UTF-8 stdout encoding where possible
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Sensitivity redaction patterns
REDACT_PATTERNS = [
    (re.compile(r'(?i)(password|passwd|token|auth|bearer|cookie|secret|private_key|refresh_token)\s*[:=]\s*["\']?[^\s"\'&,]+["\']?'), r'\1=[REDACTED]'),
    (re.compile(r'Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*'), 'Bearer [REDACTED]'),
    (re.compile(r'ghp_[A-Za-z0-9]{36}'), 'ghp_[REDACTED]'),
    (re.compile(r'gho_[A-Za-z0-9]{36}'), 'gho_[REDACTED]'),
]


def redact_sensitive_data(text: str) -> str:
    """Sanitize sensitive strings (passwords, tokens, keys)."""
    if not text:
        return ""
    sanitized = text
    for pattern, replacement in REDACT_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def run_cmd(cmd: list[str], timeout: int = 10) -> tuple[int, str, str]:
    """Execute command safely and return (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as e:
        return -1, "", str(e)


def check_systemd_service(service_name: str) -> dict:
    """Check systemd service status safely."""
    # First try systemctl show for exact properties
    rc, out, _ = run_cmd(["systemctl", "show", service_name, "--property=ActiveState,SubState,MainPID,ExecMainStartTimestamp"])

    properties = {}
    if rc == 0 and out:
        for line in out.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                properties[k.strip()] = v.strip()

    active_state = properties.get("ActiveState", "unknown")
    sub_state = properties.get("SubState", "unknown")
    main_pid = properties.get("MainPID", "0")
    uptime = properties.get("ExecMainStartTimestamp", "N/A")

    # If systemctl show didn't return active state, fallback to systemctl is-active
    if active_state == "unknown":
        rc_active, is_act_out, _ = run_cmd(["systemctl", "is-active", service_name])
        if rc_active == 0:
            active_state = is_act_out
        else:
            active_state = is_act_out or "failed"

    status_flag = "OK"
    if active_state == "active":
        status_flag = "OK"
    elif active_state in ("activating", "deactivating", "reloading"):
        status_flag = "WARNING"
    else:
        status_flag = "ERROR"

    return {
        "service": service_name,
        "active_state": active_state,
        "sub_state": sub_state,
        "pid": main_pid,
        "started_at": uptime,
        "status": status_flag
    }


def check_system_resources() -> dict:
    """Check disk, memory, and CPU metrics."""
    res = {
        "status": "OK",
        "disk": {"percent": 0.0, "used_gb": 0.0, "total_gb": 0.0, "status": "OK"},
        "memory": {"percent": 0.0, "used_mb": 0.0, "total_mb": 0.0, "status": "OK"},
        "cpu": {"load_1m": 0.0, "status": "OK"}
    }

    # Disk usage
    try:
        stat = shutil.disk_usage("/")
        disk_pct = round((stat.used / stat.total) * 100, 1)
        res["disk"] = {
            "percent": disk_pct,
            "used_gb": round(stat.used / (1024**3), 2),
            "total_gb": round(stat.total / (1024**3), 2),
            "status": "ERROR" if disk_pct >= 90 else ("WARNING" if disk_pct >= 80 else "OK")
        }
    except Exception as e:
        res["disk"]["error"] = str(e)

    # Memory usage
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
            mem_pct = round((used / total) * 100, 1) if total > 0 else 0.0
            res["memory"] = {
                "percent": mem_pct,
                "used_mb": round(used / 1024, 1),
                "total_mb": round(total / 1024, 1),
                "status": "ERROR" if mem_pct >= 95 else ("WARNING" if mem_pct >= 85 else "OK")
            }
    except Exception as e:
        res["memory"]["error"] = str(e)

    # CPU load average
    try:
        load1, _, _ = os.getloadavg()
        res["cpu"] = {
            "load_1m": round(load1, 2),
            "status": "WARNING" if load1 > 8.0 else "OK"
        }
    except Exception:
        pass

    # Overall system status
    statuses = [res["disk"]["status"], res["memory"]["status"], res["cpu"]["status"]]
    if "ERROR" in statuses:
        res["status"] = "ERROR"
    elif "WARNING" in statuses:
        res["status"] = "WARNING"

    return res


def parse_iso_timestamp(iso_str: str) -> float:
    if not iso_str:
        return 0.0
    try:
        s = iso_str.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return 0.0


def check_scheduler_and_processes(health_file_path: Path) -> tuple[dict, dict, str]:
    """Inspect orchestrator health JSON and process states."""
    scheduler_res = {
        "last_check_at": "N/A",
        "seconds_since_last_tick": -1,
        "status": "UNKNOWN"
    }
    processes_res = {}
    overall = "OK"

    if not health_file_path.exists():
        scheduler_res["status"] = "ERROR"
        scheduler_res["error"] = f"Health file not found at {health_file_path}"
        return scheduler_res, processes_res, "ERROR"

    try:
        with open(health_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        processes = data.get("processes", {})
        extrato = processes.get("Extrato", {})
        last_check_str = extrato.get("last_check_at") or data.get("last_tick") or ""

        scheduler_res["last_check_at"] = last_check_str
        if last_check_str:
            ts = parse_iso_timestamp(last_check_str)
            if ts > 0:
                diff = time.time() - ts
                scheduler_res["seconds_since_last_tick"] = round(diff, 1)
                if diff > 180:
                    scheduler_res["status"] = "ERROR"
                    overall = "ERROR"
                elif diff > 120:
                    scheduler_res["status"] = "WARNING"
                    if overall != "ERROR":
                        overall = "WARNING"
                else:
                    scheduler_res["status"] = "OK"

        for p_name, p_data in processes.items():
            st = p_data.get("state", "UNKNOWN")
            fails = p_data.get("consecutive_failures", 0)
            err = redact_sensitive_data(p_data.get("last_error") or "")

            p_status = "OK"
            if fails >= 3 or st == "FAILED":
                p_status = "ERROR"
                overall = "ERROR"
            elif fails > 0 or st == "DEGRADED":
                p_status = "WARNING"
                if overall != "ERROR":
                    overall = "WARNING"

            processes_res[p_name] = {
                "state": st,
                "consecutive_failures": fails,
                "last_run": p_data.get("last_run_at", "N/A"),
                "last_success": p_data.get("last_success_at", "N/A"),
                "last_error": err[:200] if err else "",
                "status": p_status
            }

    except Exception as e:
        scheduler_res["status"] = "ERROR"
        scheduler_res["error"] = str(e)
        overall = "ERROR"

    return scheduler_res, processes_res, overall


def check_git_repository(repo_dir: Path) -> dict:
    """Inspect git branch, SHA, status, and origin sync without exposing secrets."""
    git_res = {
        "branch": "unknown",
        "head_sha": "unknown",
        "clean": True,
        "modified_files": [],
        "origin_sha": "unknown",
        "sync_state": "unknown",
        "status": "OK"
    }

    if not (repo_dir / ".git").exists():
        git_res["status"] = "WARNING"
        git_res["error"] = f"Not a git repository: {repo_dir}"
        return git_res

    # 1. Current branch
    _, branch, _ = run_cmd(["git", "-C", str(repo_dir), "branch", "--show-current"])
    git_res["branch"] = branch or "master"

    # 2. HEAD SHA
    _, head_sha, _ = run_cmd(["git", "-C", str(repo_dir), "rev-parse", "HEAD"])
    git_res["head_sha"] = head_sha

    # 3. Porcelain status (safely extract modified file names, exclude .env from list output)
    _, status_out, _ = run_cmd(["git", "-C", str(repo_dir), "status", "--porcelain"])
    if status_out:
        git_res["clean"] = False
        files = []
        for line in status_out.splitlines():
            line = line.strip()
            if line:
                parts = line.split(maxsplit=1)
                fname = parts[1] if len(parts) > 1 else parts[0]
                # Filter out sensitive or .env file names from git status output
                if not fname.endswith(".env") and "credentials" not in fname.lower():
                    files.append(fname)
                else:
                    files.append("[REDACTED_SENSITIVE_FILE]")
        git_res["modified_files"] = files

    # 4. Fetch origin & check remote SHA
    run_cmd(["git", "-C", str(repo_dir), "fetch", "origin", git_res["branch"]], timeout=5)
    _, origin_sha, _ = run_cmd(["git", "-C", str(repo_dir), "rev-parse", f"origin/{git_res['branch']}"])
    git_res["origin_sha"] = origin_sha

    if head_sha and origin_sha:
        if head_sha == origin_sha:
            git_res["sync_state"] = "synced"
        else:
            rc_anc, _, _ = run_cmd(["git", "-C", str(repo_dir), "merge-base", "--is-ancestor", origin_sha, "HEAD"])
            if rc_anc == 0:
                git_res["sync_state"] = "ahead"
            else:
                rc_anc_rev, _, _ = run_cmd(["git", "-C", str(repo_dir), "merge-base", "--is-ancestor", head_sha, f"origin/{git_res['branch']}"])
                if rc_anc_rev == 0:
                    git_res["sync_state"] = "behind"
                else:
                    git_res["sync_state"] = "diverged"

    return git_res


def check_service_logs(service_name: str = "appextrato", max_lines: int = 200) -> dict:
    """Analyze recent journalctl logs for keywords and errors, sanitizing outputs."""
    keywords = [
        "Traceback", "ERROR", "CRITICAL", "RESOURCE_EXHAUSTED",
        "quota", "429", "failed", "exception", "Batch write failed",
        "Transfer failed", "CONTAORDEM", "T_EXTRATO"
    ]

    log_res = {
        "lines_analyzed": 0,
        "errors_found": [],
        "status": "OK"
    }

    # Fetch journalctl logs
    rc, out, _ = run_cmd(["journalctl", "-u", service_name, "-n", str(max_lines), "--no-pager"])
    if rc != 0 or not out:
        # Fallback to local log file if available
        fallback_log = Path("/home/opc/AppExtrato/logs/gmail-to-sheets.log")
        if fallback_log.exists():
            try:
                with open(fallback_log, "r", encoding="utf-8") as f:
                    lines = f.readlines()[-max_lines:]
                    out = "".join(lines)
            except Exception:
                out = ""

    if not out:
        return log_res

    lines = out.splitlines()
    log_res["lines_analyzed"] = len(lines)

    error_entries = []
    for line in lines:
        line_clean = redact_sensitive_data(line)
        # Check if line matches critical keywords
        if any(kw.lower() in line_clean.lower() for kw in keywords):
            error_entries.append(line_clean[:300])

    log_res["errors_found"] = error_entries[-10:]  # keep top 10 recent errors

    if len(error_entries) > 0:
        # If tracebacks or critical errors exist in recent logs
        has_critical = any(kw.lower() in " ".join(error_entries).lower() for kw in ["traceback", "critical", "resource_exhausted"])
        log_res["status"] = "ERROR" if has_critical else "WARNING"

    return log_res


def run_full_diagnostics(
    repo_dir: Path = Path("/home/opc/AppExtrato"),
    health_file: Path = Path("/home/opc/AppExtrato/data/orchestrator-health.json"),
    output_json_path: Path = Path("data/server-diagnostics.json")
) -> tuple[dict, int]:
    """Run all diagnostics and return (json_dict, exit_code)."""
    hostname = os.uname().nodename if hasattr(os, "uname") else os.getenv("COMPUTERNAME", "localhost")

    # 1. Services
    appextrato_svc = check_systemd_service("appextrato.service")
    runner_svc = check_systemd_service("actions.runner.Geniolle-Tesouraria-SOMA.servidor-tesouraria-runner.service")

    # 2. System Resources
    system_res = check_system_resources()

    # 3. Scheduler & Processes
    sched_res, proc_res, proc_overall = check_scheduler_and_processes(health_file)

    # 4. Git Repo
    git_res = check_git_repository(repo_dir)

    # 5. Log Analysis
    logs_res = check_service_logs("appextrato", max_lines=200)

    # Overall Status Calculation
    all_statuses = [
        appextrato_svc["status"],
        runner_svc["status"],
        system_res["status"],
        sched_res["status"],
        proc_overall,
        git_res["status"],
        logs_res["status"]
    ]

    if "ERROR" in all_statuses:
        overall_status = "ERROR"
        exit_code = 2
    elif "WARNING" in all_statuses:
        overall_status = "WARNING"
        exit_code = 1
    else:
        overall_status = "OK"
        exit_code = 0

    diagnostics_data = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "hostname": hostname,
        "overall_status": overall_status,
        "services": {
            "appextrato": appextrato_svc,
            "github_runner": runner_svc
        },
        "scheduler": sched_res,
        "system": system_res,
        "processes": proc_res,
        "git": git_res,
        "logs": logs_res
    }

    # Save to JSON
    try:
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(diagnostics_data, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save diagnostics JSON to {output_json_path}: {e}", file=sys.stderr)

    return diagnostics_data, exit_code


def print_human_report(diag: dict) -> None:
    """Print readable terminal report."""
    status_str = diag["overall_status"]
    status_label = f"OK [{status_str}]" if status_str == "OK" else status_str

    print("\n" + "=" * 70)
    print(f"  TESOURARIA-SOMA SERVER DIAGNOSTICS — {diag['timestamp']}")
    print(f"  Hostname: {diag['hostname']}")
    print(f"  Overall Status: {status_label}")
    print("=" * 70 + "\n")

    # Services
    print("SERVICES:")
    for name, s in diag.get("services", {}).items():
        print(f"  - {name}: [{s['status']}] {s['active_state']} (PID: {s['pid']})")

    # Scheduler
    sched = diag.get("scheduler", {})
    sec_tick = sched.get("seconds_since_last_tick", -1)
    tick_str = f"{sec_tick}s ago" if sec_tick >= 0 else "N/A"
    print(f"\nSCHEDULER: [{sched.get('status')}] Last tick {tick_str}")

    # System Resources
    sys_info = diag.get("system", {})
    disk = sys_info.get("disk", {})
    mem = sys_info.get("memory", {})
    print("\nSYSTEM RESOURCES:")
    print(f"  - Disk:   [{disk.get('status')}] {disk.get('percent', 0)}% ({disk.get('used_gb', 0)}GB / {disk.get('total_gb', 0)}GB)")
    print(f"  - Memory: [{mem.get('status')}] {mem.get('percent', 0)}% ({mem.get('used_mb', 0)}MB / {mem.get('total_mb', 0)}MB)")

    # Git Status
    git = diag.get("git", {})
    print("\nGIT REPOSITORY:")
    print(f"  - Branch: {git.get('branch')} | SHA: {git.get('head_sha', '')[:7]} | Sync: {git.get('sync_state')} | Clean: {git.get('clean')}")

    # Log Errors
    logs = diag.get("logs", {})
    err_count = len(logs.get("errors_found", []))
    print("\nLOG ANALYSIS:")
    print(f"  - Lines analyzed: {logs.get('lines_analyzed')}")
    print(f"  - Errors found in last 200 lines: {err_count}")
    if err_count > 0:
        print("  - Recent log errors:")
        for err_line in logs["errors_found"][-5:]:
            print(f"    * {err_line[:120]}")

    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Tesouraria Server Diagnostics")
    parser.add_argument("--repo-dir", type=Path, default=Path("/home/opc/AppExtrato"))
    parser.add_argument("--health-file", type=Path, default=Path("/home/opc/AppExtrato/data/orchestrator-health.json"))
    parser.add_argument("--output-json", type=Path, default=Path("data/server-diagnostics.json"))
    args = parser.parse_args()

    # Fallback to local repo path if running in workspace development environment
    repo_path = args.repo_dir
    if not repo_path.exists():
        repo_path = Path(__file__).resolve().parent.parent

    health_path = args.health_file
    if not health_path.exists():
        health_path = repo_path / "data" / "orchestrator-health.json"

    diag_data, code = run_full_diagnostics(
        repo_dir=repo_path,
        health_file=health_path,
        output_json_path=args.output_json
    )

    print_human_report(diag_data)
    sys.exit(code)
