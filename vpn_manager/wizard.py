"""vpn_manager.wizard — Interactive VPN setup wizard.

Replaces lib/configure.sh entirely.  Guides the user through creating
a new VPN entry and writes the appropriate config files.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer
from rich import print as rprint

from .config import CONFIG_DIR, VPN_CONF, load_entries
from .models import AuthType


def _validate_id(vpn_id: str) -> bool:
    """Return True if *vpn_id* is valid and not already used."""
    import re
    if not re.match(r"^[a-zA-Z0-9_-]+$", vpn_id):
        rprint("[red]❌ L'ID doit contenir uniquement des lettres, chiffres, tirets ou underscores[/red]")
        return False
    existing_ids = [e.id for e in load_entries()]
    if vpn_id in existing_ids:
        rprint(f"[red]❌ Un VPN avec l'ID '{vpn_id}' existe déjà[/red]")
        return False
    return True


def _fetch_cert(host: str, port: int) -> str:
    """Auto-detect the server SSL certificate fingerprint."""
    try:
        result = subprocess.run(
            ["openssl", "s_client", "-connect", f"{host}:{port}", "-servername", host],
            input=b"",
            capture_output=True,
            timeout=10,
        )
        cert = subprocess.run(
            ["openssl", "x509", "-fingerprint", "-noout", "-sha256"],
            input=result.stdout,
            capture_output=True,
            timeout=5,
        )
        line = cert.stdout.decode(errors="replace")
        if "=" in line:
            return line.split("=", 1)[1].strip().replace(":", "").lower()
    except Exception:
        pass
    return ""


def _ask_dependency() -> str:
    """Ask the user to pick an optional dependency from existing entries.

    Returns the ID of the chosen entry, or empty string.
    """
    entries = load_entries()
    if not entries:
        return ""

    rprint("\n[yellow]Dépendance (optionnel)[/yellow]")
    rprint("Ce VPN/tunnel dépend-il d'une autre connexion ?")
    rprint("  0) Aucune dépendance")
    for e in entries:
        rprint(f"  {e.index}) {e.name}")

    choice = typer.prompt(f"Votre choix [0-{len(entries)}]", default="0")
    if choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(entries):
            return entries[idx - 1].id
    return ""


def _wizard_password_or_2fa(vpn_id: str, vpn_name: str, auth: AuthType, depends_on: str) -> None:
    """Collect openfortivpn credentials and write config files."""
    rprint(f"\n[yellow]Configuration du serveur[/yellow]")

    vpn_host = typer.prompt("Hôte (ex: vpn.example.com)")
    if not vpn_host:
        rprint("[red]❌ L'hôte est obligatoire[/red]")
        raise typer.Exit(1)

    vpn_port = typer.prompt("Port", default="443")
    vpn_username = typer.prompt("Nom d'utilisateur")
    if not vpn_username:
        rprint("[red]❌ Le nom d'utilisateur est obligatoire[/red]")
        raise typer.Exit(1)

    if auth == AuthType.TWO_FA:
        rprint("Mot de passe (le code 2FA sera demandé à chaque connexion)")
    else:
        rprint("Mot de passe")
    vpn_password = typer.prompt("Mot de passe", hide_input=True, default="")

    rprint(f"\nCertificat SSL")
    rprint(f"Pour obtenir le certificat :")
    rprint(f"  echo | openssl s_client -connect {vpn_host}:{vpn_port} 2>/dev/null | openssl x509 -fingerprint -noout -sha256")
    rprint("")

    vpn_cert = typer.prompt("Certificat SHA256 (sans ':'), ou Entrée pour auto-détecter", default="")
    if not vpn_cert:
        rprint(f"[blue]🔍 Tentative d'auto-détection du certificat de {vpn_host}:{vpn_port}…[/blue]")
        vpn_cert = _fetch_cert(vpn_host, int(vpn_port))
        if vpn_cert:
            rprint(f"[green]✅ Certificat détecté : {vpn_cert[:16]}…[/green]")
        else:
            rprint("[yellow]⚠️  Impossible de récupérer le certificat — connexion sans vérification[/yellow]")

    # Write .conf file
    config_file = f"{vpn_id}.conf"
    config_path = CONFIG_DIR / config_file
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Configuration VPN : {vpn_name}\n",
        f"host = {vpn_host}\n",
        f"port = {vpn_port}\n",
        f"username = {vpn_username}\n",
    ]
    if vpn_password:
        lines.append(f"password = {vpn_password}\n")
    if vpn_cert:
        lines.append(f"trusted-cert = {vpn_cert}\n")
    lines += [
        "set-routes = 1\n",
        "set-dns = 0\n",
        "pppd-use-peerdns = 0\n",
    ]
    config_path.write_text("".join(lines))
    config_path.chmod(0o600)

    # Append entry to vpns.conf
    with VPN_CONF.open("a") as f:
        f.write(f"\n[{vpn_id}]\n")
        f.write(f"name = {vpn_name}\n")
        f.write(f"auth = {auth.value}\n")
        f.write(f"config = {config_file}\n")
        if depends_on:
            f.write(f"depends_on = {depends_on}\n")

    rprint(f"\n[green]✅ VPN '{vpn_name}' créé avec succès ![/green]")
    rprint(f"  • {VPN_CONF}  (entrée ajoutée)")
    rprint(f"  • {config_path}  (chmod 600)")


def _wizard_saml(vpn_id: str, vpn_name: str, depends_on: str) -> None:
    """Collect SAML parameters and write vpns.conf entry."""
    rprint("\n[yellow]Configuration SAML[/yellow]")
    saml_host = typer.prompt("Hôte:port (ex: vpn.example.com:444)")
    if not saml_host:
        rprint("[red]❌ L'hôte SAML est obligatoire[/red]")
        raise typer.Exit(1)

    with VPN_CONF.open("a") as f:
        f.write(f"\n[{vpn_id}]\n")
        f.write(f"name = {vpn_name}\n")
        f.write(f"auth = saml\n")
        f.write(f"saml_host = {saml_host}\n")
        if depends_on:
            f.write(f"depends_on = {depends_on}\n")

    rprint(f"\n[green]✅ VPN SAML '{vpn_name}' créé avec succès ![/green]")
    rprint(f"  • {VPN_CONF}  (entrée ajoutée)")


def _wizard_ssh(vpn_id: str, vpn_name: str, depends_on: str) -> None:
    """Collect SSH tunnel parameters and write config files."""
    rprint("\n[yellow]Configuration du tunnel SSH[/yellow]")

    ssh_key = typer.prompt(f"Clé SSH", default=f"{Path.home()}/.ssh/id_rsa")
    if not Path(ssh_key).exists():
        rprint(f"[yellow]⚠️  La clé {ssh_key} n'existe pas encore[/yellow]")

    ssh_user = typer.prompt("Utilisateur SSH")
    if not ssh_user:
        rprint("[red]❌ L'utilisateur SSH est obligatoire[/red]")
        raise typer.Exit(1)

    ssh_host = typer.prompt("Hôte SSH / proxy de rebond (ex: 10.244.18.22)")
    if not ssh_host:
        rprint("[red]❌ L'hôte SSH est obligatoire[/red]")
        raise typer.Exit(1)

    rprint("\n[yellow]Port forwarding[/yellow]")
    local_port = typer.prompt("Port local (ex: 33070)")
    remote_host = typer.prompt("Hôte distant / destination (ex: 91.216.43.88)")
    remote_port = typer.prompt("Port distant (ex: 3306)")

    for label, val in [("port local", local_port), ("hôte distant", remote_host), ("port distant", remote_port)]:
        if not val:
            rprint(f"[red]❌ Le {label} est obligatoire[/red]")
            raise typer.Exit(1)

    config_file = f"{vpn_id}.conf"
    config_path = CONFIG_DIR / config_file
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    config_path.write_text(
        f"# Tunnel SSH : {vpn_name}\n"
        f"ssh_key = {ssh_key}\n"
        f"ssh_user = {ssh_user}\n"
        f"ssh_host = {ssh_host}\n"
        f"local_port = {local_port}\n"
        f"remote_host = {remote_host}\n"
        f"remote_port = {remote_port}\n"
    )
    config_path.chmod(0o600)

    with VPN_CONF.open("a") as f:
        f.write(f"\n[{vpn_id}]\n")
        f.write(f"name = {vpn_name}\n")
        f.write(f"auth = ssh_tunnel\n")
        f.write(f"config = {config_file}\n")
        if depends_on:
            f.write(f"depends_on = {depends_on}\n")

    rprint(f"\n[green]✅ Tunnel SSH '{vpn_name}' créé avec succès ![/green]")
    rprint(f"  • {VPN_CONF}  (entrée ajoutée)")
    rprint(f"  • {config_path}  (chmod 600)")
    rprint(f"\n[blue]Équivalent SSH :[/blue]")
    rprint(f"  ssh -i {ssh_key} -L {local_port}:{remote_host}:{remote_port} -N {ssh_user}@{ssh_host}")
    if depends_on:
        rprint(f"  [yellow]Dépendance : {depends_on}[/yellow]")


# ── Public entry point ───────────────────────────────────────


def run_wizard() -> None:
    """Run the full interactive creation wizard."""
    rprint("\n[blue]══════════════════════════════════════════════════════════[/blue]")
    rprint("[blue]        Configurateur VPN — Assistant de création         [/blue]")
    rprint("[blue]══════════════════════════════════════════════════════════[/blue]\n")

    # ID
    rprint("[yellow]Identifiant du VPN[/yellow]")
    rprint("Choisissez un identifiant unique (lettres, chiffres, tirets)")
    rprint("Exemple : mon-vpn, vpn-prod, kore")
    while True:
        vpn_id = typer.prompt("ID du VPN")
        if vpn_id and _validate_id(vpn_id):
            break

    # Name
    rprint("\n[yellow]Nom du VPN[/yellow]")
    vpn_name = typer.prompt("Nom affiché", default=vpn_id)

    # Auth type
    rprint("\n[yellow]Type d'authentification[/yellow]")
    rprint("  1) password    — Mot de passe simple")
    rprint("  2) 2fa         — Authentification 2FA (FortiToken)")
    rprint("  3) saml        — Authentification SSO/SAML")
    rprint("  4) ssh_tunnel  — Tunnel SSH (port forwarding)")
    auth_choice = typer.prompt("Votre choix [1-4]")
    auth_map = {"1": AuthType.PASSWORD, "2": AuthType.TWO_FA, "3": AuthType.SAML, "4": AuthType.SSH_TUNNEL}
    auth = auth_map.get(auth_choice)
    if auth is None:
        rprint("[red]❌ Choix invalide[/red]")
        raise typer.Exit(1)

    # Optional dependency
    depends_on = _ask_dependency()

    # Delegate to type-specific wizard
    if auth in (AuthType.PASSWORD, AuthType.TWO_FA):
        _wizard_password_or_2fa(vpn_id, vpn_name, auth, depends_on)
    elif auth == AuthType.SAML:
        _wizard_saml(vpn_id, vpn_name, depends_on)
    else:
        _wizard_ssh(vpn_id, vpn_name, depends_on)

    # Find new entry index and show connect hint
    entries = load_entries()
    new_entry = next((e for e in entries if e.id == vpn_id), None)
    idx = new_entry.index if new_entry else "?"
    rprint(f"\n[blue]Vous pouvez maintenant vous connecter avec :[/blue]")
    rprint(f"  vpn connect {idx}")
