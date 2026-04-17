"""vpn_manager.disconnect — VPN and SSH tunnel disconnection logic.

Provides:

* :func:`kill_process`      — send SIGTERM then SIGKILL to a process
* :func:`disconnect_one`    — disconnect a single VPN entry or raw PID
* :func:`disconnect_all`    — disconnect every active session (dependency-ordered)
* :func:`cleanup_orphans`   — kill untracked openfortivpn processes + stale ppp interfaces
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Callable, List, Optional

from .models import VpnEntry
from .session import (
    _alive,
    list_active_sessions,
    read_session,
    remove_session,
)


# ── Process helpers ──────────────────────────────────────────


def _process_owner(pid: int) -> str:
    """Return the username that owns *pid*, or empty string."""
    try:
        uid = Path(f"/proc/{pid}/status").read_text()
        for line in uid.splitlines():
            if line.startswith("Uid:"):
                real_uid = int(line.split()[1])
                import pwd
                return pwd.getpwuid(real_uid).pw_name
    except (OSError, KeyError, IndexError, ValueError):
        pass
    return ""


def _send_signal(pid: int, sig: int) -> None:
    """Send *sig* to *pid*, escalating to sudo if the process is owned by root."""
    owner = _process_owner(pid)
    if owner in ("root", ""):
        subprocess.run(["sudo", "kill", f"-{sig}", str(pid)], check=False)
    else:
        try:
            os.kill(pid, sig)
        except OSError:
            pass


def kill_process(
    pid: int,
    progress: Callable[[str], None] = print,
) -> bool:
    """Terminate *pid* gracefully (SIGTERM → SIGKILL).

    1. Send SIGTERM to process and its children.
    2. Wait up to 3 s.
    3. If still alive, send SIGKILL.
    4. Wait 2 s and report.

    Returns:
        True if the process is dead, False if it could not be killed.
    """
    import signal as _signal

    if not _alive(pid):
        return True

    # Kill children first
    try:
        children_result = subprocess.run(
            ["pgrep", "-P", str(pid)],
            capture_output=True,
            text=True,
        )
        children = [int(p) for p in children_result.stdout.splitlines() if p.strip()]
    except Exception:
        children = []

    for child in children:
        _send_signal(child, _signal.SIGTERM)

    _send_signal(pid, _signal.SIGTERM)
    time.sleep(3)

    if not _alive(pid):
        return True

    progress("Processus encore actif, envoi de SIGKILL…")
    for child in children:
        _send_signal(child, _signal.SIGKILL)
    _send_signal(pid, _signal.SIGKILL)
    time.sleep(2)

    if _alive(pid):
        progress(f"❌ Impossible de terminer le processus {pid}")
        progress(f"💡 Essayez manuellement : sudo kill -9 {pid}")
        return False

    return True


# ── Disconnect a single entry ────────────────────────────────


def disconnect_entry(
    entry: VpnEntry,
    all_entries: List[VpnEntry],
    ask_cascade: Callable[[List[str]], bool],
    progress: Callable[[str], None] = print,
) -> bool:
    """Disconnect *entry*, cascading to dependents if needed.

    Args:
        entry:       The entry to disconnect.
        all_entries: Full entry list (needed to find dependents).
        ask_cascade: Receives a list of dependent names and returns
                     True if they should be disconnected first.
        progress:    Status message callback.

    Returns:
        True on success.
    """
    pid = read_session(entry.id)
    if pid is None:
        progress(f"❌ {entry.name} n'est pas connecté")
        return False

    # Find connected dependents (entries that depend on this one)
    dependents = [
        e for e in all_entries
        if e.depends_on == entry.id and e.connected
    ]

    if dependents:
        dep_names = [e.name for e in dependents]
        progress(f"⚠️  Des connexions dépendent de {entry.name} : {', '.join(dep_names)}")
        if not ask_cascade(dep_names):
            progress("❌ Déconnexion annulée")
            return False
        for dep in dependents:
            disconnect_entry(dep, all_entries, ask_cascade, progress)

    progress(f"🔌 Déconnexion de {entry.name} (PID : {pid})…")
    if not kill_process(pid, progress):
        return False

    remove_session(entry.id)
    progress(f"✅ {entry.name} déconnecté")
    return True


def disconnect_by_pid(
    pid: int,
    progress: Callable[[str], None] = print,
) -> bool:
    """Disconnect a process by raw PID (for untracked / orphan processes).

    Only openfortivpn and ssh processes are accepted.

    Returns:
        True on success.
    """
    if not _alive(pid):
        progress(f"❌ Aucun processus avec le PID {pid}")
        return False

    proc_name_path = Path(f"/proc/{pid}/comm")
    proc_name = proc_name_path.read_text().strip() if proc_name_path.exists() else ""
    if proc_name not in ("openfortivpn", "ssh"):
        progress(f"❌ Le PID {pid} n'est pas un processus VPN ou tunnel SSH ({proc_name})")
        return False

    progress(f"🔌 Déconnexion du processus (PID : {pid})…")
    if not kill_process(pid, progress):
        return False

    # Clean up any stale session file pointing to this PID
    from .config import SESSION_DIR
    for path in SESSION_DIR.glob(".session_*"):
        try:
            if int(path.read_text().strip()) == pid:
                path.unlink(missing_ok=True)
        except (ValueError, OSError):
            pass

    progress("✅ Processus déconnecté")
    return True


# ── Disconnect all ───────────────────────────────────────────


def _topological_order(entries: List[VpnEntry]) -> List[VpnEntry]:
    """Return *entries* sorted so dependents come before their base VPN.

    This ensures we disconnect dependents before the VPN they rely on.
    """
    connected = [e for e in entries if e.connected]
    # Dependents first (have a depends_on), then base VPNs
    with_dep = [e for e in connected if e.depends_on]
    without_dep = [e for e in connected if not e.depends_on]
    return with_dep + without_dep


def disconnect_all(
    all_entries: List[VpnEntry],
    ask_cascade: Callable[[List[str]], bool],
    progress: Callable[[str], None] = print,
) -> int:
    """Disconnect every active session in dependency-safe order.

    Returns:
        Number of successfully disconnected entries.
    """
    ordered = _topological_order(all_entries)
    if not ordered:
        progress("❌ Aucune connexion active")
        return 0

    count = 0
    disconnected_ids: set[str] = set()

    for entry in ordered:
        if entry.id in disconnected_ids:
            continue
        # Skip cascade check — we are disconnecting everything
        pid = read_session(entry.id)
        if pid is None:
            continue
        progress(f"🔌 Déconnexion de {entry.name} (PID : {pid})…")
        if kill_process(pid, progress):
            remove_session(entry.id)
            progress(f"✅ {entry.name} déconnecté")
            disconnected_ids.add(entry.id)
            count += 1

    # Also kill untracked openfortivpn processes
    result = subprocess.run(["pgrep", "-x", "openfortivpn"], capture_output=True, text=True)
    for pid_str in result.stdout.splitlines():
        pid = int(pid_str.strip())
        if _alive(pid):
            progress(f"🔌 Processus non tracké (PID : {pid})…")
            if kill_process(pid, progress):
                count += 1

    return count


# ── Orphan cleanup ───────────────────────────────────────────


def cleanup_orphans(
    progress: Callable[[str], None] = print,
) -> int:
    """Kill untracked openfortivpn processes and remove orphan ppp interfaces.

    Returns:
        Number of items cleaned up.
    """
    cleaned = 0

    # Collect tracked PIDs
    tracked_pids = {pid for _, pid in list_active_sessions()}

    # 1. Kill untracked openfortivpn processes
    result = subprocess.run(["pgrep", "-x", "openfortivpn"], capture_output=True, text=True)
    for pid_str in result.stdout.splitlines():
        pid = int(pid_str.strip())
        if pid in tracked_pids:
            continue
        progress(f"  Arrêt du processus orphelin (PID : {pid})…")
        _send_signal(pid, 9)
        time.sleep(0.5)
        if not _alive(pid):
            cleaned += 1

    # 2. Remove orphan ppp interfaces (only if no openfortivpn is running)
    time.sleep(1)
    remaining = subprocess.run(["pgrep", "-x", "openfortivpn"], capture_output=True, text=True)
    if not remaining.stdout.strip():
        ifaces_result = subprocess.run(
            ["ip", "-o", "link", "show", "type", "ppp"],
            capture_output=True,
            text=True,
        )
        for line in ifaces_result.stdout.splitlines():
            parts = line.split(": ")
            if len(parts) >= 2:
                iface = parts[1].strip()
                progress(f"  Suppression de l'interface orpheline : {iface}")
                subprocess.run(["sudo", "ip", "link", "delete", iface], check=False)
                cleaned += 1

    # 3. Remove stale session files
    from .session import cleanup_stale_sessions
    stale = cleanup_stale_sessions()
    if stale:
        progress(f"  {stale} fichier(s) de session obsolète(s) supprimé(s)")
        cleaned += stale

    return cleaned
