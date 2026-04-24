"""vpn — Command-line interface for VPN Manager.

Usage examples::

    vpn                             # interactive menu (default)
    vpn connect                     # interactive connect
    vpn connect 1                   # connect entry #1 directly
    vpn connect my-vpn              # connect by ID
    vpn connect my-vpn --otp 123456 # connect with 2FA code
    vpn connect my-vpn --yes        # skip confirmation prompts
    vpn connect my-vpn --json       # machine-readable output
    vpn disconnect                  # interactive disconnect
    vpn disconnect my-vpn           # disconnect by ID
    vpn disconnect my-vpn --yes     # skip cascade confirmation
    vpn disconnect 2                # disconnect 2nd connected entry
    vpn disconnect 322169           # disconnect by PID (untracked)
    vpn disconnect all              # disconnect everything
    vpn status                      # show connection status
    vpn status --json               # machine-readable status
    vpn list                        # list configured VPNs
    vpn list --json                 # machine-readable VPN list
    vpn configure                   # interactive setup wizard
    vpn cleanup                     # kill orphan processes
"""

from __future__ import annotations

import json
import sys
from typing import Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from vpn_manager import config as cfg
from vpn_manager import connect as conn
from vpn_manager import disconnect as disc
from vpn_manager import status as st
from vpn_manager.config import load_entries, get_entry_by_id, get_entry_by_index
from vpn_manager.models import AuthType, VpnEntry
from vpn_manager.session import attach_session_state, read_session

app = typer.Typer(
    name="vpn",
    help="Gestionnaire VPN multi-connexions (openfortivpn + tunnels SSH).",
    no_args_is_help=False,
    invoke_without_command=True,
)
console = Console()

# ── Shared helpers ───────────────────────────────────────────


def _is_tty() -> bool:
    """Return True when stdin is an interactive terminal."""
    return sys.stdin.isatty()


def _stderr_progress(msg: str) -> None:
    """Progress printer that writes to stderr (used in --json mode)."""
    if msg == ".":
        print(".", end="", flush=True, file=sys.stderr)
    else:
        print(msg, file=sys.stderr)


def _load() -> list[VpnEntry]:
    """Load and return all entries with live session state attached."""
    cfg.ensure_config_dir()
    entries = load_entries()
    return attach_session_state(entries)


def _resolve_entry(target: str, entries: list[VpnEntry]) -> Optional[VpnEntry]:
    """Resolve *target* (index string or VPN ID) to a VpnEntry."""
    if target.isdigit():
        idx = int(target)
        if 1 <= idx <= len(entries):
            return entries[idx - 1]
        return None
    return next((e for e in entries if e.id == target), None)


def _progress(msg: str) -> None:
    """Rich-aware progress printer."""
    # Dot continuation lines (no newline)
    if msg == ".":
        console.print(".", end="", markup=False)
    else:
        console.print(msg)


def _list_vpns(entries: list[VpnEntry]) -> None:
    """Print a formatted list of configured VPNs."""
    if not entries:
        rprint("[yellow]Aucun VPN configuré.[/yellow]")
        rprint("[blue]💡 Utilisez 'vpn configure' pour créer votre premier VPN[/blue]")
        return

    rprint("[blue]VPNs disponibles :[/blue]")
    for entry in entries:
        dep_info = ""
        if entry.depends_on:
            dep = next((e for e in entries if e.id == entry.depends_on), None)
            dep_info = f" [yellow](← {dep.name if dep else entry.depends_on})[/yellow]"

        if entry.connected:
            rprint(f"  {entry.index}) [green]● {entry.type_icon} {entry.name}[/green]{dep_info}")
        else:
            rprint(f"  {entry.index}) {entry.type_icon} {entry.name}{dep_info}")


# ── Commands ─────────────────────────────────────────────────


@app.callback(invoke_without_command=True)
def default(ctx: typer.Context) -> None:
    """Show the interactive menu when no sub-command is given."""
    if ctx.invoked_subcommand is None:
        _interactive_menu()


