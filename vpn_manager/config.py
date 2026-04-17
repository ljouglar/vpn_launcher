"""vpn_manager.config — Single INI parser for vpns.conf.

This module replaces both lib/config.sh and tray/vpn_backend.py's
duplicate parsing logic. It is the only place in the project that
reads ~/.vpn/vpns.conf and ~/.vpn/configs/*.conf.

Format mirrors the original Bash parser exactly:
  - Sections:  [a-zA-Z0-9_-]+
  - Keys:      [a-zA-Z0-9_]+
  - Comments:  lines starting with #
  - Values:    trailing whitespace stripped
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from .models import (
    AuthType,
    FortiVpnConfig,
    SamlConfig,
    SshTunnelConfig,
    VpnEntry,
)

# ── Default filesystem paths ─────────────────────────────────

VPN_DIR = Path.home() / ".vpn"
VPN_CONF = VPN_DIR / "vpns.conf"
CONFIG_DIR = VPN_DIR / "configs"
SESSION_DIR = VPN_DIR / "sessions"
LOG_DIR = VPN_DIR / "logs"

# Default connection timeout (seconds) per auth type
DEFAULT_TIMEOUTS: Dict[AuthType, int] = {
    AuthType.PASSWORD: 20,
    AuthType.TWO_FA: 30,
    AuthType.SAML: 60,
    AuthType.SSH_TUNNEL: 15,
}

# Skeleton config written to vpns.conf when it does not exist yet
_CONF_SKELETON = """\
# VPN Manager — configuration
# Format : [vpn-id]
#   name       = Displayed name
#   auth       = password | 2fa | saml | ssh_tunnel
#   config     = filename.conf     (password / 2fa / ssh_tunnel)
#   saml_host  = host:port         (saml)
#   saml_cert  = sha256-fingerprint (saml, auto-detected if omitted)
#   depends_on = other-vpn-id      (optional)
#
# Run  vpn configure  to create your first VPN interactively.
"""

# ── Internal helpers ─────────────────────────────────────────

_SECTION_RE = re.compile(r"^\[([a-zA-Z0-9_-]+)\]$")
_KV_RE = re.compile(r"^([a-zA-Z0-9_]+)\s*=\s*(.+)$")


def _parse_kv_file(path: Path) -> Dict[str, str]:
    """Parse a ``key = value`` file; skip blank lines and ``#`` comments."""
    result: Dict[str, str] = {}
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = _KV_RE.match(line)
            if m:
                result[m.group(1)] = m.group(2).strip()
    except OSError:
        pass
    return result


def _parse_ini(path: Path) -> List[tuple[str, Dict[str, str]]]:
    """Parse an INI file into an ordered list of (section_id, props) tuples."""
    sections: List[tuple[str, Dict[str, str]]] = []
    current_id: Optional[str] = None
    current_props: Dict[str, str] = {}

    try:
        lines = path.read_text().splitlines()
    except OSError:
        return sections

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        m = _SECTION_RE.match(line)
        if m:
            if current_id is not None:
                sections.append((current_id, current_props))
            current_id = m.group(1)
            current_props = {}
            continue

        if current_id is not None:
            kv = _KV_RE.match(line)
            if kv:
                current_props[kv.group(1)] = kv.group(2).strip()

    if current_id is not None:
        sections.append((current_id, current_props))

    return sections


# ── Public API ───────────────────────────────────────────────


def ensure_config_dir() -> None:
    """Create the ~/.vpn directory structure if it does not exist."""
    for directory in (VPN_DIR, CONFIG_DIR, SESSION_DIR, LOG_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    if not VPN_CONF.exists():
        VPN_CONF.write_text(_CONF_SKELETON)
        VPN_CONF.chmod(0o600)


def load_entries(conf_path: Path = VPN_CONF) -> List[VpnEntry]:
    """Parse *conf_path* and return a list of :class:`VpnEntry` objects.

    SSH tunnel entries have their ``~/.vpn/configs/<file>.conf`` merged in
    automatically so callers never have to read auxiliary files themselves.

    Args:
        conf_path: Path to the INI config file (defaults to ``~/.vpn/vpns.conf``).

    Returns:
        Ordered list of VpnEntry objects, one per ``[section]`` in the file.
        Returns an empty list if the file does not exist.
    """
    if not conf_path.exists():
        return []

    entries: List[VpnEntry] = []

    for index, (section_id, props) in enumerate(_parse_ini(conf_path), start=1):
        raw_auth = props.get("auth", "password")
        try:
            auth = AuthType(raw_auth)
        except ValueError:
            # Unknown auth type — skip entry rather than crash
            continue

        entry = VpnEntry(
            id=section_id,
            name=props.get("name", section_id),
            auth=auth,
            index=index,
            depends_on=props.get("depends_on") or None,
        )

        if auth in (AuthType.PASSWORD, AuthType.TWO_FA):
            config_file = props.get("config", "")
            entry.forti_cfg = FortiVpnConfig(config_file=config_file)
            if config_file:
                cfg_path = CONFIG_DIR / config_file
                cfg = _parse_kv_file(cfg_path)
                entry.forti_cfg.host = cfg.get("host", "")
                entry.forti_cfg.port = int(cfg.get("port", 443))
                entry.forti_cfg.username = cfg.get("username", "")
                entry.forti_cfg.password = cfg.get("password", "")
                entry.forti_cfg.trusted_cert = cfg.get("trusted-cert", "")

        elif auth == AuthType.SAML:
            entry.saml_cfg = SamlConfig(
                saml_host=props.get("saml_host", ""),
                saml_cert=props.get("saml_cert", ""),
            )

        elif auth == AuthType.SSH_TUNNEL:
            config_file = props.get("config", "")
            entry.ssh_cfg = SshTunnelConfig(config_file=config_file)
            # Merge aux config file first, then allow inline overrides
            merged = {}
            if config_file:
                merged = _parse_kv_file(CONFIG_DIR / config_file)
            merged.update(props)  # inline props win
            entry.ssh_cfg.ssh_key = merged.get("ssh_key", "")
            entry.ssh_cfg.ssh_user = merged.get("ssh_user", "")
            entry.ssh_cfg.ssh_host = merged.get("ssh_host", "")
            try:
                entry.ssh_cfg.local_port = int(merged.get("local_port", 0))
                entry.ssh_cfg.remote_port = int(merged.get("remote_port", 0))
            except (ValueError, TypeError):
                pass
            entry.ssh_cfg.remote_host = merged.get("remote_host", "")

        entries.append(entry)

    return entries


def get_entry_by_id(vpn_id: str, conf_path: Path = VPN_CONF) -> Optional[VpnEntry]:
    """Return the VpnEntry with the given *vpn_id*, or None."""
    return next((e for e in load_entries(conf_path) if e.id == vpn_id), None)


def get_entry_by_index(index: int, conf_path: Path = VPN_CONF) -> Optional[VpnEntry]:
    """Return the VpnEntry at the given 1-based *index*, or None."""
    entries = load_entries(conf_path)
    if 1 <= index <= len(entries):
        return entries[index - 1]
    return None


def get_timeout(entry: VpnEntry) -> int:
    """Return the connection timeout in seconds for *entry*."""
    return DEFAULT_TIMEOUTS.get(entry.auth, 20)
