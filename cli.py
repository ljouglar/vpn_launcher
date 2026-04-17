"""vpn — Command-line interface for VPN Manager.

Usage examples::

    vpn                      # interactive menu (default)
    vpn connect              # interactive connect
    vpn connect 1            # connect entry #1 directly
    vpn connect my-vpn       # connect by ID
    vpn disconnect           # interactive disconnect
    vpn disconnect my-vpn    # disconnect by ID
    vpn disconnect 2         # disconnect 2nd connected entry
    vpn disconnect 322169    # disconnect by PID (untracked)
    vpn disconnect all       # disconnect everything
    vpn status               # show connection status
    vpn list                 # list configured VPNs
    vpn configure            # interactive setup wizard
    vpn cleanup              # kill orphan processes
"""

from __future__ import annotations

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
from vpn_manager.session import attach_session_state

app = typer.Typer(
    name="vpn",
    help="Gestionnaire VPN multi-connexions (openfortivpn + tunnels SSH).",
    no_args_is_help=False,
    invoke_without_command=True,
)
console = Console()

# ── Shared helpers ───────────────────────────────────────────


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


@app.command()
def connect(
    target: Optional[str] = typer.Argument(
        None,
        help="Index (1-N) ou ID du VPN à connecter. Menu interactif si absent.",
    ),
) -> None:
    """Se connecter à un VPN ou tunnel SSH."""
    entries = _load()

    if not entries:
        rprint("[yellow]⚠️  Aucun VPN configuré.[/yellow]")
        rprint("[blue]Utilisez 'vpn configure' pour en créer un.[/blue]")
        raise typer.Exit(1)

    entry: Optional[VpnEntry] = None

    if target is not None:
        entry = _resolve_entry(target, entries)
        if entry is None:
            rprint(f"[red]❌ VPN introuvable : {target!r}[/red]")
            raise typer.Exit(1)
    else:
        _list_vpns(entries)
        choice = typer.prompt(f"\nChoisissez un VPN (1-{len(entries)})")
        entry = _resolve_entry(choice, entries)
        if entry is None:
            rprint(f"[red]❌ Choix invalide : {choice!r}[/red]")
            raise typer.Exit(1)

    if entry.connected:
        rprint(f"[yellow]⚠️  {entry.name} est déjà connecté.[/yellow]")
        reconn = typer.confirm("Reconnecter ?", default=False)
        if reconn:
            disc.disconnect_entry(
                entry, entries,
                ask_cascade=lambda deps: typer.confirm(
                    f"Déconnecter les dépendances ({', '.join(deps)}) d'abord ?", default=True
                ),
                progress=_progress,
            )
            import time; time.sleep(2)
        else:
            raise typer.Exit(0)

    # Prompt for OTP if 2fa
    otp_code: Optional[str] = None
    if entry.auth == AuthType.TWO_FA:
        otp_code = typer.prompt("🔐 Code FortiToken")
        if not otp_code:
            rprint("[red]❌ Code FortiToken requis[/red]")
            raise typer.Exit(1)

    success = conn.connect(
        entry,
        entries,
        otp_code=otp_code,
        ask_connect=lambda name: typer.confirm(f"Connecter la dépendance {name!r} d'abord ?", default=True),
        progress=_progress,
    )
    raise typer.Exit(0 if success else 1)


@app.command()
def disconnect(
    target: Optional[str] = typer.Argument(
        None,
        help="ID, index, PID ou 'all'. Menu interactif si absent.",
    ),
) -> None:
    """Se déconnecter d'un VPN ou tunnel SSH."""
    entries = _load()

    if target == "all" or target == "a":
        count = disc.disconnect_all(
            entries,
            ask_cascade=lambda deps: True,  # "all" skips cascade prompt
            progress=_progress,
        )
        rprint(f"[green]✅ {count} connexion(s) fermée(s)[/green]")
        return

    if target is not None:
        # Raw PID?
        if target.isdigit() and not any(e.id == target for e in entries):
            pid = int(target)
            from .vpn_manager.session import _alive
            from vpn_manager.session import _alive as alive_check
            if alive_check(pid):
                success = disc.disconnect_by_pid(pid, progress=_progress)
                raise typer.Exit(0 if success else 1)

        entry = _resolve_entry(target, entries)
        if entry is None:
            rprint(f"[red]❌ VPN introuvable : {target!r}[/red]")
            raise typer.Exit(1)

        success = disc.disconnect_entry(
            entry, entries,
            ask_cascade=lambda deps: typer.confirm(
                f"Déconnecter les dépendances ({', '.join(deps)}) d'abord ?", default=True
            ),
            progress=_progress,
        )
        raise typer.Exit(0 if success else 1)

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
            ask_cascade=lambda deps: typer.confirm(
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
        ask_cascade=lambda deps: typer.confirm(
            f"Déconnecter les dépendances ({', '.join(deps)}) d'abord ?", default=True
        ),
        progress=_progress,
    )


@app.command()
def status() -> None:
    """Afficher le statut de toutes les connexions."""
    entries = _load()
    connected_infos = st.get_connected(entries)
    untracked = st.get_untracked_processes()

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


@app.command(name="list")
def list_vpns() -> None:
    """Lister les VPNs configurés."""
    entries = _load()
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


@app.command(name="help")
def show_help() -> None:
    """Afficher l'aide détaillée des commandes disponibles."""
    table = Table(show_header=True, header_style="bold blue", box=None, padding=(0, 2))
    table.add_column("Commande", style="cyan", no_wrap=True)
    table.add_column("Description")

    table.add_row("vpn", "Ouvre le menu interactif (par défaut)")
    table.add_row("vpn connect", "Menu interactif de connexion")
    table.add_row("vpn connect <id|n°>", "Connexion directe par ID ou numéro")
    table.add_row("vpn disconnect", "Menu interactif de déconnexion")
    table.add_row("vpn disconnect <id|n°>", "Déconnexion par ID ou numéro")
    table.add_row("vpn disconnect <pid>", "Déconnexion par PID (processus non tracké)")
    table.add_row("vpn disconnect all", "Déconnecter toutes les connexions actives")
    table.add_row("vpn status", "Afficher l'état de toutes les connexions")
    table.add_row("vpn list", "Lister les VPNs configurés")
    table.add_row("vpn configure", "Assistant de création d'un nouveau VPN")
    table.add_row("vpn cleanup", "Supprimer les processus et interfaces orphelins")
    table.add_row("vpn help", "Afficher cette aide")

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
    # Intercept 'help' before Click/Typer consumes it as a reserved word
    if len(sys.argv) == 2 and sys.argv[1] == "help":
        sys.argv.pop(1)
        show_help()
        return
    app()


if __name__ == "__main__":
    main()