@app.command(
    epilog=(
        "Examples:\n\n"
        "  vpn connect 1\n"
        "  vpn connect my-vpn\n"
        "  vpn connect my-vpn --otp 123456\n"
        "  vpn connect my-vpn --yes --json\n"
    ),
)
def connect(
    target: Optional[str] = typer.Argument(
        None,
        help="Index (1-N) ou ID du VPN à connecter. Obligatoire hors TTY.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirmer automatiquement (reconnexion, dépendances)."),
    otp: Optional[str] = typer.Option(None, "--otp", help="Code OTP/FortiToken pour l'authentification 2FA."),
    json_output: bool = typer.Option(False, "--json", "-j", help="Sortie JSON structurée (pour agents/scripts)."),
) -> None:
    """Se connecter à un VPN ou tunnel SSH."""
    progress = _stderr_progress if json_output else _progress
    entries = _load()

    if not entries:
        if json_output:
            print(json.dumps({"success": False, "error": "no_vpns_configured",
                               "message": "Aucun VPN configuré. Utilisez 'vpn configure'."}))
        else:
            rprint("[yellow]⚠️  Aucun VPN configuré.[/yellow]")
            rprint("[blue]Utilisez 'vpn configure' pour en créer un.[/blue]")
        raise typer.Exit(1)

    entry: Optional[VpnEntry] = None

    if target is not None:
        entry = _resolve_entry(target, entries)
        if entry is None:
            valid_ids = ", ".join(f"{e.index}={e.id}" for e in entries)
            if json_output:
                print(json.dumps({"success": False, "error": "vpn_not_found", "target": target,
                                   "available": [{"index": e.index, "id": e.id, "name": e.name} for e in entries]}))
            else:
                rprint(f"[red]❌ VPN introuvable : {target!r}[/red]")
                rprint(f"[dim]VPNs disponibles : {valid_ids}[/dim]")
                rprint(f"[dim]Usage : vpn connect <id|index>[/dim]")
            raise typer.Exit(1)
    else:
        if not _is_tty():
            valid_ids = ", ".join(f"{e.index}={e.id}" for e in entries)
            if json_output:
                print(json.dumps({"success": False, "error": "target_required",
                                   "message": "Argument <target> requis en mode non-interactif.",
                                   "available": [{"index": e.index, "id": e.id, "name": e.name} for e in entries]}))
            else:
                print("Error: <target> requis en mode non-interactif.", file=sys.stderr)
                print("Usage: vpn connect <id|index>", file=sys.stderr)
                print(f"VPNs disponibles : {valid_ids}", file=sys.stderr)
            raise typer.Exit(1)
        _list_vpns(entries)
        choice = typer.prompt(f"\nChoisissez un VPN (1-{len(entries)})")
        entry = _resolve_entry(choice, entries)
        if entry is None:
            rprint(f"[red]❌ Choix invalide : {choice!r}[/red]")
            raise typer.Exit(1)

    if entry.connected:
        if json_output and not yes:
            # En mode JSON non-interactif : connexion déjà active = succès idempotent
            print(json.dumps({"success": True, "already_connected": True,
                               "vpn_id": entry.id, "name": entry.name, "pid": entry.pid}))
            raise typer.Exit(0)
        rprint(f"[yellow]⚠️  {entry.name} est déjà connecté.[/yellow]")
        reconn = yes or typer.confirm("Reconnecter ?", default=False)
        if reconn:
            disc.disconnect_entry(
                entry, entries,
                ask_cascade=lambda deps: True if yes else typer.confirm(
                    f"Déconnecter les dépendances ({', '.join(deps)}) d'abord ?", default=True
                ),
                progress=progress,
            )
            import time; time.sleep(2)
        else:
            raise typer.Exit(0)

    # Resolve OTP for 2FA
    otp_code: Optional[str] = otp
    if entry.auth == AuthType.TWO_FA and not otp_code:
        if not _is_tty():
            if json_output:
                print(json.dumps({"success": False, "error": "otp_required",
                                   "message": "Code OTP requis pour ce VPN (2FA). Utilisez --otp <code>."}))
            else:
                print("Error: code OTP requis pour ce VPN (2FA).", file=sys.stderr)
                print(f"Usage: vpn connect {entry.id} --otp <code>", file=sys.stderr)
            raise typer.Exit(1)
        otp_code = typer.prompt("🔐 Code FortiToken")
        if not otp_code:
            rprint("[red]❌ Code FortiToken requis[/red]")
            raise typer.Exit(1)

    success = conn.connect(
        entry,
        entries,
        otp_code=otp_code,
        ask_connect=lambda name: True if yes else typer.confirm(
            f"Connecter la dépendance {name!r} d'abord ?", default=True
        ),
        progress=progress,
    )

    if json_output:
        pid = read_session(entry.id) if success else None
        print(json.dumps({"success": success, "vpn_id": entry.id, "name": entry.name, "pid": pid}))

    raise typer.Exit(0 if success else 1)


