"""Tests for vpn_manager.session — PID tracking helpers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from vpn_manager import session as sess
from vpn_manager.models import VpnEntry, AuthType, FortiVpnConfig


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_entry(vpn_id: str = "test-vpn") -> VpnEntry:
    return VpnEntry(
        id=vpn_id,
        name="Test VPN",
        auth=AuthType.PASSWORD,
        index=1,
        forti_cfg=FortiVpnConfig(
            config_file="test.conf",
            host="vpn.example.com",
            port=443,
            username="user",
            password="",
            trusted_cert="",
        ),
    )


# ── Tests: write / read / remove ──────────────────────────────────────────────


def test_write_and_read_session(tmp_path, monkeypatch):
    monkeypatch.setattr(sess, "SESSION_DIR", tmp_path)
    write_session = sess.write_session
    read_session = sess.read_session
    remove_session = sess.remove_session

    write_session("my-vpn", 12345)
    pid = read_session("my-vpn")
    assert pid == 12345

    remove_session("my-vpn")
    assert read_session("my-vpn") is None


def test_read_nonexistent_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(sess, "SESSION_DIR", tmp_path)
    assert sess.read_session("ghost") is None


def test_remove_nonexistent_does_not_raise(tmp_path, monkeypatch):
    monkeypatch.setattr(sess, "SESSION_DIR", tmp_path)
    sess.remove_session("ghost")  # Should not raise


# ── Tests: is_connected ───────────────────────────────────────────────────────


def test_is_connected_false_when_no_session(tmp_path, monkeypatch):
    monkeypatch.setattr(sess, "SESSION_DIR", tmp_path)
    assert sess.is_connected("my-vpn") is False


def test_is_connected_false_when_pid_dead(tmp_path, monkeypatch):
    monkeypatch.setattr(sess, "SESSION_DIR", tmp_path)
    sess.write_session("my-vpn", 999999999)  # Very large PID, almost certainly dead
    # _alive returns False for non-existent PIDs
    assert sess.is_connected("my-vpn") is False


def test_is_connected_true_when_pid_alive(tmp_path, monkeypatch):
    monkeypatch.setattr(sess, "SESSION_DIR", tmp_path)
    current_pid = os.getpid()
    sess.write_session("my-vpn", current_pid)
    assert sess.is_connected("my-vpn") is True


# ── Tests: attach_session_state ───────────────────────────────────────────────


def test_attach_session_state_connected(tmp_path, monkeypatch):
    monkeypatch.setattr(sess, "SESSION_DIR", tmp_path)
    entry = _make_entry("vpn-a")
    sess.write_session("vpn-a", os.getpid())
    result = sess.attach_session_state([entry])
    assert result[0].connected is True
    assert result[0].pid == os.getpid()


def test_attach_session_state_disconnected(tmp_path, monkeypatch):
    monkeypatch.setattr(sess, "SESSION_DIR", tmp_path)
    entry = _make_entry("vpn-b")
    result = sess.attach_session_state([entry])
    assert result[0].connected is False
    assert result[0].pid is None


# ── Tests: cleanup_stale_sessions ─────────────────────────────────────────────


def test_cleanup_removes_stale_pids(tmp_path, monkeypatch):
    monkeypatch.setattr(sess, "SESSION_DIR", tmp_path)
    # Write a session with a dead PID
    sess.write_session("stale", 999999999)
    stale_file = tmp_path / ".session_stale"
    assert stale_file.exists()

    sess.cleanup_stale_sessions()
    assert not stale_file.exists()


def test_cleanup_keeps_alive_pids(tmp_path, monkeypatch):
    monkeypatch.setattr(sess, "SESSION_DIR", tmp_path)
    sess.write_session("alive", os.getpid())
    alive_file = tmp_path / ".session_alive"
    assert alive_file.exists()

    sess.cleanup_stale_sessions()
    assert alive_file.exists()
