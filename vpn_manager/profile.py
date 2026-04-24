"""vpn_manager.profile — Profile management (named groups of VPNs).

A profile is a named set of VPN IDs that can be connected/disconnected
together with a single command.

Profiles are stored in ``~/.vpn/profiles.conf`` using the same INI format
as ``vpns.conf``::

    [bureau]
    name = Bureau
    vpns = vpn-corp, vpn-dev, tunnel-db

    [home]
    name = Home (Vendredi)
    vpns = vpn-corp, vpn-dev, tunnel-db, tunnel-6
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from .config import VPN_DIR, _parse_ini
from .models import Profile

# ── Paths ────────────────────────────────────────────────────

PROFILES_CONF = VPN_DIR / "profiles.conf"

_PROFILES_SKELETON = """\
# VPN Manager — profils
# Format : [profile-id]
#   name = Nom affiché
#   vpns = id1, id2, id3   (IDs des VPNs à connecter ensemble)
#
# Exemple :
# [bureau]
# name = Bureau
# vpns = vpn-corp, vpn-dev, tunnel-db
#
# [home]
# name = Home (Vendredi)
# vpns = vpn-corp, vpn-dev, tunnel-db, tunnel-6
"""


# ── Public API ───────────────────────────────────────────────


def load_profiles(conf_path: Path = PROFILES_CONF) -> List[Profile]:
    """Parse *conf_path* and return an ordered list of :class:`Profile` objects."""
    if not conf_path.exists():
        return []

    profiles: List[Profile] = []
    for section_id, props in _parse_ini(conf_path):
        raw_vpns = props.get("vpns", "")
        vpn_ids = [v.strip() for v in raw_vpns.split(",") if v.strip()]
        profiles.append(
            Profile(
                id=section_id,
                name=props.get("name", section_id),
                vpn_ids=vpn_ids,
            )
        )
    return profiles


def get_profile_by_id(profile_id: str, conf_path: Path = PROFILES_CONF) -> Optional[Profile]:
    """Return the Profile with the given *profile_id*, or None."""
    return next((p for p in load_profiles(conf_path) if p.id == profile_id), None)


def save_profile(profile: Profile, conf_path: Path = PROFILES_CONF) -> None:
    """Write or update *profile* in *conf_path*.

    If a profile with the same ID already exists, it is replaced in-place.
    Otherwise the profile is appended. The file is created with a skeleton
    header if it does not yet exist.
    """
    profiles = load_profiles(conf_path)

    found = False
    for i, p in enumerate(profiles):
        if p.id == profile.id:
            profiles[i] = profile
            found = True
            break
    if not found:
        profiles.append(profile)

    _write_profiles(profiles, conf_path)


def delete_profile(profile_id: str, conf_path: Path = PROFILES_CONF) -> bool:
    """Remove the profile identified by *profile_id*.

    Returns:
        True  if the profile was found and removed.
        False if no profile with that ID existed.
    """
    profiles = load_profiles(conf_path)
    filtered = [p for p in profiles if p.id != profile_id]
    if len(filtered) == len(profiles):
        return False
    _write_profiles(filtered, conf_path)
    return True


# ── Internal helpers ─────────────────────────────────────────


def _write_profiles(profiles: List[Profile], conf_path: Path = PROFILES_CONF) -> None:
    """Serialise *profiles* back to *conf_path*, preserving the skeleton header."""
    lines: List[str] = [_PROFILES_SKELETON]
    for p in profiles:
        lines.append(f"\n[{p.id}]\n")
        lines.append(f"name = {p.name}\n")
        lines.append(f"vpns = {', '.join(p.vpn_ids)}\n")

    conf_path.write_text("".join(lines))
    conf_path.chmod(0o600)