@app.command(
    epilog=(
        "Examples:\n\n"
        "  vpn disconnect my-vpn\n"
        "  vpn disconnect all\n"
        "  vpn disconnect my-vpn --yes --json\n"
        "  vpn disconnect 12345          # par PID\n"
    ),
)
def disconnect(
    target: Optional[str] = typer.Argument(
        None,
        help="ID, index, PID ou 'all'. Obligatoire hors TTY.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirmer automatiquement les déconnexions en cascade."),
    json_output: bool = typer.Option(False, "--json", "-j", help="Sortie JSON structurée (pour agents/scripts)."),
) -> None:
    """Se déconnecter d'un VPN ou tunnel SSH."""
    progress = _stderr_progress if json_output else _progress
    entries = _load()

    if target == "all" or target == "a":
        count = disc.disconnect_all(
            entries,
            ask_cascade=lambda deps: True,
            progress=progress,
        )
        if json_output:
            print(json.dumps({"success": True, "disconnected_count": count}))
        else:
            rprint(f"[green]✅ {count} connexion(s) fermée(s)[/green]")
        return

    if target is not None:
        # Raw PID?
        if target.isdigit() and not any(e.id == target for e in entries):
            pid = int(target)
            from vpn_manager.session import _alive as alive_check
            if alive_check(pid):
                success = disc.disconnect_by_pid(pid, progress=progress)
                if json_output:
                    print(json.dumps({"success": success, "pid": pid}))
                raise typer.Exit(0 if success else 1)

        entry = _resolve_entry(target, entries)
        if entry is None:
            valid_ids = ", ".join(f"{e.index}={e.id}" for e in entries)
            if json_output:
                print(json.dumps({"success": False, "error": "vpn_not_found", "target": target,
                                   "available": [{"index": e.index, "id": e.id, "name": e.name} for e in entries]}))
            else:
                rprint(f"[red]❌ VPN introuvable : {target!r}[/red]")
                rprint(f"[dim]VPNs disponibles : {valid_ids}[/dim]")
                rprint(f"[dim]Usage : vpn disconnect <id|index|pid|all>[/dim]")
            raise typer.Exit(1)

        success = disc.disconnect_entry(
            entry, entries,
            ask_cascade=lambda deps: True if yes else typer.confirm(
                f"Déconnecter les dépendances ({', '.join(deps)}) d'abord ?", default=True
            ),
            progress=progress,
        )
        if json_output:
            print(json.dumps({"success": success, "vpn_id": entry.id, "name": entry.name}))
        raise typer.Exit(0 if success else 1)

    # No target — need interactive mode
    if not _is_tty():
        active = [e for e in entries if e.connected]
        active_ids = ", ".join(f"{e.index}={e.id}" for e in active) if active else "aucune"
        if json_output:
            print(json.dumps({"success": False, "error": "target_required",
                               "message": "Argument <target> requis en mode non-interactif.",
                               "active": [{"index": e.index, "id": e.id, "name": e.name} for e in active]}))
        else:
            print("Error: <target> requis en mode non-interactif.", file=sys.stderr)
            print("Usage: vpn disconnect <id|index|pid|all>", file=sys.stderr)
            print(f"Connexions actives : {active_ids}", file=sys.stderr)
        raise typer.Exit(1)

    # Interactive mode
    active = [e for e in entries if e.connected]
    if not active:
        rprint("[red]❌ Aucune connexion active[/red]")

        untracked = st.get_untracked_processes()
        if untracked:
            rprint("[yellow]⚠️  Des processus VPN non trackés ont été détectés.[/yellow]")
            if typer.confirm("Nettoyer les processus orphelins ?", default=False):
                disc.cleanup_orphans(_progress)
        raise typer.Exit(1)

    if len(active) == 1:
        disc.disconnect_entry(
            active[0], entries,
            ask_cascade=lambda deps: True if yes else typer.confirm(
                f"Déconnecter les dépendances ({', '.join(deps)}) d'abord ?", default=True
            ),
            progress=_progress,
        )
        return

    _list_vpns(entries)
    choice = typer.prompt(f"\nDéconnecter quel VPN ? (1-{len(active)})")
    entry = _resolve_entry(choice, active)
    if entry is None:
        rprint(f"[red]❌ Choix invalide : {choice!r}[/red]")
        raise typer.Exit(1)

    disc.disconnect_entry(
        entry, entries,
        ask_cascade=lambda deps: True if yes else typer.confirm(
            f"Déconnecter les dépendances ({', '.join(deps)}) d'abord ?", default=True
        ),
        progress=_progress,
    )


