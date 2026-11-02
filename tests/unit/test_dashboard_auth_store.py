import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dashboard"))

import auth_store  # noqa: E402
from auth_store import AuthStore, hash_password, verify_password  # noqa: E402


def test_password_hash_roundtrip() -> None:
    stored = hash_password("correct horse")
    assert "correct horse" not in stored
    assert verify_password("correct horse", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("x", "garbage")


def test_login_and_sessions(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "auth.db")
    store.set_password(" Ana@Example.PT ", "senha-segura-1")

    assert store.check_password("ana@example.pt", "senha-segura-1")
    assert not store.check_password("ana@example.pt", "outra")
    assert not store.check_password("ninguem@example.pt", "senha-segura-1")

    keep = store.create_session("ana@example.pt")
    drop = store.create_session("ana@example.pt")
    assert store.session_email(keep) == "ana@example.pt"
    store.delete_sessions("ana@example.pt", keep_token=keep)
    assert store.session_email(keep) == "ana@example.pt"
    assert store.session_email(drop) is None

    store.delete_user("ana@example.pt")
    assert store.session_email(keep) is None
    assert store.emails() == []


def test_expired_session_is_rejected(tmp_path: Path, monkeypatch) -> None:
    store = AuthStore(tmp_path / "auth.db")
    token = store.create_session("ana@example.pt")
    monkeypatch.setattr(auth_store.time, "time", lambda: 10**12)
    assert store.session_email(token) is None


def test_generated_password_must_be_changed(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "auth.db")
    store.set_password("ana@example.pt", "inicial-123", must_change=True)
    assert store.must_change("ana@example.pt")
    store.set_password("ana@example.pt", "escolhida-123")
    assert not store.must_change("ana@example.pt")
    assert not store.must_change("ninguem@example.pt")


def test_old_database_gets_must_change_column(tmp_path: Path) -> None:
    import sqlite3

    db = sqlite3.connect(tmp_path / "auth.db")
    db.execute(
        "CREATE TABLE users (email TEXT PRIMARY KEY, pw_hash TEXT NOT NULL, updated_at INTEGER NOT NULL)"
    )
    db.execute("INSERT INTO users VALUES ('ana@example.pt', 'x', 0)")
    db.commit()
    db.close()
    store = AuthStore(tmp_path / "auth.db")
    assert not store.must_change("ana@example.pt")


def test_accounts_report_state_and_last_login(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "auth.db")
    store.set_password("ana@example.pt", "inicial-123", must_change=True)
    assert store.accounts() == {"ana@example.pt": {"must_change": 1, "last_login": None}}
    store.create_session("ana@example.pt")
    assert store.accounts()["ana@example.pt"]["last_login"] is not None


def test_initial_password_from_env(monkeypatch) -> None:
    monkeypatch.delenv("DASHBOARD_INITIAL_PASSWORD", raising=False)
    assert len(auth_store.generate_password()) == 16
    monkeypatch.setenv("DASHBOARD_INITIAL_PASSWORD", "fixa-inicial")
    assert auth_store.generate_password() == "fixa-inicial"
