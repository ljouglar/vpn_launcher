"""vpn_manager.status — Runtime status and orphan detection.

Provides functions used by both the CLI ``status`` command and the
system tray polling loop.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .config import SESSION_DIR
from .models import VpnEntry
from .session import _alive, list_active_sessions, read_session


# ── PPP interface helpers ────────────────────────────────────


def _ppp_interfaces() -> List[str]:
    result = subprocess.run(
        ["ip", "-o", "link", "show", "type", "ppp"],
        capture_output=True,
        text=True,
    )
    ifaces = []
    for line in result.stdout.splitlines():
        parts = line.split(": ")
        if len(parts) >= 2:
            ifaces.append(parts[1].strip())
    return ifaces


def _interface_ip(iface: str) -> str:
    result = subprocess.run(
        ["ip", "a", "show", iface],
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("inet "):
            return line.split()[1].split("/")[0]
    return ""


# ── Data structures ──────────────────────────────────────────


@dataclass
class ConnectedVpnInfo:
    """Runtime information for a tracked, connected VPN session."""

    entry: VpnEntry
    pid: int
    ip: str = ""          # IPv4 address (empty for SSH tunnels)
    interface: str = ""   # ppp interface name (empty for SSH tunnels)


@dataclass
class UntrackedProcess:
    """An openfortivpn process that is not tracked by a session file."""

    pid: int
    cmdline: str = ""
    ip: str = ""


# ── Public API ───────────────────────────────────────────────


def get_connected(entries: List[VpnEntry]) -> List[ConnectedVpnInfo]:
    """Return runtime info for every tracked, connected entry.

    Automatically matches ppp interfaces to VPN entries (by order).
    """
    result: List[ConnectedVpnInfo] = []
    ppp_ifaces = _ppp_interfaces()
    ppp_index = 0

    for entry in entries:
        if not entry.connected or entry.pid is None:
            continue

        info = ConnectedVpnInfo(entry=entry, pid=entry.pid)

        if entry.is_ssh_tunnel:
            # SSH tunnels have no ppp interface
            pass
        else:
            if ppp_index < len(ppp_ifaces):
                iface = ppp_ifaces[ppp_index]
                info.interface = iface
                info.ip = _interface_ip(iface)
                ppp_index += 1

        result.append(info)

    return result


def get_untracked_processes() -> List[UntrackedProcess]:
    """Return openfortivpn processes not tracked by any session file."""
    tracked_pids = {pid for _, pid in list_active_sessions()}

    result_ps = subprocess.run(
        ["ps", "aux"],
        capture_output=True,
        text=True,
    )

    untracked: List[UntrackedProcess] = []
    for line in result_ps.stdout.splitlines():
        parts = line.split()
        if len(parts) < 11:
            continue
        # Match lines where the binary name is exactly openfortivpn
        if parts[10] != "openfortivpn":
            continue
        try:
            pid = int(parts[1])
        except ValueError:
            continue

        if pid in tracked_pids:
            continue

        cmdline = " ".join(parts[10:])[:120]
        ppp_ifaces = _ppp_interfaces()
        ip = _interface_ip(ppp_ifaces[-1]) if ppp_ifaces else ""

        untracked.append(UntrackedProcess(pid=pid, cmdline=cmdline, ip=ip))

    return untracked


def count_connected(entries: List[VpnEntry]) -> int:
    """Return the number of currently connected entries."""
    return sum(1 for e in entries if e.connected)