@app.command(
    epilog=(
        "Examples:\n\n"
        "  vpn status\n"
        "  vpn status --json\n"
    ),
)
def status(
    json_output: bool = typer.Option(False, "--json", "-j", help="Sortie JSON structurée (pour agents/scripts)."),
) -> None:
    """Afficher le statut de toutes les connexions."""
    entries = _load()
    connected_infos = st.get_connected(entries)
    untracked = st.get_untracked_processes()

    if json_output:
        result: dict = {"connected": [], "untracked": []}
        for info in connected_infos:
            e = info.entry
            entry_data: dict = {"vpn_id": e.id, "name": e.name, "pid": info.pid, "type": e.auth.value}
            if e.is_ssh_tunnel and e.ssh_cfg:
                c = e.ssh_cfg
                entry_data["local_port"] = c.local_port
                entry_data["remote_host"] = c.remote_host
                entry_data["remote_port"] = c.remote_port
            else:
                if info.ip:
                    entry_data["ip"] = info.ip
                if info.interface:
                    entry_data["interface"] = info.interface
            result["connected"].append(entry_data)
        for proc in untracked:
            result["untracked"].append({"pid": proc.pid, "cmdline": proc.cmdline, "ip": proc.ip})
        print(json.dumps(result))
        return

    if not connected_infos and not untracked:
        rprint("[red]❌ Aucune connexion VPN active[/red]")
        return

    for info in connected_infos:
        e = info.entry
        if e.is_ssh_tunnel and e.ssh_cfg:
            c = e.ssh_cfg
            rprint(
                f"[green]✅ 🔗 {e.name}[/green]  "
                f"(PID : {info.pid}, localhost:{c.local_port} → {c.remote_host}:{c.remote_port})"
            )
        else:
            ip_part = f", IP : {info.ip}" if info.ip else ""
            iface_part = f", iface : {info.interface}" if info.interface else ""
            rprint(f"[green]✅ 🔒 {e.name}[/green]  (PID : {info.pid}{ip_part}{iface_part})")

    for proc in untracked:
        ip_part = f", IP : {proc.ip}" if proc.ip else ""
        rprint(f"[yellow]⚠️  VPN non tracké (PID : {proc.pid}{ip_part})[/yellow]")
        rprint(f"   [dim]{proc.cmdline}[/dim]")

    if untracked:
        rprint("\n[yellow]💡 Utilisez 'vpn disconnect <pid>' pour déconnecter un processus non tracké[/yellow]")


@app.command(
    name="list",
    epilog=(
        "Examples:\n\n"
        "  vpn list\n"
        "  vpn list --json\n"
        "  vpn list --json | jq '.[] | select(.connected)'"
    ),
)
def list_vpns(
    json_output: bool = typer.Option(False, "--json", "-j", help="Sortie JSON structurée (pour agents/scripts)."),
) -> None:
    """Lister les VPNs configurés."""
    entries = _load()
    if json_output:
        result = []
        for e in entries:
            entry_data: dict = {
                "index": e.index, "id": e.id, "name": e.name,
                "type": e.auth.value, "connected": e.connected,
            }
            if e.pid:
                entry_data["pid"] = e.pid
            if e.depends_on:
                entry_data["depends_on"] = e.depends_on
            result.append(entry_data)
        print(json.dumps(result))
        return
    _list_vpns(entries)


@app.command()
def cleanup() -> None:
    """Supprimer les processus et interfaces VPN orphelins."""
    rprint("[blue]🧹 Nettoyage des processus et interfaces orphelins…[/blue]")
    n = disc.cleanup_orphans(_progress)
    if n:
        rprint(f"[green]✅ {n} élément(s) nettoyé(s)[/green]")
    else:
        rprint("[green]✅ Rien à nettoyer[/green]")


