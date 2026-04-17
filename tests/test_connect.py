"""Tests for vpn_manager.connect — subprocess commands built correctly."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call
import subprocess

import pytest

from vpn_manager.models import (
    AuthType,
    FortiVpnConfig,
    SamlConfig,
    SshTunnelConfig,
    VpnEntry,
)
import vpn_manager.connect as conn


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _forti_entry(vpn_id="vpn1", auth=AuthType.PASSWORD) -> VpnEntry:
    return VpnEntry(
        id=vpn_id,
        name="Test VPN",
        auth=auth,
        index=1,
        forti_cfg=FortiVpnConfig(
            config_file="/home/user/.vpn/configs/vpn1.conf",
            host="vpn.example.com",
            port=443,
            username="jdoe",
            password="s3cr3t",
            trusted_cert="aa:bb:cc",
        ),
    )


def _saml_entry() -> VpnEntry:
    return VpnEntry(
        id="saml-vpn",
        name="SAML VPN",
        auth=AuthType.SAML,
        index=2,
        saml_cfg=SamlConfig(saml_host="vpn.example.com:444", saml_cert="abc123"),
    )


def _ssh_entry() -> VpnEntry:
    return VpnEntry(
        id="ssh-tunnel",
        name="SSH Tunnel",
        auth=AuthType.SSH_TUNNEL,
        index=3,
        ssh_cfg=SshTunnelConfig(
            config_file=None,
            ssh_key="/home/user/.ssh/id_rsa",
            ssh_user="root",
            ssh_host="10.0.0.1",
            local_port=33070,
            remote_host="192.168.1.1",
            remote_port=3306,
        ),
    )


# ── Tests: connect_password ───────────────────────────────────────────────────


def test_connect_password_calls_openfortivpn(tmp_path):
    entry = _forti_entry(auth=AuthType.PASSWORD)
    with patch("vpn_manager.connect.subprocess.Popen") as mock_popen, \
         patch("vpn_manager.connect._wait_for_ppp") as mock_wait, \
         patch("vpn_manager.connect.write_session") as mock_ws:
        mock_proc = MagicMock()
        mock_proc.pid = 42
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        mock_wait.return_value = True

        conn.connect_password(entry)

        args = mock_popen.call_args[0][0]
        assert "openfortivpn" in args[0]
        assert "-c" in args
        assert "/home/user/.vpn/configs/vpn1.conf" in args
        mock_ws.assert_called_once_with("vpn1", 42)


def test_connect_password_passes_username(tmp_path):
    entry = _forti_entry(auth=AuthType.PASSWORD)
    with patch("vpn_manager.connect.subprocess.Popen") as mock_popen, \
         patch("vpn_manager.connect._wait_for_ppp", return_value=True), \
         patch("vpn_manager.connect.write_session"):
        mock_proc = MagicMock()
        mock_proc.pid = 1
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        conn.connect_password(entry)

        args = mock_popen.call_args[0][0]
        assert "--username=jdoe" in args or "-u" in args or "jdoe" in " ".join(args)


# ── Tests: connect_ssh ────────────────────────────────────────────────────────


def test_connect_ssh_calls_correct_command():
    entry = _ssh_entry()
    with patch("vpn_manager.connect.subprocess.Popen") as mock_popen, \
         patch("vpn_manager.connect.write_session") as mock_ws:
        mock_proc = MagicMock()
        mock_proc.pid = 99
        mock_popen.return_value = mock_proc

        conn.connect_ssh(entry)

        args = mock_popen.call_args[0][0]
        assert "ssh" in args[0]
        # Should contain port forwarding -L
        joined = " ".join(args)
        assert "-L" in joined or "33070" in joined
        assert "10.0.0.1" in joined
        mock_ws.assert_called_once_with("ssh-tunnel", 99)


def test_connect_ssh_uses_ssh_key():
    entry = _ssh_entry()
    with patch("vpn_manager.connect.subprocess.Popen") as mock_popen, \
         patch("vpn_manager.connect.write_session"):
        mock_proc = MagicMock()
        mock_proc.pid = 5
        mock_popen.return_value = mock_proc

        conn.connect_ssh(entry)

        joined = " ".join(mock_popen.call_args[0][0])
        assert "/home/user/.ssh/id_rsa" in joined or "-i" in joined


# ── Tests: connect dispatcher ────────────────────────────────────────────────


def test_connect_dispatches_to_password():
    entry = _forti_entry(auth=AuthType.PASSWORD)
    with patch("vpn_manager.connect.connect_password") as mock_cp:
        conn.connect(entry, [entry])
        mock_cp.assert_called_once()


def test_connect_dispatches_to_2fa():
    entry = _forti_entry(auth=AuthType.TWO_FA)
    with patch("vpn_manager.connect.connect_2fa") as mock_c2:
        conn.connect(entry, [entry], otp_code="123456")
        mock_c2.assert_called_once()


def test_connect_dispatches_to_ssh():
    entry = _ssh_entry()
    with patch("vpn_manager.connect.connect_ssh") as mock_cs:
        conn.connect(entry, [entry])
        mock_cs.assert_called_once()


def test_connect_raises_if_already_connected():
    entry = _forti_entry(auth=AuthType.PASSWORD)
    entry.connected = True
    with pytest.raises(RuntimeError, match="already connected|déjà connecté"):
        conn.connect(entry, [entry])
