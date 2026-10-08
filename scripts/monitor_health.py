import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add scripts directory to path for send_ntfy import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from send_ntfy import send_ntfy

HEALTH_FILE = Path("/home/opc/AppExtrato/data/orchestrator-health.json")
STATE_FILE = Path("/home/opc/AppExtrato/data/monitor-state.json")
STALE_THRESHOLD_SECONDS = 300  # 5 minutes

def parse_iso_to_timestamp(iso_str: str) -> float:
    if not iso_str:
        return 0.0
    try:
        # Handle  Z or offset
        if iso_str.endswith("Z"):
            iso_str = iso_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(iso_str)
        return dt.timestamp()
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

def check_health(health_path: Path = HEALTH_FILE, state_path: Path = STATE_FILE, dry_run: bool = False) -> dict:
    health_data = load_json(health_path)
    state_data = load_json(state_path)

    processes = health_data.get("processes", {})
    extrato = processes.get("Extrato", {})

    state = extrato.get("state", "UNKNOWN")
    failures = extrato.get("consecutive_failures", 0)
    last_error = extrato.get("last_error") or ""
    last_success_at = extrato.get("last_success_at") or "N/A"
    last_check_at_str = extrato.get("last_check_at") or ""

    now = time.time()
    last_check_ts = parse_iso_to_timestamp(last_check_at_str)
    seconds_since_check = now - last_check_ts if last_check_ts > 0 else 0

    functional_alerted = state_data.get("functional_failure_alerted", False)
    stale_alerted = state_data.get("scheduler_stale_alerted", False)

    actions = []

    # 1. CAMADA 2: FALHA FUNCIONAL (consecutive_failures >= 3)
    if failures >= 3:
        if not functional_alerted:
            title = "🚨 AppExtrato — ERRO FUNCIONAL"
            msg = (
                f"Servidor: servidor-tesouraria-v2\n"
                f"Processo: Extrato\n"
                f"Estado: {state}\n"
                f"Falhas consecutivas: {failures}\n"
                f"Erro: {last_error[:300]}\n"
                f"Último sucesso: {last_success_at}\n"
                f"Última verificação: {last_check_at_str}"
            )
            actions.append(("FUNCTIONAL_ALERT", title, msg, "high", ["warning", "alert"]))
            if not dry_run:
                send_ntfy(title, msg, priority="high", tags=["warning", "alert"])
                state_data["functional_failure_alerted"] = True
    else:
        # Recuperação funcional
        if functional_alerted:
            title = "✅ AppExtrato — RECUPERADO"
            msg = (
                f"Servidor: servidor-tesouraria-v2\n"
                f"Processo: Extrato\n"
                f"Estado: {state}\n"
                f"Falhas consecutivas: {failures}\n"
                f"Última verificação: {last_check_at_str}"
            )
            actions.append(("FUNCTIONAL_RECOVERY", title, msg, "default", ["white_check_mark"]))
            if not dry_run:
                send_ntfy(title, msg, priority="default", tags=["white_check_mark"])
                state_data["functional_failure_alerted"] = False

    # 2. CAMADA 3: WATCHDOG DO SCHEDULER (last_check_at > 5 min)
    if last_check_ts > 0 and seconds_since_check > STALE_THRESHOLD_SECONDS:
        if not stale_alerted:
            minutes_stale = int(seconds_since_check // 60)
            title = "⚠️ AppExtrato — SCHEDULER SEM ATIVIDADE"
            msg = (
                f"Servidor: servidor-tesouraria-v2\n"
                f"Serviço: active\n"
                f"Último check: {last_check_at_str}\n"
                f"Tempo sem atividade: {minutes_stale} minutos"
            )
            actions.append(("STALE_ALERT", title, msg, "high", ["clock", "warning"]))
            if not dry_run:
                send_ntfy(title, msg, priority="high", tags=["clock", "warning"])
                state_data["scheduler_stale_alerted"] = True
    else:
        # Recuperação do scheduler
        if stale_alerted:
            title = "✅ AppExtrato — SCHEDULER RECUPERADO"
            msg = (
                f"Servidor: servidor-tesouraria-v2\n"
                f"Serviço: active\n"
                f"Último check: {last_check_at_str}"
            )
            actions.append(("STALE_RECOVERY", title, msg, "default", ["white_check_mark"]))
            if not dry_run:
                send_ntfy(title, msg, priority="default", tags=["white_check_mark"])
                state_data["scheduler_stale_alerted"] = False

    if not dry_run:
        save_json(state_path, state_data)

    return {
        "state": state,
        "failures": failures,
        "seconds_since_check": seconds_since_check,
        "actions": actions,
        "state_saved": state_data
    }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--health-file", type=Path, default=HEALTH_FILE)
    parser.add_argument("--state-file", type=Path, default=STATE_FILE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    res = check_health(args.health_file, args.state_file, args.dry_run)
    print(json.dumps(res, indent=2))