@app.command()
def configure() -> None:
    """Assistant interactif de création d'un VPN ou tunnel SSH."""
    from vpn_manager.wizard import run_wizard
    cfg.ensure_config_dir()
    run_wizard()


# ── Profile sub-commands ─────────────────────────────────────

profile_app = typer.Typer(
    name="profile",
    help="Gérer les profils VPN (groupes de connexions).",
    no_args_is_help=False,
    invoke_without_command=True,
)
app.add_typer(profile_app, name="profile")


@profile_app.callback(invoke_without_command=True)
def profile_default(ctx: typer.Context) -> None:
    """Lister les profils si aucune sous-commande n'est fournie."""
    if ctx.invoked_subcommand is None:
        _cmd_profile_list(json_output=False)


def _cmd_profile_list(json_output: bool) -> None:
    from vpn_manager.profile import load_profiles

    profiles = load_profiles()
    entries = _load()

    if json_output:
        print(json.dumps([{"id": p.id, "name": p.name, "vpns": p.vpn_ids} for p in profiles]))
        return

    if not profiles:
        rprint("[yellow]Aucun profil défini.[/yellow]")
        rprint("[blue]💡 Utilisez 'vpn profile create' pour créer un profil.[/blue]")
        return

    rprint("[blue]Profils disponibles :[/blue]")
    for p in profiles:
        vpn_names = []
        for vid in p.vpn_ids:
            e = next((e for e in entries if e.id == vid), None)
            vpn_names.append(e.name if e else f"[red]?{vid}[/red]")
        rprint(f"  [cyan]{p.id}[/cyan]  {p.name}")
        rprint(f"    [dim]{', '.join(vpn_names)}[/dim]")


@profile_app.command(name="list")
def profile_list(
    json_output: bool = typer.Option(False, "--json", "-j", help="Sortie JSON structurée."),
) -> None:
    """Lister les profils définis."""
    _cmd_profile_list(json_output)


