"""vpn_manager.connect — VPN and SSH tunnel connection logic.

Each public function handles one authentication / connection type:

* :func:`connect_password` — openfortivpn with password in config file
* :func:`connect_2fa`      — openfortivpn with additional OTP prompt
* :func:`connect_saml`     — openfortivpn with SAML/SSO browser flow
* :func:`connect_ssh`      — SSH local port-forwarding tunnel

:func:`connect` dispatches to the correct function based on the entry's
auth type and handles pre-connection dependency checks.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional

from .config import CONFIG_DIR, LOG_DIR, get_timeout
from .models import AuthType, VpnEntry
from .session import is_connected, write_session, _alive

# ── Browser helper ───────────────────────────────────────────

_BROWSER_COMMANDS = [
    "xdg-open",
    "gnome-open",
    "kde-open",
    "firefox",
    "google-chrome",
    "chromium",
]


def open_browser(url: str) -> bool:
    """Try to open *url* in the default browser.  Returns True on success."""
    for cmd in _BROWSER_COMMANDS:
        if shutil.which(cmd):
            subprocess.Popen(
                [cmd, url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
    return False


# ── Auto-detect SSL certificate ──────────────────────────────


def _fetch_cert(host: str, port: int) -> str:
    """Return the SHA-256 fingerprint of the server certificate (lowercase, no colons).

    Returns an empty string if detection fails.
    """
    result = subprocess.run(
        ["openssl", "s_client", "-connect", f"{host}:{port}", "-servername", host],
        input=b"",
        capture_output=True,
        timeout=10,
    )
    cert_proc = subprocess.run(
        ["openssl", "x509", "-noout", "-fingerprint", "-sha256"],
        input=result.stdout,
        capture_output=True,
        timeout=5,
    )
    line = cert_proc.stdout.decode(errors="replace")
    # Format: "SHA256 Fingerprint=AB:CD:..."
    if "=" in line:
        return line.split("=", 1)[1].strip().replace(":", "").lower()
    return ""


# ── PID discovery helpers ────────────────────────────────────


def _find_openfortivpn_pid(config_basename: str) -> Optional[int]:
    """Return the PID of the openfortivpn process using *config_basename*.

    We look for the real openfortivpn process (not the sudo wrapper).
    """
    result = subprocess.run(
        ["pgrep", "-x", "openfortivpn"],
        capture_output=True,
        text=True,
    )
    for pid_str in result.stdout.splitlines():
        pid = int(pid_str.strip())
        try:
            args = Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace")
            if config_basename in args:
                return pid
        except OSError:
            continue
    return None


def _find_openfortivpn_pid_by_host(host: str) -> Optional[int]:
    """Return the PID of the openfortivpn process for the given *host*."""
    result = subprocess.run(
        ["pgrep", "-x", "openfortivpn"],
        capture_output=True,
        text=True,
    )
    for pid_str in result.stdout.splitlines():
        pid = int(pid_str.strip())
        try:
            args = Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace")
            if host in args:
                return pid
        except OSError:
            continue
    return None


def _find_ssh_tunnel_pid(local_port: int, remote_host: str, remote_port: int, ssh_user: str, ssh_host: str) -> Optional[int]:
    """Return the PID of the ssh process for the given tunnel parameters."""
    pattern = f"ssh.*-L {local_port}:{remote_host}:{remote_port}.*{ssh_user}@{ssh_host}"
    result = subprocess.run(
        ["pgrep", "-f", pattern],
        capture_output=True,
        text=True,
    )
    pids = result.stdout.splitlines()
    return int(pids[0].strip()) if pids else None


# ── Interface detection ──────────────────────────────────────


def _ppp_interfaces() -> List[str]:
    """Return the current list of ppp interface names."""
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
    return sorted(ifaces)


def _interface_ip(iface: str) -> str:
    """Return the IPv4 address of *iface*, or empty string."""
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


# ── Wait for connection ──────────────────────────────────────


def _wait_for_ppp(
    vpn_id: str,
    vpn_pid: Optional[int],
    ifaces_before: List[str],
    log_path: Path,
    timeout: int,
    progress: Callable[[str], None],
) -> bool:
    """Poll until a new ppp interface appears or *timeout* seconds elapse.

    Args:
        vpn_id:        Entry ID used to persist the session.
        vpn_pid:       PID to watch for early crash detection.
        ifaces_before: ppp interface list captured before launch.
        log_path:      openfortivpn log file (for error context on failure).
        timeout:       Maximum seconds to wait.
        progress:      Callback called with a status string each second.

    Returns:
        True on successful connection, False otherwise.
    """
    for _ in range(timeout):
        ifaces_after = _ppp_interfaces()
        new_ifaces = [i for i in ifaces_after if i not in ifaces_before]
        if new_ifaces:
            iface = new_ifaces[0]
            ip = _interface_ip(iface)
            write_session(vpn_id, vpn_pid or 0)
            progress(f"✅ Connecté (IP: {ip}, interface: {iface})")
            return True

        # Early crash detection
        if vpn_pid and not _alive(vpn_pid):
            progress(f"❌ Le processus openfortivpn s'est arrêté\n📝 Logs : {log_path}")
            return False

        progress(".")
        time.sleep(1)

    progress(f"❌ Timeout : connexion non établie après {timeout}s\n📝 Logs : {log_path}")
    if vpn_pid:
        subprocess.run(["sudo", "kill", "-INT", str(vpn_pid)], check=False)
    return False


# ── Public connect functions ─────────────────────────────────


def connect_password(
    entry: VpnEntry,
    progress: Callable[[str], None] = print,
) -> bool:
    """Connect using openfortivpn with a config file (password mode).

    Args:
        entry:    VpnEntry with :attr:`forti_cfg` populated.
        progress: Callback for status messages (defaults to print).

    Returns:
        True on success.
    """
    assert entry.forti_cfg, "forti_cfg must be set for password auth"
    config_path = CONFIG_DIR / entry.forti_cfg.config_file
    log_path = LOG_DIR / f"{entry.id}.log"
    ifaces_before = _ppp_interfaces()

    subprocess.Popen(
        ["sudo", "-b", "openfortivpn", "-c", str(config_path)],
        stdout=log_path.open("w"),
        stderr=subprocess.STDOUT,
    )
    time.sleep(2)

    vpn_pid = _find_openfortivpn_pid(entry.forti_cfg.config_file)
    progress(f"🚀 Connexion à {entry.name}…")
    return _wait_for_ppp(entry.id, vpn_pid, ifaces_before, log_path, get_timeout(entry), progress)


def connect_2fa(
    entry: VpnEntry,
    otp_code: str,
    progress: Callable[[str], None] = print,
) -> bool:
    """Connect using openfortivpn with an OTP code.

    Args:
        entry:    VpnEntry with :attr:`forti_cfg` populated.
        otp_code: Time-based OTP (FortiToken code).
        progress: Callback for status messages.

    Returns:
        True on success.
    """
    assert entry.forti_cfg, "forti_cfg must be set for 2fa auth"
    config_path = CONFIG_DIR / entry.forti_cfg.config_file
    log_path = LOG_DIR / f"{entry.id}.log"
    ifaces_before = _ppp_interfaces()

    subprocess.Popen(
        ["sudo", "-b", "openfortivpn", "-c", str(config_path), f"--otp={otp_code}"],
        stdout=log_path.open("w"),
        stderr=subprocess.STDOUT,
    )
    time.sleep(2)

    vpn_pid = _find_openfortivpn_pid(entry.forti_cfg.config_file)
    progress(f"🚀 Connexion à {entry.name} (2FA)…")
    return _wait_for_ppp(entry.id, vpn_pid, ifaces_before, log_path, get_timeout(entry), progress)


def connect_saml(
    entry: VpnEntry,
    progress: Callable[[str], None] = print,
) -> bool:
    """Connect using openfortivpn with SAML/SSO browser authentication.

    Launches openfortivpn in background, waits for the SAML URL to appear
    in the log, opens the browser, then waits for the ppp interface.

    Args:
        entry:    VpnEntry with :attr:`saml_cfg` populated.
        progress: Callback for status messages.

    Returns:
        True on success.
    """
    assert entry.saml_cfg, "saml_cfg must be set for saml auth"
    cfg = entry.saml_cfg
    log_path = LOG_DIR / f"{entry.id}.log"
    ifaces_before = _ppp_interfaces()

    # Parse host and port
    if ":" in cfg.saml_host:
        host, port_str = cfg.saml_host.rsplit(":", 1)
        port = int(port_str)
    else:
        host, port = cfg.saml_host, 443

    # Auto-detect certificate if not configured
    saml_cert = cfg.saml_cert
    if not saml_cert:
        progress(f"🔍 Récupération du certificat de {host}:{port}…")
        try:
            saml_cert = _fetch_cert(host, port)
            if saml_cert:
                progress(f"✅ Certificat détecté : {saml_cert[:16]}…")
        except Exception:
            pass

    cmd = ["sudo", "-b", "openfortivpn", cfg.saml_host, "--saml-login"]
    if saml_cert:
        cmd += ["--trusted-cert", saml_cert]

    subprocess.Popen(cmd, stdout=log_path.open("w"), stderr=subprocess.STDOUT)
    time.sleep(2)

    vpn_pid = _find_openfortivpn_pid_by_host(host)

    # Wait for the SAML URL to appear in the log (up to 10 s)
    auth_url: Optional[str] = None
    for _ in range(10):
        try:
            content = log_path.read_text(errors="replace")
            import re
            m = re.search(r"Authenticate at '([^']+)'", content)
            if m:
                auth_url = m.group(1)
                break
        except OSError:
            pass
        progress(".")
        time.sleep(1)

    if not auth_url:
        progress(f"❌ Impossible de récupérer l'URL SAML\n📝 Logs : {log_path}")
        if vpn_pid:
            subprocess.run(["sudo", "kill", "-INT", str(vpn_pid)], check=False)
        return False

    progress(f"\n🌐 Authentification SSO requise\n\n  {auth_url}\n")
    if open_browser(auth_url):
        progress("✅ Navigateur ouvert automatiquement")
    else:
        progress("⚠️  Ouvrez l'URL ci-dessus manuellement dans votre navigateur")

    progress("\n⏳ En attente de l'authentification dans le navigateur…")
    return _wait_for_ppp(entry.id, vpn_pid, ifaces_before, log_path, get_timeout(entry), progress)


def connect_ssh(
    entry: VpnEntry,
    progress: Callable[[str], None] = print,
) -> bool:
    """Open an SSH local port-forwarding tunnel.

    Args:
        entry:    VpnEntry with :attr:`ssh_cfg` populated.
        progress: Callback for status messages.

    Returns:
        True on success.
    """
    assert entry.ssh_cfg, "ssh_cfg must be set for ssh_tunnel auth"
    cfg = entry.ssh_cfg
    log_path = LOG_DIR / f"{entry.id}.log"

    # Validate required fields
    missing = [f for f in ("ssh_key", "ssh_user", "ssh_host", "remote_host") if not getattr(cfg, f)]
    if cfg.local_port == 0:
        missing.append("local_port")
    if cfg.remote_port == 0:
        missing.append("remote_port")
    if missing:
        progress(f"❌ Champs manquants pour {entry.id} : {', '.join(missing)}")
        return False

    if not Path(cfg.ssh_key).exists():
        progress(f"❌ Clé SSH introuvable : {cfg.ssh_key}")
        return False

    # Check local port availability
    result = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True)
    if f":{cfg.local_port} " in result.stdout:
        progress(f"⚠️  Le port local {cfg.local_port} est déjà utilisé")
        return False

    progress(f"🔗 Tunnel SSH : localhost:{cfg.local_port} → {cfg.remote_host}:{cfg.remote_port} via {cfg.ssh_user}@{cfg.ssh_host}")

    # -f → go to background after successful authentication
    timeout = get_timeout(entry)
    ret = subprocess.run(
        [
            "ssh",
            "-i", cfg.ssh_key,
            "-L", f"{cfg.local_port}:{cfg.remote_host}:{cfg.remote_port}",
            "-N", "-f",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
            "-o", f"ConnectTimeout={timeout}",
            f"{cfg.ssh_user}@{cfg.ssh_host}",
        ],
        stdout=log_path.open("w"),
        stderr=subprocess.STDOUT,
    )

    if ret.returncode != 0:
        progress(f"❌ Échec du tunnel SSH (code : {ret.returncode})\n📝 Logs : {log_path}")
        return False

    time.sleep(1)
    tunnel_pid = _find_ssh_tunnel_pid(cfg.local_port, cfg.remote_host, cfg.remote_port, cfg.ssh_user, cfg.ssh_host)
    if not tunnel_pid:
        progress("❌ Impossible de trouver le PID du tunnel SSH")
        return False

    write_session(entry.id, tunnel_pid)
    progress(
        f"✅ Tunnel SSH ouvert : localhost:{cfg.local_port} → {cfg.remote_host}:{cfg.remote_port}\n"
        f"   PID : {tunnel_pid}"
    )
    return True


# ── Dependency check ─────────────────────────────────────────


def check_dependency(
    entry: VpnEntry,
    all_entries: List[VpnEntry],
    ask_connect: Callable[[str], bool],
    progress: Callable[[str], None] = print,
) -> bool:
    """Ensure the dependency of *entry* is connected, prompting if needed.

    Args:
        entry:       The entry about to be connected.
        all_entries: Full list from config.load_entries (with session state).
        ask_connect: Callback that receives the dependency name and returns
                     True if the user wants to auto-connect it.
        progress:    Status message callback.

    Returns:
        True if the dependency is satisfied (or there is none), False otherwise.
    """
    if not entry.depends_on:
        return True

    dep = next((e for e in all_entries if e.id == entry.depends_on), None)
    if dep is None:
        progress(f"❌ Dépendance '{entry.depends_on}' introuvable dans la configuration")
        return False

    if dep.connected:
        progress(f"✅ Dépendance satisfaite : {dep.name} est connecté")
        return True

    progress(f"⚠️  {entry.name} dépend de {dep.name} qui n'est pas connecté")
    if not ask_connect(dep.name):
        progress("❌ Connexion annulée (dépendance non satisfaite)")
        return False

    # Recursively connect the dependency
    if not connect(dep, all_entries, ask_connect=ask_connect, progress=progress):
        progress(f"❌ Impossible de connecter la dépendance {dep.name}")
        return False

    # Re-check after connection attempt
    from .session import is_connected as _is_connected
    if not _is_connected(dep.id):
        return False

    return True


# ── Main dispatcher ──────────────────────────────────────────


def connect(
    entry: VpnEntry,
    all_entries: List[VpnEntry],
    otp_code: Optional[str] = None,
    ask_connect: Optional[Callable[[str], bool]] = None,
    progress: Callable[[str], None] = print,
) -> bool:
    """Connect *entry*, handling dependencies and dispatching by auth type.

    Args:
        entry:       The VpnEntry to connect.
        all_entries: Full entry list (needed for dependency resolution).
        otp_code:    Pre-supplied OTP for 2fa entries (CLI will prompt if None).
        ask_connect: Callback for dependency auto-connect prompt.
                     Receives dep name, returns True to proceed.
                     Defaults to always returning True (non-interactive).
        progress:    Status message callback.

    Returns:
        True on successful connection.
    """
    if ask_connect is None:
        ask_connect = lambda _name: True  # non-interactive default

    if not check_dependency(entry, all_entries, ask_connect, progress):
        return False

    if entry.auth == AuthType.PASSWORD:
        return connect_password(entry, progress)

    if entry.auth == AuthType.TWO_FA:
        if otp_code is None:
            raise ValueError("otp_code is required for 2fa connections")
        return connect_2fa(entry, otp_code, progress)

    if entry.auth == AuthType.SAML:
        return connect_saml(entry, progress)

    if entry.auth == AuthType.SSH_TUNNEL:
        return connect_ssh(entry, progress)

    progress(f"❌ Type d'authentification inconnu : {entry.auth}")
    return False
