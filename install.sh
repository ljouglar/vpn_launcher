#!/bin/bash
# Script d'installation VPN Manager - Version optimisée
# Ce script installe et configure le gestionnaire VPN multi-connexions

set -e

# === Couleurs ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# === Fonctions utilitaires ===
log_info() { echo -e "${BLUE}$1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }

# === Détection des chemins ===
INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_SOURCE="$INSTALL_DIR/vpn"
LIB_SOURCE="$INSTALL_DIR/lib"
TEMPLATES_DIR="$INSTALL_DIR/templates"

VPN_DIR="$HOME/.vpn"
CONFIG_DIR="$VPN_DIR/configs"
LOG_DIR="$VPN_DIR/logs"
SESSION_DIR="$VPN_DIR/sessions"
LIB_DIR="$VPN_DIR/lib"

SCRIPT_DEST="$HOME/vpn"
VPNS_CONF="$VPN_DIR/vpns.conf"

# === Vérification des prérequis ===
check_prerequisites() {
    echo -e "${BLUE}══════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}   Installation du Gestionnaire VPN Multi-Connexions ${NC}"
    echo -e "${BLUE}══════════════════════════════════════════════════════${NC}"
    echo ""
    
    log_info "Vérification des prérequis..."
    
    if ! command -v openfortivpn &> /dev/null; then
        log_error "openfortivpn n'est pas installé"
        echo ""
        echo "Pour installer openfortivpn :"
        echo "  • Ubuntu/Debian: sudo apt install openfortivpn"
        echo "  • Fedora/RHEL:   sudo dnf install openfortivpn"
        echo "  • Arch:          sudo pacman -S openfortivpn"
        exit 1
    fi
    
    log_success "openfortivpn est installé"
    
    if [ ! -f "$SCRIPT_SOURCE" ]; then
        log_error "Le fichier 'vpn' n'a pas été trouvé dans $INSTALL_DIR"
        exit 1
    fi
    
    if [ ! -d "$LIB_SOURCE" ]; then
        log_error "Le dossier 'lib/' n'a pas été trouvé dans $INSTALL_DIR"
        exit 1
    fi
}

# === Création de la structure ===
create_structure() {
    echo ""
    log_info "Création de la structure de dossiers..."
    
    mkdir -p "$CONFIG_DIR" "$LOG_DIR" "$SESSION_DIR" "$LIB_DIR"
    log_success "Dossiers créés"
}

# === Installation du script principal ===
install_script() {
    log_info "Installation du script vpn..."
    
    # Supprimer le lien/fichier existant
    [ -L "$SCRIPT_DEST" ] || [ -f "$SCRIPT_DEST" ] && rm -f "$SCRIPT_DEST"
    
    # Créer le lien symbolique
    ln -s "$SCRIPT_SOURCE" "$SCRIPT_DEST"
    chmod +x "$SCRIPT_SOURCE"
    
    log_success "Lien symbolique créé : ~/vpn -> $SCRIPT_SOURCE"
}

# === Installation des modules ===
install_libraries() {
    log_info "Installation des modules..."
    
    cp -r "$LIB_SOURCE"/* "$LIB_DIR/"
    chmod +x "$LIB_DIR"/*.sh
    
    log_success "Modules installés dans $LIB_DIR"
}

# === Installation des templates ===
install_templates() {
    log_info "Installation des configurations..."
    
    # vpns.conf
    if [ ! -f "$VPNS_CONF" ]; then
        cp "$TEMPLATES_DIR/vpns.conf.template" "$VPNS_CONF"
        log_success "Fichier vpns.conf créé"
    else
        log_info "Le fichier vpns.conf existe déjà"
    fi
    
    # example.conf
    local example_conf="$CONFIG_DIR/example.conf"
    if [ ! -f "$example_conf" ]; then
        cp "$TEMPLATES_DIR/example.conf.template" "$example_conf"
        chmod 600 "$example_conf"
        log_success "Exemple de configuration créé (chmod 600)"
    fi
    
    # README.md
    local readme="$VPN_DIR/README.md"
    if [ ! -f "$readme" ]; then
        cp "$TEMPLATES_DIR/README.md.template" "$readme"
        log_success "README créé"
    fi
}

# === Protection des fichiers sensibles ===
secure_configs() {
    log_info "Protection des fichiers de configuration..."
    find "$CONFIG_DIR" -type f -name "*.conf" -exec chmod 600 {} \;
    log_success "Permissions des fichiers .conf définies à 600"
}

# === Configuration du PATH ===
configure_path() {
    echo ""
    log_info "Configuration du PATH (optionnel)..."
    
    if [[ ":$PATH:" == *":$HOME:"* ]]; then
        log_success "Le script vpn est déjà accessible"
        return
    fi
    
    log_warning "Le dossier ~/vpn n'est pas dans le PATH"
    echo ""
    echo "Pour exécuter 'vpn' depuis n'importe où, ajoutez cette ligne à votre ~/.bashrc :"
    echo "  export PATH=\"\$HOME:\$PATH\""
    echo ""
    
    read -p "Voulez-vous l'ajouter automatiquement à ~/.bashrc ? (o/N) " -n 1 -r
    echo ""
    
    if [[ $REPLY =~ ^[Oo]$ ]]; then
        if ! grep -q "# VPN Manager PATH" "$HOME/.bashrc"; then
            {
                echo ""
                echo "# VPN Manager PATH"
                echo "export PATH=\"\$HOME:\$PATH\""
            } >> "$HOME/.bashrc"
            log_success "PATH ajouté à ~/.bashrc"
            log_warning "Exécutez 'source ~/.bashrc' ou ouvrez un nouveau terminal"
        else
            log_info "PATH déjà présent dans ~/.bashrc"
        fi
    fi
}

# === Résumé de l'installation ===
show_summary() {
    echo ""
    echo -e "${GREEN}══════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}   ✅ Installation terminée avec succès !              ${NC}"
    echo -e "${GREEN}══════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "${BLUE}📁 Structure installée :${NC}"
    echo "   ~/vpn                          → Lien symbolique vers le script"
    echo "   ~/.vpn/vpns.conf               → Configuration des VPNs"
    echo "   ~/.vpn/configs/                → Configurations openfortivpn (chmod 600)"
    echo "   ~/.vpn/logs/                   → Logs de connexion"
    echo "   ~/.vpn/lib/                    → Modules du script"
    echo ""
    echo -e "${YELLOW}🔄 Pour mettre à jour le script :${NC}"
    echo "   cd $INSTALL_DIR && git pull && ./install.sh"
    echo ""
}

# === Proposition du configurateur ===
offer_configurator() {
    local vpn_count=$(grep -c "^\[.*\]$" "$VPNS_CONF" 2>/dev/null || echo "0")
    
    if [ "$vpn_count" -eq 0 ]; then
        echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
        echo -e "${YELLOW}   Aucun VPN configuré - Configuration recommandée         ${NC}"
        echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
        echo ""
        echo -e "${BLUE}Voulez-vous configurer votre premier VPN maintenant ?${NC}"
        echo ""
        
        read -p "Lancer le configurateur ? (O/n) : " -n 1 -r
        echo ""
        
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            echo ""
            "$SCRIPT_DEST" configure
        else
            echo ""
            log_info "Vous pourrez le faire plus tard avec : ~/vpn configure"
        fi
    else
        log_info "VPNs configurés : $vpn_count"
        echo ""
        log_warning "Pour ajouter un nouveau VPN : ~/vpn configure"
    fi
}

# === Affichage des commandes utiles ===
show_usage() {
    echo ""
    echo -e "${YELLOW}📋 Commandes utiles :${NC}"
    echo "   ~/vpn                  # Menu interactif"
    echo "   ~/vpn configure        # Créer un nouveau VPN"
    echo "   ~/vpn list             # Lister les VPNs"
    echo "   ~/vpn help             # Aide complète"
    echo ""
    echo -e "${BLUE}📖 Documentation complète : cat ~/.vpn/README.md${NC}"
    echo ""
}

# === Point d'entrée principal ===
main() {
    check_prerequisites
    create_structure
    install_script
    install_libraries
    install_templates
    secure_configs
    configure_path
    show_summary
    offer_configurator
    show_usage
}

main
