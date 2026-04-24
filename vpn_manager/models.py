"""vpn_manager.models — Data model for VPN entries.

Single definition of every domain object used across the CLI,
the tray, the connect/disconnect logic, and the tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AuthType(str, Enum):
    """Authentication / connection type for a VPN or SSH tunnel entry."""

    PASSWORD = "password"
    TWO_FA = "2fa"
    SAML = "saml"
    SSH_TUNNEL = "ssh_tunnel"


@dataclass
class FortiVpnConfig:
    """Openfortivpn configuration file parameters.

    These values are read from ~/.vpn/configs/<name>.conf and merged
    into the parent VpnEntry at load time.
    """

    config_file: str  # basename, e.g. "my-vpn.conf"
    host: str = ""
    port: int = 443
    username: str = ""
    password: str = ""
    trusted_cert: str = ""


@dataclass
class SamlConfig:
    """SAML/SSO connection parameters (stored inline in vpns.conf)."""

    saml_host: str  # "vpn.example.com:444"
    saml_cert: str = ""  # auto-detected if empty


@dataclass
class SshTunnelConfig:
    """SSH tunnel / port-forwarding parameters.

    These values are read from ~/.vpn/configs/<name>.conf and merged
    into the parent VpnEntry at load time.
    """

    config_file: str  # basename, e.g. "my-tunnel.conf"
    ssh_key: str = ""
    ssh_user: str = ""
    ssh_host: str = ""
    local_port: int = 0
    remote_host: str = ""
    remote_port: int = 0


@dataclass
class VpnEntry:
    """A single VPN or SSH tunnel as defined in vpns.conf.

    Attributes:
        id:          Unique machine identifier, e.g. "my-vpn" (INI section name).
        name:        Human-readable display name shown in menus.
        auth:        Authentication / connection type.
        index:       1-based position in vpns.conf (used by CLI shortcuts).
        depends_on:  ID of another VpnEntry that must be connected first.
        forti_cfg:   Populated for password / 2fa auth types.
        saml_cfg:    Populated for saml auth type.
        ssh_cfg:     Populated for ssh_tunnel auth type.
        connected:   Runtime flag — True when a live session is detected.
        pid:         PID of the running VPN / tunnel process (runtime).
    """

    id: str
    name: str
    auth: AuthType
    index: int

    depends_on: Optional[str] = None

    # Type-specific config — exactly one will be set (or none before load)
    forti_cfg: Optional[FortiVpnConfig] = None
    saml_cfg: Optional[SamlConfig] = None
    ssh_cfg: Optional[SshTunnelConfig] = None

    # Runtime state (not persisted)
    connected: bool = False
    pid: Optional[int] = None

    # ── Convenience helpers ──────────────────────────────────

    @property
    def is_forti(self) -> bool:
        """True for password and 2fa entries (use openfortivpn)."""
        return self.auth in (AuthType.PASSWORD, AuthType.TWO_FA)

    @property
    def is_saml(self) -> bool:
        return self.auth == AuthType.SAML

    @property
    def is_ssh_tunnel(self) -> bool:
        return self.auth == AuthType.SSH_TUNNEL

    @property
    def type_icon(self) -> str:
        """Emoji icon for display in menus and status output."""
        return "🔗" if self.is_ssh_tunnel else "🔒"

    def __repr__(self) -> str:  # pragma: no cover
        state = "✅" if self.connected else "○"
        return f"VpnEntry({state} {self.id!r} auth={self.auth.value})"


@dataclass
class Profile:
    """A named group of VPN IDs to connect/disconnect together.

    Attributes:
        id:       Unique machine identifier (INI section name), e.g. "bureau".
        name:     Human-readable display name.
        vpn_ids:  Ordered list of VpnEntry IDs to connect as a group.
    """

    id: str
    name: str
    vpn_ids: list[str] = field(default_factory=list)
