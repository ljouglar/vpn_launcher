#!/usr/bin/env python3
"""VPN Tray Icon — System tray indicator for vpn_launcher on Ubuntu.

Provides an AppIndicator3 icon in the GNOME top bar that shows
how many VPNs are currently connected and lets the user toggle
each VPN directly from the dropdown menu.

Dependencies (Ubuntu):
    sudo apt install gir1.2-appindicator3-0.1 python3-gi python3-gi-cairo
"""

import os
import shutil
import sys
import tempfile

# ── Ensure imports from the same directory work ──────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── GTK / AppIndicator imports ───────────────────────────────
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

from vpn_backend import (  # noqa: E402
    VpnEntry,
    connect_vpn,
    disconnect_all_vpns,
    disconnect_vpn,
    find_vpn_script,
    get_all_vpn_status,
)

# ── Constants ────────────────────────────────────────────────

REFRESH_SECONDS = 5  # Status polling interval
ICON_RENDER_SIZE = 128  # Render large; the system scales down for the panel
APP_ID = "vpn-tray-indicator"


# ── Icon generator ───────────────────────────────────────────


class _IconFactory:
    """Generates numbered shield icons with Cairo and caches them on disk."""

    def __init__(self, directory: str):
        self._dir = directory
        self._size = ICON_RENDER_SIZE
        self._generate_all()

    # Public ───────────────────────────────────────────────────

    def path(self, count: int) -> str:
        """Absolute path to the PNG icon for *count* active VPNs."""
        return os.path.join(self._dir, f"vpn-{min(count, 9)}.png")

    # Private ──────────────────────────────────────────────────

    def _generate_all(self):
        for n in range(10):
            self._render(n)

    def _render(self, count: int):
        S = self._size
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, S, S)
        ctx = cairo.Context(surface)

        cx = S / 2
        cy = S * 0.48
        w = S * 0.78
        h = S * 0.88
        top = cy - h * 0.45
        bottom = cy + h * 0.55

        # ── Subtle outline (visibility on both light & dark themes) ──
        self._shield_path(ctx, cx, cy, w, h, top, bottom)
        ctx.set_source_rgba(0, 0, 0, 0.25)
        ctx.set_line_width(S * 0.03)
        ctx.stroke()

        # ── Shield fill ──
        self._shield_path(ctx, cx, cy, w, h, top, bottom)
        if count == 0:
            ctx.set_source_rgba(0.50, 0.52, 0.55, 0.92)  # muted grey
        else:
            ctx.set_source_rgba(0.16, 0.65, 0.35, 0.95)  # vivid green
        ctx.fill()

        # ── Inner text / symbol ──
        ctx.set_source_rgba(1, 1, 1, 0.95)
        text_y = cy + h * 0.05

        ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        if count == 0:
            ctx.set_font_size(S * 0.38)
            text = "—"
        else:
            ctx.set_font_size(S * 0.42)
            text = str(count)

        ext = ctx.text_extents(text)
        ctx.move_to(
            cx - ext.width / 2 - ext.x_bearing,
            text_y - ext.height / 2 - ext.y_bearing,
        )
        ctx.show_text(text)

        surface.write_to_png(self.path(count))

    @staticmethod
    def _shield_path(ctx, cx, cy, w, h, top, bottom):
        """Trace a shield / badge outline."""
        left = cx - w / 2
        right = cx + w / 2
        shoulder = cy - h * 0.15

        ctx.new_path()
        ctx.move_to(cx, top)
        ctx.line_to(right, top + h * 0.06)
        ctx.line_to(right, shoulder)
        ctx.curve_to(
            right,
            cy + h * 0.20,
            cx + w * 0.12,
            bottom - h * 0.05,
            cx,
            bottom,
        )
        ctx.curve_to(
            cx - w * 0.12,
            bottom - h * 0.05,
            left,
            cy + h * 0.20,
            left,
            shoulder,
        )
        ctx.line_to(left, top + h * 0.06)
        ctx.close_path()


# ── Main tray class ──────────────────────────────────────────


