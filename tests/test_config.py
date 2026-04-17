"""Tests for vpn_manager.config — INI parser and entry loading."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from vpn_manager.config import load_entries, get_entry_by_id, get_entry_by_index
from vpn_manager.models import AuthType


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def conf_dir(tmp_path: Path) -> Path:
    """Return a temp directory containing a vpns.conf and a configs/ subdir."""
    (tmp_path / "configs").mkdir()
    return tmp_path


def write_conf(conf_dir: Path, content: str) -> Path:
    path = conf_dir / "vpns.conf"
    path.write_text(textwrap.dedent(content))
    return path


# ── Tests: basic parsing ──────────────────────────────────────────────────────


def test_empty_file_returns_no_entries(conf_dir):
    conf = write_conf(conf_dir, "# just a comment\n")
    assert load_entries(conf) == []


def test_password_entry(conf_dir):
    conf = write_conf(
        conf_dir,
        """
        [my-vpn]
        name = My VPN
        auth = password
        config = my-vpn.conf
        """,
    )
    entries = load_entries(conf)
    assert len(entries) == 1
    e = entries[0]
    assert e.id == "my-vpn"
    assert e.name == "My VPN"
    assert e.auth == AuthType.PASSWORD
    assert e.index == 1
    assert e.forti_cfg is not None
    assert e.forti_cfg.config_file == "my-vpn.conf"


def test_2fa_entry(conf_dir):
    conf = write_conf(
        conf_dir,
        """
        [vpn-2fa]
        name = VPN 2FA
        auth = 2fa
        config = vpn-2fa.conf
        """,
    )
    entries = load_entries(conf)
    assert entries[0].auth == AuthType.TWO_FA


def test_saml_entry(conf_dir):
    conf = write_conf(
        conf_dir,
        """
        [my-saml]
        name = SAML VPN
        auth = saml
        saml_host = vpn.example.com:444
        saml_cert = deadbeef
        """,
    )
    e = load_entries(conf)[0]
    assert e.auth == AuthType.SAML
    assert e.saml_cfg is not None
    assert e.saml_cfg.saml_host == "vpn.example.com:444"
    assert e.saml_cfg.saml_cert == "deadbeef"


def test_ssh_tunnel_entry_inline(conf_dir):
    conf = write_conf(
        conf_dir,
        """
        [my-tunnel]
        name = DB Tunnel
        auth = ssh_tunnel
        ssh_key = /home/user/.ssh/id_rsa
        ssh_user = root
        ssh_host = 10.0.0.1
        local_port = 33070
        remote_host = 192.168.1.1
        remote_port = 3306
        """,
    )
    e = load_entries(conf)[0]
    assert e.auth == AuthType.SSH_TUNNEL
    assert e.ssh_cfg is not None
    assert e.ssh_cfg.local_port == 33070
    assert e.ssh_cfg.remote_port == 3306
    assert e.ssh_cfg.remote_host == "192.168.1.1"


def test_ssh_tunnel_entry_from_config_file(conf_dir):
    # Write auxiliary config file
    (conf_dir / "configs" / "tunnel.conf").write_text(
        "ssh_key = /home/user/.ssh/id_rsa\n"
        "ssh_user = root\n"
        "ssh_host = 10.0.0.1\n"
        "local_port = 5432\n"
        "remote_host = db.internal\n"
        "remote_port = 5432\n"
    )
    # Monkey-patch CONFIG_DIR
    import vpn_manager.config as cfg_mod
    orig = cfg_mod.CONFIG_DIR
    cfg_mod.CONFIG_DIR = conf_dir / "configs"

    conf = write_conf(
        conf_dir,
        """
        [pg-tunnel]
        name = PG Tunnel
        auth = ssh_tunnel
        config = tunnel.conf
        """,
    )
    try:
        e = load_entries(conf)[0]
    finally:
        cfg_mod.CONFIG_DIR = orig

    assert e.ssh_cfg.ssh_host == "10.0.0.1"
    assert e.ssh_cfg.local_port == 5432


def test_depends_on(conf_dir):
    conf = write_conf(
        conf_dir,
        """
        [base-vpn]
        name = Base VPN
        auth = saml
        saml_host = vpn.example.com:444

        [tunnel]
        name = DB Tunnel
        auth = ssh_tunnel
        ssh_key = /k
        ssh_user = u
        ssh_host = h
        local_port = 100
        remote_host = r
        remote_port = 200
        depends_on = base-vpn
        """,
    )
    entries = load_entries(conf)
    assert entries[0].depends_on is None
    assert entries[1].depends_on == "base-vpn"


def test_multiple_entries_have_correct_indexes(conf_dir):
    conf = write_conf(
        conf_dir,
        """
        [vpn-a]
        name = A
        auth = password
        config = a.conf

        [vpn-b]
        name = B
        auth = saml
        saml_host = b.example.com

        [vpn-c]
        name = C
        auth = ssh_tunnel
        ssh_key=/k
        ssh_user=u
        ssh_host=h
        local_port=1
        remote_host=r
        remote_port=2
        """,
    )
    entries = load_entries(conf)
    assert [e.index for e in entries] == [1, 2, 3]


def test_unknown_auth_type_is_skipped(conf_dir):
    conf = write_conf(
        conf_dir,
        """
        [bad-vpn]
        name = Bad
        auth = magic
        """,
    )
    assert load_entries(conf) == []


def test_get_entry_by_id(conf_dir):
    conf = write_conf(conf_dir, "[my-vpn]\nname=X\nauth=saml\nsaml_host=h\n")
    assert get_entry_by_id("my-vpn", conf) is not None
    assert get_entry_by_id("missing", conf) is None


def test_get_entry_by_index(conf_dir):
    conf = write_conf(conf_dir, "[my-vpn]\nname=X\nauth=saml\nsaml_host=h\n")
    assert get_entry_by_index(1, conf) is not None
    assert get_entry_by_index(0, conf) is None
    assert get_entry_by_index(99, conf) is None
