#!/bin/bash
# Installation du tray icon VPN pour Ubuntu
# Installe les dépendances, copie les fichiers et configure l'autostart

set -e

# === Couleurs ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}$1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error()   { echo -e "${RED}❌ $1${NC}"; }

# === Chemins ===
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TRAY_DIR="$HOME/.vpn/tray"
AUTOSTART_DIR="$HOME/.config/autostart"
APPLICATIONS_DIR="$HOME/.local/share/applications"

# === Vérification Ubuntu / GNOME ===
check_environment() {
    echo -e "${BLUE}══════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}   Installation du VPN Tray Icon                      ${NC}"
    echo -e "${BLUE}══════════════════════════════════════════════════════${NC}"
    echo ""

    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 n'est pas installé"
        exit 1
    fi
    log_success "Python 3 trouvé ($(python3 --version 2>&1))"

    # Vérifier que le script vpn principal est installé
    if [ ! -f "$HOME/vpn" ] && [ ! -L "$HOME/vpn" ]; then
        if [ ! -f "$SCRIPT_DIR/../vpn" ]; then
            log_error "Le script 'vpn' principal n'est pas installé."
            echo "  Exécutez d'abord : ./install.sh"
            exit 1
        fi
    fi
    log_success "Script vpn trouvé"
}

# === Installation des dépendances système ===
install_dependencies() {
    echo ""
    log_info "Vérification des dépendances Python/GTK..."

    local missing=()

    if ! python3 -c "import gi" 2>/dev/null; then
        missing+=("python3-gi")
    fi

    if ! python3 -c "import gi; gi.require_version('AppIndicator3', '0.1'); from gi.repository import AppIndicator3" 2>/dev/null; then
        missing+=("gir1.2-appindicator3-0.1")
    fi

    if ! python3 -c "import cairo" 2>/dev/null; then
        missing+=("python3-gi-cairo")
    fi

    if [ ${#missing[@]} -eq 0 ]; then
        log_success "Toutes les dépendances sont installées"
        return
    fi

    log_warning "Paquets manquants : ${missing[*]}"
    echo ""
    read -p "Installer via apt ? (O/n) " -n 1 -r
    echo ""

    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        sudo apt install -y "${missing[@]}"
        log_success "Dépendances installées"
    else
        log_error "Les dépendances sont requises. Installation annulée."
        exit 1
    fi
}

# === Copie des fichiers tray ===
install_tray_files() {
    echo ""
    log_info "Installation des fichiers du tray..."

    mkdir -p "$TRAY_DIR"
    cp "$SCRIPT_DIR/vpn_tray.py" "$TRAY_DIR/"
    cp "$SCRIPT_DIR/vpn_backend.py" "$TRAY_DIR/"
    cp "$SCRIPT_DIR/vpn_tray_launch.sh" "$TRAY_DIR/"
    chmod +x "$TRAY_DIR/vpn_tray.py" "$TRAY_DIR/vpn_tray_launch.sh"

    log_success "Fichiers installés dans $TRAY_DIR"
}

# === Création du fichier .desktop ===
create_desktop_entry() {
    echo ""
    log_info "Création des entrées .desktop..."

    mkdir -p "$AUTOSTART_DIR" "$APPLICATIONS_DIR"

    local desktop_content="[Desktop Entry]
Type=Application
Name=VPN Tray
GenericName=VPN Manager Tray Icon
Comment=Indicateur système pour gérer les connexions VPN
Exec=$TRAY_DIR/vpn_tray_launch.sh
Icon=network-vpn
Terminal=false
Categories=Network;System;
Keywords=vpn;network;tray;indicator;
StartupNotify=false
X-GNOME-Autostart-enabled=true"

    # Autostart (lancé à la connexion)
    echo "$desktop_content" > "$AUTOSTART_DIR/vpn-tray.desktop"
    log_success "Autostart configuré : $AUTOSTART_DIR/vpn-tray.desktop"

    # Menu des applications
    echo "$desktop_content" > "$APPLICATIONS_DIR/vpn-tray.desktop"
    log_success "Entrée application créée : $APPLICATIONS_DIR/vpn-tray.desktop"
}

# === Résumé ===
show_summary() {
    echo ""
    echo -e "${GREEN}══════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}   ✅ VPN Tray Icon installé avec succès !             ${NC}"
    echo -e "${GREEN}══════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "${BLUE}📁 Fichiers installés :${NC}"
    echo "   $TRAY_DIR/vpn_tray.py"
    echo "   $TRAY_DIR/vpn_backend.py"
    echo "   $AUTOSTART_DIR/vpn-tray.desktop"
    echo ""
    echo -e "${YELLOW}🚀 Pour lancer maintenant :${NC}"
    echo "   python3 $TRAY_DIR/vpn_tray.py &"
    echo ""
    echo -e "${BLUE}ℹ️  Le tray se lancera automatiquement à la prochaine connexion.${NC}"
    echo ""
}

# === Lancement optionnel ===
offer_launch() {
    read -p "Lancer le tray maintenant ? (O/n) " -n 1 -r
    echo ""

    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        # Tuer une éventuelle instance précédente
        pkill -f "vpn_tray.py" 2>/dev/null || true
        sleep 0.5

        "$TRAY_DIR/vpn_tray_launch.sh" &
        disown
        log_success "VPN Tray lancé ! Vérifiez votre barre système."
    fi
}

# === Point d'entrée ===
main() {
    check_environment
    install_dependencies
    install_tray_files
    create_desktop_entry
    show_summary
    offer_launch
}

main
