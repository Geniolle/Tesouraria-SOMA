"""
Unit tests for server diagnostics (scripts/server_diagnostics.py) and
continuous health monitoring (scripts/monitor_health.py).
"""

import json
from unittest.mock import MagicMock, patch

from scripts.monitor_health import check_health as monitor_check_health
from scripts.server_diagnostics import (
    check_scheduler_and_processes,
    check_service_logs,
    check_system_resources,
    check_systemd_service,
    redact_sensitive_data,
)


class TestServerDiagnostics:

    def test_redact_sensitive_data(self):
        sample = "DB_PASSWORD='super_secret_123' token=ghp_123456789012345678901234567890123456 Bearer eyJhbGci"
        redacted = redact_sensitive_data(sample)
        assert "super_secret_123" not in redacted
        assert "ghp_123456789012345678901234567890123456" not in redacted
        assert "[REDACTED]" in redacted

    @patch("subprocess.run")
    def test_check_systemd_service_active(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "ActiveState=active\nSubState=running\nMainPID=12345\nExecMainStartTimestamp=Thu 2026-10-08"
        mock_run.return_value = mock_proc

        res = check_systemd_service("appextrato.service")
        assert res["status"] == "OK"
        assert res["active_state"] == "active"
        assert res["pid"] == "12345"

    @patch("subprocess.run")
    def test_check_systemd_service_stopped(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "ActiveState=inactive\nSubState=dead\nMainPID=0"
        mock_run.return_value = mock_proc

        res = check_systemd_service("appextrato.service")
        assert res["status"] == "ERROR"
        assert res["active_state"] == "inactive"

    def test_check_scheduler_recent_health(self, tmp_path):
        health_file = tmp_path / "orchestrator-health.json"
        now_iso = "2026-10-08T20:00:00Z"
        health_data = {
            "last_tick": now_iso,
            "processes": {
                "Extrato": {
                    "state": "IDLE",
                    "consecutive_failures": 0,
                    "last_check_at": now_iso
                }
            }
        }
        health_file.write_text(json.dumps(health_data), encoding="utf-8")

        with patch("time.time", return_value=1791489610.0):  # 10s difference
            with patch("scripts.server_diagnostics.parse_iso_timestamp", return_value=1791489600.0):
                sched_res, proc_res, overall = check_scheduler_and_processes(health_file)
                assert sched_res["status"] == "OK"
                assert proc_res["Extrato"]["status"] == "OK"
                assert overall == "OK"

    def test_check_scheduler_stale_health(self, tmp_path):
        health_file = tmp_path / "orchestrator-health.json"
        health_data = {
            "last_tick": "2026-10-08T19:00:00Z",
            "processes": {
                "Extrato": {
                    "state": "FAILED",
                    "consecutive_failures": 3,
                    "last_error": "Connection timeout"
                }
            }
        }
        health_file.write_text(json.dumps(health_data), encoding="utf-8")

        with patch("time.time", return_value=1791489600.0):
            with patch("scripts.server_diagnostics.parse_iso_timestamp", return_value=1791489000.0):  # 600s ago
                sched_res, proc_res, overall = check_scheduler_and_processes(health_file)
                assert sched_res["status"] == "ERROR"
                assert proc_res["Extrato"]["status"] == "ERROR"
                assert overall == "ERROR"

    @patch("shutil.disk_usage")
    def test_check_system_resources_thresholds(self, mock_disk):
        mock_disk.return_value = MagicMock(total=100 * 1024**3, used=85 * 1024**3, free=15 * 1024**3)
        res = check_system_resources()
        assert res["disk"]["percent"] == 85.0
        assert res["disk"]["status"] == "WARNING"
        assert res["status"] in ("WARNING", "ERROR")

    @patch("subprocess.run")
    def test_check_service_logs_with_traceback(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Oct 08 20:00:00 host python[123]: Traceback (most recent call last):\nOct 08 20:00:00 host python[123]: Exception: Quota exceeded 429"
        mock_run.return_value = mock_proc

        res = check_service_logs("appextrato", max_lines=200)
        assert res["status"] in ("WARNING", "ERROR")
        assert len(res["errors_found"]) == 2


class TestMonitorHealth:

    @patch("scripts.monitor_health.send_ntfy")
    @patch("scripts.monitor_health.get_service_active_state")
    def test_monitor_health_alerts_and_deduplication(self, mock_svc, mock_send_ntfy, tmp_path):
        mock_svc.side_effect = lambda s: "inactive" if "appextrato" in s else "active"

        health_file = tmp_path / "health.json"
        state_file = tmp_path / "state.json"
        health_file.write_text(json.dumps({"processes": {}}), encoding="utf-8")

        # First run: should trigger notification
        res1 = monitor_check_health(health_file, state_file, dry_run=False)
        assert any(a[0] == "APPEXTRATO_DOWN" for a in res1["actions"])
        assert mock_send_ntfy.call_count >= 1

        # Second run: should NOT trigger duplicate notification
        mock_send_ntfy.reset_mock()
        res2 = monitor_check_health(health_file, state_file, dry_run=False)
        assert not any(a[0] == "APPEXTRATO_DOWN" for a in res2["actions"])
        assert mock_send_ntfy.call_count == 0

        # Third run: service recovers -> recovery notification
        mock_svc.side_effect = lambda s: "active"
        res3 = monitor_check_health(health_file, state_file, dry_run=False)
        assert any(a[0] == "APPEXTRATO_RECOVERED" for a in res3["actions"])
        assert mock_send_ntfy.call_count == 1

    @patch("scripts.monitor_health.send_ntfy")
    @patch("scripts.monitor_health.get_service_active_state")
    def test_monitor_health_runner_offline_alert(self, mock_svc, mock_send_ntfy, tmp_path):
        def svc_side_effect(s):
            if "runner" in s:
                return "failed"
            return "active"

        mock_svc.side_effect = svc_side_effect
        health_file = tmp_path / "health.json"
        state_file = tmp_path / "state.json"
        health_file.write_text(json.dumps({"processes": {}}), encoding="utf-8")

        res = monitor_check_health(health_file, state_file, dry_run=False)
        assert any(a[0] == "RUNNER_DOWN" for a in res["actions"])
        assert mock_send_ntfy.call_count >= 1
