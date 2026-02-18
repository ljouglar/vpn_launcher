#!/bin/bash
# lib/core.sh - Fonctions de base et configuration globale

# === Chemins ===
VPN_DIR="$HOME/.vpn"
VPN_CONF="$VPN_DIR/vpns.conf"
CONFIG_DIR="$VPN_DIR/configs"
LOG_DIR="$VPN_DIR/logs"
SESSION_DIR="$VPN_DIR/sessions"

mkdir -p "$LOG_DIR" "$SESSION_DIR"

# === Couleurs ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# === Timeouts par défaut par mode d'auth ===
declare -A DEFAULT_TIMEOUTS
DEFAULT_TIMEOUTS[password]=20
DEFAULT_TIMEOUTS[2fa]=30
DEFAULT_TIMEOUTS[saml]=60

# ============================================================
#  Fonctions utilitaires
# ============================================================

log() {
    echo -e "${2}$1${NC}"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_DIR/vpn.log"
}

open_browser() {
    local url="$1"
    
    # Essayer différentes commandes pour ouvrir le navigateur
    # xdg-open est le standard sur Linux (fonctionne avec GNOME, KDE, XFCE, etc.)
    if command -v xdg-open &> /dev/null; then
        xdg-open "$url" &> /dev/null &
        return 0
    elif command -v gnome-open &> /dev/null; then
        gnome-open "$url" &> /dev/null &
        return 0
    elif command -v kde-open &> /dev/null; then
        kde-open "$url" &> /dev/null &
        return 0
    elif command -v firefox &> /dev/null; then
        firefox "$url" &> /dev/null &
        return 0
    elif command -v google-chrome &> /dev/null; then
        google-chrome "$url" &> /dev/null &
        return 0
    elif command -v chromium &> /dev/null; then
        chromium "$url" &> /dev/null &
        return 0
    else
        return 1
    fi
}
