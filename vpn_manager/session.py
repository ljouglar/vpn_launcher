"""vpn_manager.session — VPN session tracking.

A session is represented by a single file at::

    ~/.vpn/sessions/.session_<vpn-id>

containing the PID of the running openfortivpn or ssh process.

This module provides functions to read, write and clean up session
files, plus helpers to check whether a process is still alive.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Tuple

from .config import SESSION_DIR
from .models import VpnEntry


# ── Low-level process helpers ────────────────────────────────


def is_process_alive(pid: int) -> bool:
    """Return True if *pid* refers to a running process."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        # ProcessLookupError → process does not exist
        # PermissionError   → process exists but we cannot signal it (still alive)
        return isinstance(SystemError, PermissionError)
    except OSError:
        return False


def _alive(pid: int) -> bool:
    """os.kill(pid, 0) — returns True if the process exists (any user)."""
    if pid <= 0:
        return False
    return Path(f"/proc/{pid}").is_dir()


def get_process_name(pid: int) -> str:
    """Return the executable name of *pid*, or empty string if unavailable."""
    try:
        return Path(f"/proc/{pid}/comm").read_text().strip()
    except OSError:
        return ""


# ── Session file helpers ─────────────────────────────────────


def session_path(vpn_id: str) -> Path:
    """Return the session file path for *vpn_id*."""
    return SESSION_DIR / f".session_{vpn_id}"


def read_session(vpn_id: str) -> Optional[int]:
    """Read the PID stored in the session file, or None.

    Automatically removes the file if the stored PID is dead.
    """
    path = session_path(vpn_id)
    if not path.exists():
        return None

    try:
        pid = int(path.read_text().strip())
    except (ValueError, OSError):
        _remove_session(vpn_id)
        return None

    if _alive(pid):
        return pid

    # Stale session — clean up silently
    _remove_session(vpn_id)
    return None


def write_session(vpn_id: str, pid: int) -> None:
    """Persist *pid* as the active session for *vpn_id*."""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    path = session_path(vpn_id)
    path.write_text(str(pid))
    path.chmod(0o600)


def _remove_session(vpn_id: str) -> None:
    """Delete the session file for *vpn_id* (best-effort)."""
    try:
        session_path(vpn_id).unlink()
    except OSError:
        pass


def remove_session(vpn_id: str) -> None:
    """Public alias for :func:`_remove_session`."""
    _remove_session(vpn_id)


# ── Higher-level API ─────────────────────────────────────────


def is_connected(vpn_id: str) -> bool:
    """Return True if a live session exists for *vpn_id*."""
    return read_session(vpn_id) is not None


def attach_session_state(entries: List[VpnEntry]) -> List[VpnEntry]:
    """Populate :attr:`VpnEntry.connected` and :attr:`VpnEntry.pid` in-place.

    Args:
        entries: List returned by :func:`vpn_manager.config.load_entries`.

    Returns:
        The same list, mutated for convenience.
    """
    for entry in entries:
        pid = read_session(entry.id)
        entry.connected = pid is not None
        entry.pid = pid
    return entries


def list_active_sessions() -> List[Tuple[str, int]]:
    """Return ``(vpn_id, pid)`` pairs for every live tracked session."""
    result: List[Tuple[str, int]] = []
    try:
        for path in SESSION_DIR.glob(".session_*"):
            vpn_id = path.name.removeprefix(".session_")
            pid = read_session(vpn_id)
            if pid is not None:
                result.append((vpn_id, pid))
    except OSError:
        pass
    return result


def cleanup_stale_sessions() -> int:
    """Remove session files whose processes are no longer alive.

    Returns:
        Number of stale files removed.
    """
    removed = 0
    try:
        for path in SESSION_DIR.glob(".session_*"):
            vpn_id = path.name.removeprefix(".session_")
            try:
                pid = int(path.read_text().strip())
            except (ValueError, OSError):
                path.unlink(missing_ok=True)
                removed += 1
                continue
            if not _alive(pid):
                path.unlink(missing_ok=True)
                removed += 1
    except OSError:
        pass
    return removed
