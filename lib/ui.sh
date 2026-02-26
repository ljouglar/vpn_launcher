#!/bin/bash
# lib/ui.sh - Interface utilisateur et aide

show_menu() {
    local count=$(vpn_count)
    echo ""
    echo -e "${BLUE}=== Gestionnaire VPN ===${NC}"
    echo ""
    check_status
    echo ""
    list_vpns
    echo ""
    echo "  c) Se connecter"
    echo "  d) Se déconnecter"
    echo "  s) Statut"
    echo "  n) Configurer un nouveau VPN"
    echo "  q) Quitter"
    echo ""
    read -p "Votre choix: " choice

    case $choice in
        c|C) connect ;;
        d|D) disconnect ;;
        s|S) check_status ;;
        n|N) configure_vpn ;;
        q|Q) exit 0 ;;
        *)
            if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$count" -gt 0 ] && [ "$choice" -ge 1 ] && [ "$choice" -le "$count" ]; then
                connect "$choice"
            else
                log "❌ Choix invalide" "$RED"
            fi
            ;;
    esac
}

show_help() {
    echo "Usage: vpn [commande] [options]"
    echo ""
    echo "Commandes:"
    echo "  connect [1-$(vpn_count)]           Se connecter à un VPN (cumulable)"
    echo "  disconnect [id|numéro|pid|all]  Se déconnecter d'un VPN spécifique"
    echo "                                   - Sans argument : menu interactif"
    echo "                                   - ID du VPN : ex. 'koesio-sso'"
    echo "                                   - Numéro : ex. '1' (premier connecté)"
    echo "                                   - PID : ex. '322169' (VPN non tracké)"
    echo "                                   - 'all' : tout déconnecter"
    echo "  status                          Afficher le statut de tous les VPNs"
    echo "                                   (trackés et non trackés)"
    echo "  list                            Lister les VPNs disponibles"
    echo "  configure                       Assistant de création de VPN"
    echo "  menu                            Menu interactif (par défaut)"
    echo "  help                            Afficher cette aide"
    echo ""
    echo "Multi-VPN:"
    echo "  Les VPNs routant vers des réseaux différents peuvent"
    echo "  être lancés simultanément (ex: KORE + SSO)."
    echo ""
    echo "Configuration:"
    echo "  $VPN_CONF"
    echo ""
    echo "Exemples:"
    echo "  vpn                        # Menu interactif"
    echo "  vpn configure              # Créer un nouveau VPN"
    echo "  vpn connect 1              # Se connecter au premier VPN"
    echo "  vpn status                 # Voir tous les VPNs (trackés et non trackés)"
    echo "  vpn disconnect             # Déconnexion interactive"
    echo "  vpn disconnect koesio-sso  # Déconnecter un VPN par ID"
    echo "  vpn disconnect 2           # Déconnecter le 2e VPN connecté"
    echo "  vpn disconnect 322169      # Déconnecter par PID (VPN non tracké)"
    echo "  vpn disconnect all         # Tout déconnecter"
}