class VpnTray:
    """AppIndicator3-based system tray icon for vpn_launcher."""

    def __init__(self):
        # Locate the CLI script
        self.script_path = find_vpn_script()
        if not self.script_path:
            dialog = Gtk.MessageDialog(
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="VPN Tray",
                secondary_text=(
                    "Le script « vpn » est introuvable.\n"
                    "Vérifiez l'installation de vpn_launcher."
                ),
            )
            dialog.run()
            dialog.destroy()
            sys.exit(1)

        # Generate icons in a temporary directory
        self._icon_dir = tempfile.mkdtemp(prefix="vpn-tray-")
        self._icons = _IconFactory(self._icon_dir)

        # Create the indicator
        self._indicator = AppIndicator3.Indicator.new(
            APP_ID,
            self._icons.path(0),
            AppIndicator3.IndicatorCategory.COMMUNICATIONS,
        )
        self._indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self._indicator.set_title("VPN Manager")

        # Track previous state for notifications
        self._prev_connected: set = set()

        # Initial build
        self._update()

        # Periodic status refresh
        GLib.timeout_add_seconds(REFRESH_SECONDS, self._periodic_update)

    # ── Menu (re)build ───────────────────────────────────────

    def _update(self):
        """Refresh VPN status and rebuild the dropdown menu."""
        entries = get_all_vpn_status()
        connected_count = sum(1 for e in entries if e.connected)
        connected_ids = {e.id for e in entries if e.connected}

        # ── Desktop notifications on state changes ──
        if _HAS_NOTIFY:
            for entry in entries:
                if entry.connected and entry.id not in self._prev_connected:
                    _notify("VPN connecté", f"{entry.name} est maintenant connecté")
                elif not entry.connected and entry.id in self._prev_connected:
                    _notify("VPN déconnecté", f"{entry.name} a été déconnecté")

        self._prev_connected = connected_ids

        # ── Update icon ──
        self._indicator.set_icon_full(
            self._icons.path(connected_count),
            f"{connected_count} VPN connecté(s)",
        )

        # ── Build the menu ──
        menu = Gtk.Menu()

        # Header
        dot = "🟢" if connected_count else "⚪"
        header = Gtk.MenuItem(label=f" {dot}  {connected_count} VPN connecté(s)")
        header.set_sensitive(False)
        menu.append(header)
        menu.append(Gtk.SeparatorMenuItem())

        # VPN list
        if not entries:
            empty = Gtk.MenuItem(label="  Aucun VPN configuré")
            empty.set_sensitive(False)
            menu.append(empty)
        else:
            for entry in entries:
                bullet = "●" if entry.connected else "○"
                label = f"  {bullet}  {entry.name}"
                item = Gtk.MenuItem(label=label)
                item.connect("activate", self._on_toggle, entry)
                menu.append(item)

        menu.append(Gtk.SeparatorMenuItem())

        # Disconnect all (only when ≥ 2 VPNs are up)
        if connected_count > 1:
            da_item = Gtk.MenuItem(label="  Tout déconnecter")
            da_item.connect("activate", self._on_disconnect_all)
            menu.append(da_item)
            menu.append(Gtk.SeparatorMenuItem())

        # Refresh
        ref_item = Gtk.MenuItem(label="  Rafraîchir")
        ref_item.connect("activate", lambda _w: self._update())
        menu.append(ref_item)

        # Quit
        quit_item = Gtk.MenuItem(label="  Quitter")
        quit_item.connect("activate", self._on_quit)
        menu.append(quit_item)

        menu.show_all()
        self._indicator.set_menu(menu)

    # ── Callbacks ────────────────────────────────────────────

    def _on_toggle(self, _widget, entry: VpnEntry):
        """Connect or disconnect the clicked VPN."""
        if entry.connected:
            disconnect_vpn(entry, self.script_path)
            GLib.timeout_add_seconds(4, self._update_once)
        else:
            connect_vpn(entry, self.script_path)
            # Connection takes longer (password / 2FA / SAML)
            GLib.timeout_add_seconds(8, self._update_once)

    def _on_disconnect_all(self, _widget):
        disconnect_all_vpns(self.script_path)
        GLib.timeout_add_seconds(5, self._update_once)

    def _on_quit(self, _widget):
        shutil.rmtree(self._icon_dir, ignore_errors=True)
        Gtk.main_quit()

    # ── Helpers ──────────────────────────────────────────────

    def _update_once(self) -> bool:
        """One-shot refresh (for GLib.timeout_add callbacks)."""
        self._update()
        return False  # do not repeat

    def _periodic_update(self) -> bool:
        """Periodic refresh callback."""
        self._update()
        return True  # keep repeating


# ── Notifications helper ─────────────────────────────────────


def _notify(title: str, body: str):
    """Show a desktop notification (if libnotify is available)."""
    if not _HAS_NOTIFY:
        return
    try:
        n = Notify.Notification.new(title, body, "network-vpn")
        n.show()
    except Exception:
        pass


# ── Entry point ──────────────────────────────────────────────


def main():
    tray = VpnTray()  # noqa: F841 — prevent GC of the indicator
    try:
        Gtk.main()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
