"""VPN Tray Icon — System tray indicator for vpn_launcher on Ubuntu / GNOME.

Provides an AppIndicator3 icon in the GNOME top bar that shows the
number of connected VPNs and lets the user toggle each one directly
from the dropdown menu.

This module imports vpn_manager directly — no subprocess call to the
CLI script is needed for status polling or disconnect operations.
Connect actions still open a terminal because the flow may require
interactive input (sudo password, 2FA code, SAML browser).

Dependencies (Ubuntu):
    sudo apt install gir1.2-appindicator3-0.1 python3-gi python3-gi-cairo
    pip install vpn-manager   # or: pip install -e .
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

# ── Ensure the project root is importable when running from the tray/ dir ────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── GTK / AppIndicator imports ────────────────────────────────────────────────
try:
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("AppIndicator3", "0.1")
    from gi.repository import AppIndicator3, GLib, Gtk
    import cairo
except (ImportError, ValueError) as exc:
    print(f"Erreur : dépendances manquantes — {exc}", file=sys.stderr)
    print(
        "Installez-les avec :\n"
        "  sudo apt install gir1.2-appindicator3-0.1 python3-gi python3-gi-cairo",
        file=sys.stderr,
    )
    sys.exit(1)

# Optional desktop notifications
try:
    gi.require_version("Notify", "0.7")
    from gi.repository import Notify

    Notify.init("VPN Tray")
    _HAS_NOTIFY = True
except Exception:
    _HAS_NOTIFY = False

# ── vpn_manager imports (single source of truth) ──────────────────────────────
from vpn_manager import config as _cfg
from vpn_manager import disconnect as _disc
from vpn_manager.config import load_entries
from vpn_manager.models import VpnEntry
from vpn_manager.session import attach_session_state
from vpn_manager.status import count_connected

# ── Constants ──────────────────────────────────────────────────────────────────

REFRESH_SECONDS = 5
ICON_RENDER_SIZE = 128
APP_ID = "vpn-tray-indicator"

# ── Terminal discovery ─────────────────────────────────────────────────────────

_TERMINALS = [
    ("gnome-terminal", ["gnome-terminal", "--"]),
    ("x-terminal-emulator", ["x-terminal-emulator", "-e"]),
    ("xterm", ["xterm", "-e"]),
]


def _find_terminal() -> Optional[List[str]]:
    for cmd, argv in _TERMINALS:
        if shutil.which(cmd):
            return argv
    return None


def _find_vpn_cli() -> Optional[str]:
    """Locate the vpn CLI entry point (installed script or cli.py)."""
    candidates = [
        shutil.which("vpn"),
        str(Path.home() / "vpn"),
        str(Path(__file__).resolve().parent.parent / "cli.py"),
    ]
    for c in candidates:
        if c and Path(c).exists() and os.access(c, os.X_OK):
            return c
    return None


# ── Icon factory ───────────────────────────────────────────────────────────────


class _IconFactory:
    """Generates numbered shield PNG icons with Cairo and caches them on disk."""

    def __init__(self, directory: str) -> None:
        self._dir = directory
        self._size = ICON_RENDER_SIZE
        for n in range(10):
            self._render(n)

    def path(self, count: int) -> str:
        return os.path.join(self._dir, f"vpn-{min(count, 9)}.png")

    def _render(self, count: int) -> None:
        S = self._size
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, S, S)
        ctx = cairo.Context(surface)

        cx, cy = S / 2, S * 0.48
        w, h = S * 0.78, S * 0.88
        top = cy - h * 0.45
        bottom = cy + h * 0.55

        # Outline
        self._shield_path(ctx, cx, cy, w, h, top, bottom)
        ctx.set_source_rgba(0, 0, 0, 0.25)
        ctx.set_line_width(S * 0.03)
        ctx.stroke()

        # Fill
        self._shield_path(ctx, cx, cy, w, h, top, bottom)
        if count == 0:
            ctx.set_source_rgba(0.50, 0.52, 0.55, 0.92)
        else:
            ctx.set_source_rgba(0.16, 0.65, 0.35, 0.95)
        ctx.fill()

        # Counter text
        ctx.set_source_rgba(1, 1, 1, 0.95)
        ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        text = "—" if count == 0 else str(count)
        ctx.set_font_size(S * (0.38 if count == 0 else 0.42))
        ext = ctx.text_extents(text)
        text_y = cy + h * 0.05
        ctx.move_to(
            cx - ext.width / 2 - ext.x_bearing,
            text_y - ext.height / 2 - ext.y_bearing,
        )
        ctx.show_text(text)
        surface.write_to_png(self.path(count))

    @staticmethod
    def _shield_path(ctx, cx, cy, w, h, top, bottom) -> None:
        left, right = cx - w / 2, cx + w / 2
        shoulder = cy - h * 0.15
        ctx.new_path()
        ctx.move_to(cx, top)
        ctx.line_to(right, top + h * 0.06)
        ctx.line_to(right, shoulder)
        ctx.curve_to(right, cy + h * 0.20, cx + w * 0.12, bottom - h * 0.05, cx, bottom)
        ctx.curve_to(cx - w * 0.12, bottom - h * 0.05, left, cy + h * 0.20, left, shoulder)
        ctx.line_to(left, top + h * 0.06)
        ctx.close_path()


# ── Notifications ──────────────────────────────────────────────────────────────


def _notify(title: str, body: str) -> None:
    if not _HAS_NOTIFY:
        return
    try:
        Notify.Notification.new(title, body, "network-vpn").show()
    except Exception:
        pass


# ── Main tray class ────────────────────────────────────────────────────────────


class VpnTray:
    """AppIndicator3-based system tray icon for vpn_launcher."""

    def __init__(self) -> None:
        _cfg.ensure_config_dir()
        self._cli = _find_vpn_cli()  # used only for connect (needs a terminal)
        self._icon_dir = tempfile.mkdtemp(prefix="vpn-tray-")
        self._icons = _IconFactory(self._icon_dir)
        self._prev_connected: set[str] = set()

        self._indicator = AppIndicator3.Indicator.new(
            APP_ID,
            self._icons.path(0),
            AppIndicator3.IndicatorCategory.COMMUNICATIONS,
        )
        self._indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self._indicator.set_title("VPN Manager")

        self._update()
        GLib.timeout_add_seconds(REFRESH_SECONDS, self._periodic_update)

    # ── Status refresh ─────────────────────────────────────────

    def _load_entries(self) -> List[VpnEntry]:
        entries = load_entries()
        return attach_session_state(entries)

    def _update(self) -> None:
        """Refresh VPN status and rebuild the dropdown menu."""
        entries = self._load_entries()
        connected_count = count_connected(entries)
        connected_ids = {e.id for e in entries if e.connected}

        # Desktop notifications on state change
        for entry in entries:
            if entry.connected and entry.id not in self._prev_connected:
                _notify("VPN connecté", f"{entry.name} est maintenant connecté")
            elif not entry.connected and entry.id in self._prev_connected:
                _notify("VPN déconnecté", f"{entry.name} a été déconnecté")
        self._prev_connected = connected_ids

        self._indicator.set_icon_full(
            self._icons.path(connected_count),
            f"{connected_count} VPN connecté(s)",
        )
        self._indicator.set_menu(self._build_menu(entries, connected_count))

    def _build_menu(self, entries: List[VpnEntry], connected_count: int) -> Gtk.Menu:
        menu = Gtk.Menu()

        # Header
        dot = "🟢" if connected_count else "⚪"
        header = Gtk.MenuItem(label=f" {dot}  {connected_count} VPN connecté(s)")
        header.set_sensitive(False)
        menu.append(header)
        menu.append(Gtk.SeparatorMenuItem())

        if not entries:
            empty = Gtk.MenuItem(label="  Aucun VPN configuré")
            empty.set_sensitive(False)
            menu.append(empty)
        else:
            for entry in entries:
                bullet = "●" if entry.connected else "○"
                dep_info = ""
                if entry.depends_on:
                    dep = next((e for e in entries if e.id == entry.depends_on), None)
                    if dep:
                        dep_info = f" (← {dep.name})"
                label = f"  {bullet} {entry.type_icon}  {entry.name}{dep_info}"
                item = Gtk.MenuItem(label=label)
                item.connect("activate", self._on_toggle, entry, entries)
                menu.append(item)

        menu.append(Gtk.SeparatorMenuItem())

        if connected_count > 1:
            da = Gtk.MenuItem(label="  Tout déconnecter")
            da.connect("activate", self._on_disconnect_all, entries)
            menu.append(da)
            menu.append(Gtk.SeparatorMenuItem())

        ref = Gtk.MenuItem(label="  Rafraîchir")
        ref.connect("activate", lambda _w: self._update())
        menu.append(ref)

        quit_item = Gtk.MenuItem(label="  Quitter")
        quit_item.connect("activate", self._on_quit)
        menu.append(quit_item)

        menu.show_all()
        return menu

    # ── Callbacks ──────────────────────────────────────────────

    def _on_toggle(self, _widget, entry: VpnEntry, entries: List[VpnEntry]) -> None:
        if entry.connected:
            # Disconnect directly via vpn_manager (no subprocess needed)
            _disc.disconnect_entry(
                entry,
                entries,
                ask_cascade=lambda _deps: True,  # tray always cascades silently
            )
            GLib.timeout_add_seconds(4, self._update_once)
        else:
            # Connect requires a terminal (interactive auth flows)
            self._open_connect_terminal(entry)
            GLib.timeout_add_seconds(10, self._update_once)

    def _on_disconnect_all(self, _widget, entries: List[VpnEntry]) -> None:
        _disc.disconnect_all(entries, ask_cascade=lambda _deps: True)
        GLib.timeout_add_seconds(5, self._update_once)

    def _on_quit(self, _widget) -> None:
        shutil.rmtree(self._icon_dir, ignore_errors=True)
        Gtk.main_quit()

    # ── Helpers ────────────────────────────────────────────────

    def _open_connect_terminal(self, entry: VpnEntry) -> None:
        """Open a terminal to run the interactive connect flow."""
        terminal = _find_terminal()
        if not terminal or not self._cli:
            _notify("VPN Tray", f"Impossible d'ouvrir un terminal pour connecter {entry.name}")
            return
        cmd = (
            f'"{self._cli}" connect {entry.index}; '
            'echo ""; echo "Appuyez sur Entrée pour fermer…"; read'
        )
        subprocess.Popen(terminal + ["bash", "-c", cmd])

    def _update_once(self) -> bool:
        self._update()
        return False  # one-shot

    def _periodic_update(self) -> bool:
        self._update()
        return True  # keep repeating


# ── Entry point ────────────────────────────────────────────────────────────────


def main() -> None:
    tray = VpnTray()  # noqa: F841 — keep alive
    try:
        Gtk.main()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
