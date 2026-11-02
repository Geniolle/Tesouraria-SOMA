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