@profile_app.command(name="connect")
def profile_connect(
    profile_id: str = typer.Argument(..., help="ID du profil à connecter."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirmer automatiquement (reconnexion, dépendances)."),
    json_output: bool = typer.Option(False, "--json", "-j", help="Sortie JSON structurée."),
) -> None:
    """Connecter tous les VPNs d'un profil en une seule commande."""
    from vpn_manager.profile import get_profile_by_id

    profile = get_profile_by_id(profile_id)
    if profile is None:
        if json_output:
            print(json.dumps({"success": False, "error": "profile_not_found", "profile_id": profile_id}))
        else:
            rprint(f"[red]❌ Profil introuvable : {profile_id!r}[/red]")
            rprint("[dim]Utilisez 'vpn profile list' pour voir les profils disponibles.[/dim]")
        raise typer.Exit(1)

    progress = _stderr_progress if json_output else _progress
    results: list[dict] = []
    all_ok = True

    if not json_output:
        rprint(f"[blue]🔌 Connexion du profil [bold]{profile.name}[/bold]…[/blue]")

    for vpn_id in profile.vpn_ids:
        entries = _load()  # refresh live session state before each VPN
        entry = next((e for e in entries if e.id == vpn_id), None)

        if entry is None:
            if not json_output:
                rprint(f"  [red]❌ VPN {vpn_id!r} introuvable dans la configuration[/red]")
            results.append({"vpn_id": vpn_id, "success": False, "error": "vpn_not_found"})
            all_ok = False
            continue

        if entry.connected:
            if not json_output:
                rprint(f"  [yellow]⏭  {entry.name} — déjà connecté[/yellow]")
            results.append({"vpn_id": vpn_id, "name": entry.name, "success": True, "already_connected": True})
            continue

        # Handle 2FA OTP
        otp_code: Optional[str] = None
        if entry.auth == AuthType.TWO_FA:
            if not _is_tty():
                if not json_output:
                    rprint(f"  [yellow]⚠️  {entry.name} — ignoré (2FA requis, mode non-interactif)[/yellow]")
                results.append({"vpn_id": vpn_id, "name": entry.name, "success": False, "error": "otp_required"})
                all_ok = False
                continue
            otp_code = typer.prompt(f"  🔐 Code FortiToken pour {entry.name}")
            if not otp_code:
                rprint(f"  [red]❌ Code FortiToken requis pour {entry.name}[/red]")
                results.append({"vpn_id": vpn_id, "name": entry.name, "success": False, "error": "otp_missing"})
                all_ok = False
                continue

        if not json_output:
            rprint(f"  → Connexion de [cyan]{entry.name}[/cyan]…")

        success = conn.connect(
            entry,
            entries,
            otp_code=otp_code,
            ask_connect=lambda name: True,  # auto-accept depends_on in profile mode
            progress=progress,
        )

        if not success:
            all_ok = False
        if not json_output:
            if success:
                rprint(f"  [green]✅ {entry.name}[/green]")
            else:
                rprint(f"  [red]❌ {entry.name} — échec de connexion[/red]")

        results.append({"vpn_id": vpn_id, "name": entry.name, "success": success})

    if json_output:
        print(json.dumps({"profile_id": profile_id, "name": profile.name, "results": results, "all_ok": all_ok}))
    elif all_ok:
        rprint(f"\n[green]✅ Profil [bold]{profile.name}[/bold] connecté[/green]")
    else:
        rprint(f"\n[yellow]⚠️  Profil [bold]{profile.name}[/bold] — connexion partielle[/yellow]")

    raise typer.Exit(0 if all_ok else 1)


@profile_app.command(name="disconnect")
def profile_disconnect(
    profile_id: str = typer.Argument(..., help="ID du profil à déconnecter."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirmer automatiquement les déconnexions."),
    json_output: bool = typer.Option(False, "--json", "-j", help="Sortie JSON structurée."),
) -> None:
    """Déconnecter tous les VPNs actifs d'un profil."""
    from vpn_manager.profile import get_profile_by_id

    profile = get_profile_by_id(profile_id)
    if profile is None:
        if json_output:
            print(json.dumps({"success": False, "error": "profile_not_found", "profile_id": profile_id}))
        else:
            rprint(f"[red]❌ Profil introuvable : {profile_id!r}[/red]")
        raise typer.Exit(1)

    entries = _load()
    progress = _stderr_progress if json_output else _progress
    results: list[dict] = []

    if not json_output:
        rprint(f"[blue]🔌 Déconnexion du profil [bold]{profile.name}[/bold]…[/blue]")

    # Disconnect in reverse order to respect depends_on chains
    for vpn_id in reversed(profile.vpn_ids):
        entry = next((e for e in entries if e.id == vpn_id), None)
        if entry is None or not entry.connected:
            continue

        success = disc.disconnect_entry(
            entry, entries,
            ask_cascade=lambda deps: True,
            progress=progress,
        )
        if not json_output:
            if success:
                rprint(f"  [green]✅ {entry.name} déconnecté[/green]")
            else:
                rprint(f"  [red]❌ {entry.name} — échec[/red]")
        results.append({"vpn_id": vpn_id, "name": entry.name, "success": success})

    if json_output:
        print(json.dumps({"profile_id": profile_id, "name": profile.name, "results": results}))
    elif not results:
        rprint("[yellow]Aucun VPN actif dans ce profil.[/yellow]")


@profile_app.command(name="create")
def profile_create(
    profile_id: Optional[str] = typer.Argument(None, help="ID du profil (ex: bureau, home)."),
) -> None:
    """Créer un nouveau profil interactivement."""
    from vpn_manager.profile import save_profile as _save_profile
    from vpn_manager.models import Profile

    entries = _load()
    if not entries:
        rprint("[yellow]⚠️  Aucun VPN configuré. Utilisez 'vpn configure' d'abord.[/yellow]")
        raise typer.Exit(1)

    if not profile_id:
        profile_id = typer.prompt("ID du profil (ex: bureau, home)")

    if not profile_id or not profile_id.replace("-", "").replace("_", "").isalnum():
        rprint("[red]❌ L'ID doit être alphanumérique (tirets et underscores autorisés).[/red]")
        raise typer.Exit(1)

    profile_name = typer.prompt("Nom affiché", default=profile_id.capitalize())

    rprint("\n[blue]VPNs disponibles :[/blue]")
    _list_vpns(entries)
    rprint()

    vpn_ids_raw = typer.prompt("IDs des VPNs à inclure (séparés par virgules ou espaces)")
    vpn_ids = [v.strip() for v in vpn_ids_raw.replace(",", " ").split() if v.strip()]

    valid_ids = {e.id for e in entries}
    invalid = [v for v in vpn_ids if v not in valid_ids]
    if invalid:
        rprint(f"[red]❌ IDs inconnus : {', '.join(invalid)}[/red]")
        raise typer.Exit(1)

    if not vpn_ids:
        rprint("[red]❌ Le profil doit contenir au moins un VPN.[/red]")
        raise typer.Exit(1)

    profile = Profile(id=profile_id, name=profile_name, vpn_ids=vpn_ids)
    _save_profile(profile)

    vpn_names = [next((e.name for e in entries if e.id == v), v) for v in vpn_ids]
    rprint(f"\n[green]✅ Profil [bold]{profile_name}[/bold] créé avec {len(vpn_ids)} VPN(s) :[/green]")
    for name in vpn_names:
        rprint(f"   [dim]• {name}[/dim]")
    rprint(f"\n[dim]Utilisation : vpn profile connect {profile_id}[/dim]")


@profile_app.command(name="delete")
def profile_delete(
    profile_id: str = typer.Argument(..., help="ID du profil à supprimer."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Ne pas demander de confirmation."),
) -> None:
    """Supprimer un profil."""
    from vpn_manager.profile import delete_profile as _delete_profile, get_profile_by_id

    profile = get_profile_by_id(profile_id)
    if profile is None:
        rprint(f"[red]❌ Profil introuvable : {profile_id!r}[/red]")
        raise typer.Exit(1)

    if not yes:
        confirmed = typer.confirm(f"Supprimer le profil {profile.name!r} ?", default=False)
        if not confirmed:
            raise typer.Exit(0)

    _delete_profile(profile_id)
    rprint(f"[green]✅ Profil {profile.name!r} supprimé[/green]")


@app.command(name="help")
def show_help() -> None:
    """Afficher l'aide détaillée des commandes disponibles."""
    table = Table(show_header=True, header_style="bold blue", box=None, padding=(0, 2))
    table.add_column("Commande", style="cyan", no_wrap=True)
    table.add_column("Description")

    table.add_row("vpn", "Ouvre le menu interactif (par défaut)")
    table.add_row("vpn connect", "Menu interactif de connexion")
    table.add_row("vpn connect <id|n°>", "Connexion directe par ID ou numéro")
    table.add_row("vpn connect <id> --otp <code>", "Connexion avec code 2FA/OTP")
    table.add_row("vpn connect <id> --yes", "Connexion sans confirmation (reconnexion, dépendances)")
    table.add_row("vpn disconnect", "Menu interactif de déconnexion")
    table.add_row("vpn disconnect <id|n°>", "Déconnexion par ID ou numéro")
    table.add_row("vpn disconnect <pid>", "Déconnexion par PID (processus non tracké)")
    table.add_row("vpn disconnect all", "Déconnecter toutes les connexions actives")
    table.add_row("vpn disconnect <id> --yes", "Déconnexion sans confirmation en cascade")
    table.add_row("vpn status", "Afficher l'état de toutes les connexions")
    table.add_row("vpn status --json", "Statut en JSON (pour agents/scripts)")
    table.add_row("vpn list", "Lister les VPNs configurés")
    table.add_row("vpn list --json", "Liste en JSON (pour agents/scripts)")
    table.add_row("vpn configure", "Assistant de création d'un nouveau VPN")
    table.add_row("vpn cleanup", "Supprimer les processus et interfaces orphelins")
    table.add_row("vpn help", "Afficher cette aide")
    table.add_row("", "")
    table.add_row("[bold]Profils[/bold]", "")
    table.add_row("vpn profile", "Lister les profils définis")
    table.add_row("vpn profile connect <id>", "Connecter tous les VPNs d'un profil")
    table.add_row("vpn profile disconnect <id>", "Déconnecter tous les VPNs d'un profil")
    table.add_row("vpn profile create", "Créer un nouveau profil interactivement")
    table.add_row("vpn profile delete <id>", "Supprimer un profil")

    rprint()
    rprint("[bold blue]Gestionnaire VPN — Commandes disponibles[/bold blue]")
    rprint()
    console.print(table)
    rprint()
    rprint("[bold]Exemples :[/bold]")
    rprint("  [dim]# Connexion rapide au VPN n°1[/dim]")
    rprint("  [cyan]vpn connect 1[/cyan]")
    rprint()
    rprint("  [dim]# Connexion par identifiant[/dim]")
    rprint("  [cyan]vpn connect mon-vpn[/cyan]")
    rprint()
    rprint("  [dim]# Connecter un profil entier d'un coup[/dim]")
    rprint("  [cyan]vpn profile connect bureau[/cyan]")
    rprint()
    rprint("  [dim]# Voir le statut[/dim]")
    rprint("  [cyan]vpn status[/cyan]")
    rprint()
    rprint("  [dim]# Déconnecter tout[/dim]")
    rprint("  [cyan]vpn disconnect all[/cyan]")
    rprint()
    rprint("[dim]Chaque commande accepte aussi [bold]--help[/bold] pour plus de détails.[/dim]")
    rprint()


# ── Interactive menu ─────────────────────────────────────────


def _interactive_menu() -> None:
    """Full-screen interactive menu loop (replaces the old Bash menu)."""
    while True:
        entries = _load()
        console.clear()
        rprint("[blue]=== Gestionnaire VPN ===[/blue]\n")
        _print_status_inline(entries)
        rprint()
        _list_vpns(entries)
        rprint()
        rprint("  c) Se connecter")
        rprint("  d) Se déconnecter")
        rprint("  s) Statut")
        rprint("  p) Connecter un profil")
        rprint("  n) Configurer un nouveau VPN")
        rprint("  h) Aide")
        rprint("  q) Quitter")
        rprint()

        choice = typer.prompt("Votre choix", default="")

        if choice in ("h", "H", "?"):
            try:
                show_help()
            except SystemExit:
                pass
        elif choice in ("c", "C"):
            try:
                connect(target=None)
            except SystemExit:
                pass
        elif choice in ("d", "D"):
            try:
                disconnect(target=None)
            except SystemExit:
                pass
        elif choice in ("s", "S"):
            try:
                status()
            except SystemExit:
                pass
        elif choice in ("p", "P"):
            try:
                _profile_menu()
            except SystemExit:
                pass
        elif choice in ("n", "N"):
            try:
                configure()
            except SystemExit:
                pass
        elif choice in ("q", "Q"):
            raise typer.Exit(0)
        elif choice.isdigit():
            entry = _resolve_entry(choice, entries)
            if entry:
                try:
                    connect(target=choice)
                except SystemExit:
                    pass
            else:
                rprint("[red]❌ Choix invalide[/red]")
        else:
            rprint("[red]❌ Choix invalide[/red]")

        if choice not in ("q", "Q"):
            typer.pause("\nAppuyez sur Entrée pour continuer…")


def _profile_menu() -> None:
    """Sub-menu interactif pour connecter un profil depuis le menu principal."""
    from vpn_manager.profile import load_profiles

    entries = _load()
    profiles = load_profiles()

    if not profiles:
        rprint("[yellow]Aucun profil défini.[/yellow]")
        rprint("[blue]💡 Utilisez 'vpn profile create' pour créer un profil.[/blue]")
        return

    rprint("[blue]Profils disponibles :[/blue]")
    for i, p in enumerate(profiles, 1):
        vpn_names = [next((e.name for e in entries if e.id == v), f"?{v}") for v in p.vpn_ids]
        rprint(f"  {i}) [cyan]{p.name}[/cyan]  [dim]({', '.join(vpn_names)})[/dim]")
    rprint()

    choice = typer.prompt(f"Connecter quel profil ? (1-{len(profiles)})")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(profiles):
            profile_connect(profiles[idx].id)
        else:
            rprint("[red]❌ Choix invalide[/red]")
    except ValueError:
        rprint("[red]❌ Choix invalide[/red]")


def _print_status_inline(entries: list[VpnEntry]) -> None:
    """One-line status summary for the menu header."""
    active = [e for e in entries if e.connected]
    if active:
        names = ", ".join(e.name for e in active)
        rprint(f"[green]● {len(active)} connecté(s) : {names}[/green]")
    else:
        rprint("[red]○ Aucune connexion active[/red]")


# ── Entry point ──────────────────────────────────────────────


def main() -> None:
    # Intercept 'help' / '--help' (no subcommand) before Click/Typer consumes them
    if len(sys.argv) == 2 and sys.argv[1] in ("help", "--help", "-h"):
        sys.argv.pop(1)
        show_help()
        return
    app()


if __name__ == "__main__":
    main()
