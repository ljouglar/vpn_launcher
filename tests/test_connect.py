"""Tests for vpn_manager.connect."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from vpn_manager.models import (
    AuthType,
    FortiVpnConfig,
    SamlConfig,
    SshTunnelConfig,
    VpnEntry,
)
import vpn_manager.connect as conn


def _forti_entry(vpn_id: str = "vpn1", auth: AuthType = AuthType.PASSWORD) -> VpnEntry:
    return VpnEntry(
        id=vpn_id,
        name="Test VPN",
        auth=auth,
        index=1,
        forti_cfg=FortiVpnConfig(
            config_file="vpn1.conf",
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


def test_connect_password_starts_openfortivpn_and_passes_pid_finder(tmp_path):
    entry = _forti_entry()
    with (
        patch.object(conn, "CONFIG_DIR", tmp_path),
        patch.object(conn, "LOG_DIR", tmp_path),
        patch("vpn_manager.connect.subprocess.Popen") as mock_popen,
        patch("vpn_manager.connect.time.sleep"),
        patch("vpn_manager.connect._ppp_interfaces", return_value=[]),
        patch("vpn_manager.connect._find_openfortivpn_pid", return_value=4242) as mock_find_pid,
        patch("vpn_manager.connect._wait_for_ppp", return_value=True) as mock_wait,
    ):
        mock_popen.return_value = MagicMock()

        assert conn.connect_password(entry) is True

        args = mock_popen.call_args[0][0]
        assert args == ["sudo", "-b", "openfortivpn", "-c", str(tmp_path / "vpn1.conf")]

        wait_args, wait_kwargs = mock_wait.call_args
        assert wait_args[:6] == ("vpn1", 4242, [], tmp_path / "vpn1.log", conn.get_timeout(entry), print)
        assert wait_kwargs["pid_finder"]() == 4242
        mock_find_pid.assert_called_with("vpn1.conf")


def test_wait_for_ppp_retries_pid_lookup_before_writing_session(tmp_path):
    pid_finder = MagicMock(side_effect=[None, 4242])
    progress = MagicMock()

    with (
        patch("vpn_manager.connect._ppp_interfaces", side_effect=[[], ["ppp0"]]),
        patch("vpn_manager.connect._interface_ip", return_value="10.0.0.2"),
        patch("vpn_manager.connect._alive", return_value=True),
        patch("vpn_manager.connect.write_session") as mock_write_session,
        patch("vpn_manager.connect.time.sleep"),
    ):
        assert conn._wait_for_ppp(
            "vpn1",
            None,
            [],
            tmp_path / "vpn1.log",
            2,
            progress,
            pid_finder=pid_finder,
        )

    mock_write_session.assert_called_once_with("vpn1", 4242)


def test_wait_for_ppp_falls_back_to_unique_untracked_pid(tmp_path):
    progress = MagicMock()

    with (
        patch("vpn_manager.connect._ppp_interfaces", return_value=["ppp0"]),
        patch("vpn_manager.connect._interface_ip", return_value="10.0.0.2"),
        patch("vpn_manager.connect._find_single_untracked_openfortivpn_pid", return_value=5252),
        patch("vpn_manager.connect.write_session") as mock_write_session,
    ):
        assert conn._wait_for_ppp(
            "vpn1",
            None,
            [],
            tmp_path / "vpn1.log",
            1,
            progress,
        )

    mock_write_session.assert_called_once_with("vpn1", 5252)


def test_wait_for_ppp_fails_instead_of_writing_invalid_session(tmp_path):
    progress = MagicMock()

    with (
        patch("vpn_manager.connect._ppp_interfaces", return_value=["ppp0"]),
        patch("vpn_manager.connect._find_single_untracked_openfortivpn_pid", return_value=None),
        patch("vpn_manager.connect.write_session") as mock_write_session,
    ):
        assert not conn._wait_for_ppp(
            "vpn1",
            None,
            [],
            tmp_path / "vpn1.log",
            1,
            progress,
        )

    mock_write_session.assert_not_called()
    assert any("impossible d'associer le processus" in call.args[0] for call in progress.call_args_list)


def test_connect_dispatches_to_password():
    entry = _forti_entry(auth=AuthType.PASSWORD)
    with patch("vpn_manager.connect.connect_password") as mock_connect:
        conn.connect(entry, [entry])
        mock_connect.assert_called_once_with(entry, print)


def test_connect_dispatches_to_2fa():
    entry = _forti_entry(auth=AuthType.TWO_FA)
    with patch("vpn_manager.connect.connect_2fa") as mock_connect:
        conn.connect(entry, [entry], otp_code="123456")
        mock_connect.assert_called_once_with(entry, "123456", print)


def test_connect_dispatches_to_saml():
    entry = _saml_entry()
    with patch("vpn_manager.connect.connect_saml") as mock_connect:
        conn.connect(entry, [entry])
        mock_connect.assert_called_once_with(entry, print)


def test_connect_dispatches_to_ssh():
    entry = _ssh_entry()
    with patch("vpn_manager.connect.connect_ssh") as mock_connect:
        conn.connect(entry, [entry])
        mock_connect.assert_called_once_with(entry, print)
