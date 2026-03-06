#!/usr/bin/env python3
"""Backend for VPN Tray — interfaces with vpn_launcher shell scripts.

Reads VPN configuration from ~/.vpn/vpns.conf (INI format),
checks session files in ~/.vpn/sessions/, and delegates
connect/disconnect actions to the vpn CLI script.
"""

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

# ── Paths ────────────────────────────────────────────────────

VPN_DIR = Path.home() / ".vpn"
VPN_CONF = VPN_DIR / "vpns.conf"
CONFIG_DIR = VPN_DIR / "configs"
SESSION_DIR = VPN_DIR / "sessions"
LOG_DIR = VPN_DIR / "logs"


# ── Data model ───────────────────────────────────────────────

@dataclass
class VpnEntry:
    """Represents a VPN or SSH tunnel from the configuration file."""

    id: str
    name: str
    auth: str  # password | 2fa | saml | ssh_tunnel
    index: int  # 1-based position in the config file
    connected: bool = False
    pid: Optional[int] = None
    depends_on: Optional[str] = None
    # SSH tunnel specific fields
    local_port: Optional[int] = None
    remote_host: Optional[str] = None
    remote_port: Optional[int] = None


# ── Script discovery ─────────────────────────────────────────

def find_vpn_script() -> Optional[str]:
    """Locate the vpn launcher script."""
    candidates = [
        Path.home() / "vpn",
        Path(__file__).resolve().parent.parent / "vpn",
    ]
    for candidate in candidates:
        try:
            resolved = candidate.resolve() if candidate.is_symlink() else candidate
            if resolved.exists() and os.access(str(resolved), os.X_OK):
                return str(candidate)
        except OSError:
            continue
    return None


# ── Configuration parser ─────────────────────────────────────


def _parse_key_value_file(path: Path) -> dict:
    """Parse a key = value config file (comments and blanks ignored)."""
    props = {}
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                kv = re.match(r"^([a-zA-Z0-9_]+)\s*=\s*(.+)$", line)
                if kv:
                    props[kv.group(1)] = kv.group(2).strip()
    except OSError:
        pass
    return props


def parse_config() -> List[VpnEntry]:
    """Parse ~/.vpn/vpns.conf (INI format) and return VPN entries.

    Mirrors the bash INI parser in lib/config.sh exactly:
    - Sections: [a-zA-Z0-9_-]+
    - Keys: [a-zA-Z0-9_]+
    - Comments start with #
    """
    if not VPN_CONF.exists():
        return []

    entries: List[VpnEntry] = []
    current_section: Optional[str] = None
    props: dict = {}
    sections: list = []

    with open(VPN_CONF, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Section header
            match = re.match(r"^\[([a-zA-Z0-9_-]+)\]$", line)
            if match:
                if current_section:
                    sections.append((current_section, dict(props)))
                current_section = match.group(1)
                props = {}
                continue

            # Key = value
            if current_section:
                kv = re.match(r"^([a-zA-Z0-9_]+)\s*=\s*(.+)$", line)
                if kv:
                    props[kv.group(1)] = kv.group(2).strip()

    if current_section:
        sections.append((current_section, dict(props)))

    for idx, (section_id, section_props) in enumerate(sections, 1):
        entry = VpnEntry(
            id=section_id,
            name=section_props.get("name", section_id),
            auth=section_props.get("auth", "password"),
            index=idx,
            depends_on=section_props.get("depends_on"),
        )
        # Parse SSH tunnel fields (from config file or inline)
        if entry.auth == "ssh_tunnel":
            tunnel_props = dict(section_props)
            # If a config file is referenced, parse it and merge
            config_file = section_props.get("config")
            if config_file:
                config_path = CONFIG_DIR / config_file
                if config_path.exists():
                    tunnel_props.update(_parse_key_value_file(config_path))
            try:
                entry.local_port = int(tunnel_props.get("local_port", 0))
                entry.remote_host = tunnel_props.get("remote_host")
                entry.remote_port = int(tunnel_props.get("remote_port", 0))
            except (ValueError, TypeError):
                pass
        entries.append(entry)

    return entries


# ── Session / process checks ────────────────────────────────

def is_process_alive(pid: int) -> bool:
    """Check whether a process is running via /proc."""
    return Path(f"/proc/{pid}").is_dir()


def check_session(vpn_id: str) -> Tuple[bool, Optional[int]]:
    """Check if a VPN session is active.

    Returns (connected, pid).
    Cleans up stale session files automatically.
    """
    session_file = SESSION_DIR / f".session_{vpn_id}"
    if not session_file.exists():
        return False, None

    try:
        pid = int(session_file.read_text().strip())
    except (ValueError, OSError):
        return False, None

    if is_process_alive(pid):
        return True, pid

    # Stale session — clean up
    try:
        session_file.unlink()
    except OSError:
        pass
    return False, None


def get_all_vpn_status() -> List[VpnEntry]:
    """Return all configured VPNs with their live connection status."""
    entries = parse_config()
    for entry in entries:
        connected, pid = check_session(entry.id)
        entry.connected = connected
        entry.pid = pid
    return entries


def count_connected() -> int:
    """Count currently connected VPNs."""
    return sum(1 for e in get_all_vpn_status() if e.connected)


# ── Sudo helper ──────────────────────────────────────────────

def can_sudo_without_password() -> bool:
    """Return True if sudo credentials are currently cached."""
    try:
        result = subprocess.run(
            ["sudo", "-n", "true"],
            capture_output=True,
            timeout=3,
        )
        return result.returncode == 0
    except Exception:
        return False


# ── Terminal discovery ───────────────────────────────────────

def _find_terminal() -> Optional[List[str]]:
    """Find an available terminal emulator and return its argv prefix.

    Returns None if no terminal is found.
    """
    terminals = [
        ("gnome-terminal", ["gnome-terminal", "--"]),
        ("x-terminal-emulator", ["x-terminal-emulator", "-e"]),
        ("xterm", ["xterm", "-e"]),
    ]
    for cmd, argv in terminals:
        try:
            if subprocess.run(
                ["which", cmd], capture_output=True, timeout=3
            ).returncode == 0:
                return argv
        except Exception:
            continue
    return None


# ── VPN actions ──────────────────────────────────────────────

def connect_vpn(entry: VpnEntry, script_path: str) -> Optional[subprocess.Popen]:
    """Launch a VPN connection in a terminal window.

    A terminal is always required because the connection flow may
    prompt for a sudo password, a 2FA code, or open a SAML browser.
    """
    terminal = _find_terminal()
    if not terminal:
        return None

    cmd_str = (
        f'"{script_path}" connect {entry.index}; '
        'echo ""; '
        'echo "Appuyez sur Entrée pour fermer…"; '
        "read"
    )
    return subprocess.Popen(terminal + ["bash", "-c", cmd_str])


def disconnect_vpn(
    entry: VpnEntry, script_path: str
) -> Optional[subprocess.Popen]:
    """Disconnect a VPN.

    If sudo credentials are cached, the disconnect runs silently.
    Otherwise a terminal is opened for the sudo prompt.
    """
    if can_sudo_without_password():
        return subprocess.Popen(
            [script_path, "disconnect", entry.id],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    terminal = _find_terminal()
    if not terminal:
        return None

    cmd_str = f'"{script_path}" disconnect {entry.id}; sleep 2'
    return subprocess.Popen(terminal + ["bash", "-c", cmd_str])


def disconnect_all_vpns(script_path: str) -> Optional[subprocess.Popen]:
    """Disconnect every active VPN."""
    if can_sudo_without_password():
        return subprocess.Popen(
            [script_path, "disconnect", "all"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    terminal = _find_terminal()
    if not terminal:
        return None

    cmd_str = f'"{script_path}" disconnect all; sleep 2'
    return subprocess.Popen(terminal + ["bash", "-c", cmd_str])
