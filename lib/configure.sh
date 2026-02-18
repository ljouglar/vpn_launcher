#!/bin/bash
# lib/configure.sh - Configurateur interactif VPN

configure_vpn() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}        Configurateur VPN - Assistant de création          ${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    
    # 1. ID du VPN
    echo -e "${YELLOW}Identifiant du VPN${NC}"
    echo "Choisissez un identifiant unique (lettres, chiffres, tirets)"
    echo "Exemple: mon-vpn, vpn-prod, kore"
    read -p "ID du VPN : " vpn_id
    
    if [ -z "$vpn_id" ]; then
        log "❌ L'ID ne peut pas être vide" "$RED"
        return 1
    fi
    
    # Vérifier que l'ID n'existe pas déjà
    if grep -q "^\[${vpn_id}\]" "$VPN_CONF" 2>/dev/null; then
        log "❌ Un VPN avec l'ID '$vpn_id' existe déjà" "$RED"
        return 1
    fi
    
    # 2. Nom affiché
    echo ""
    echo -e "${YELLOW}Nom du VPN${NC}"
    echo "Nom descriptif qui sera affiché dans le menu"
    read -p "Nom : " vpn_name
    
    if [ -z "$vpn_name" ]; then
        vpn_name="$vpn_id"
    fi
    
    # 3. Type d'authentification
    echo ""
    echo -e "${YELLOW}Type d'authentification${NC}"
    echo "  1) password - Mot de passe simple"
    echo "  2) 2fa      - Authentification 2FA (FortiToken)"
    echo "  3) saml     - Authentification SSO/SAML"
    read -p "Votre choix [1-3] : " auth_choice
    
    case $auth_choice in
        1) auth_type="password" ;;
        2) auth_type="2fa" ;;
        3) auth_type="saml" ;;
        *)
            log "❌ Choix invalide" "$RED"
            return 1
            ;;
    esac
    
    # 4. Configuration selon le type
    if [ "$auth_type" = "saml" ]; then
        # === Mode SAML ===
        echo ""
        echo -e "${YELLOW}Configuration SAML${NC}"
        echo ""
        read -p "Hôte:port (ex: vpn.example.com:444) : " saml_host
        
        if [ -z "$saml_host" ]; then
            log "❌ L'hôte SAML est obligatoire" "$RED"
            return 1
        fi
        
        echo ""
        echo "Certificat SSL (optionnel)"
        echo "Pour obtenir le certificat :"
        echo "  echo | openssl s_client -connect $saml_host 2>/dev/null | openssl x509 -fingerprint -noout -sha256"
        read -p "Certificat SHA256 (laissez vide si inconnu) : " saml_cert
        
        # Créer l'entrée dans vpns.conf
        echo "" >> "$VPN_CONF"
        echo "[$vpn_id]" >> "$VPN_CONF"
        echo "name = $vpn_name" >> "$VPN_CONF"
        echo "auth = saml" >> "$VPN_CONF"
        echo "saml_host = $saml_host" >> "$VPN_CONF"
        if [ -n "$saml_cert" ]; then
            echo "saml_cert = $saml_cert" >> "$VPN_CONF"
        fi
        
        echo ""
        log "✅ VPN SAML '$vpn_name' créé avec succès !" "$GREEN"
        echo ""
        echo "Configuration ajoutée dans $VPN_CONF"
        
    else
        # === Mode password / 2fa ===
        echo ""
        echo -e "${YELLOW}Configuration du serveur${NC}"
        echo ""
        read -p "Hôte (ex: vpn.example.com ou 46.18.224.128) : " vpn_host
        read -p "Port (défaut: 443) : " vpn_port
        vpn_port="${vpn_port:-443}"
        
        if [ -z "$vpn_host" ]; then
            log "❌ L'hôte est obligatoire" "$RED"
            return 1
        fi
        
        read -p "Nom d'utilisateur : " vpn_username
        
        if [ -z "$vpn_username" ]; then
            log "❌ Le nom d'utilisateur est obligatoire" "$RED"
            return 1
        fi
        
        # Mot de passe
        echo ""
        if [ "$auth_type" = "2fa" ]; then
            echo "Mot de passe (le code 2FA sera demandé à chaque connexion)"
        else
            echo "Mot de passe"
        fi
        read -s -p "Mot de passe : " vpn_password
        echo ""
        
        # Certificat SSL
        echo ""
        echo "Certificat SSL"
        echo "Pour obtenir le certificat, exécutez :"
        echo "  echo | openssl s_client -connect $vpn_host:$vpn_port 2>/dev/null | openssl x509 -fingerprint -noout -sha256"
        echo ""
        read -p "Certificat SHA256 (sans les ':') : " vpn_cert
        
        if [ -z "$vpn_cert" ]; then
            log "⚠️  Attention : connexion sans vérification du certificat (non recommandé)" "$YELLOW"
        fi
        
        # Créer le fichier de configuration openfortivpn
        local config_file="${vpn_id}.conf"
        local config_path="$CONFIG_DIR/$config_file"
        
        cat > "$config_path" << EOF
# Configuration VPN: $vpn_name
host = $vpn_host
port = $vpn_port
username = $vpn_username
EOF
        
        # Ajouter le mot de passe si fourni
        if [ -n "$vpn_password" ]; then
            echo "password = $vpn_password" >> "$config_path"
        fi
        
        # Ajouter le certificat si fourni
        if [ -n "$vpn_cert" ]; then
            echo "trusted-cert = $vpn_cert" >> "$config_path"
        fi
        
        # Ajouter les paramètres réseau
        cat >> "$config_path" << EOF
set-routes = 1
set-dns = 0
pppd-use-peerdns = 0
EOF
        
        # Protéger le fichier
        chmod 600 "$config_path"
        
        # Créer l'entrée dans vpns.conf
        echo "" >> "$VPN_CONF"
        echo "[$vpn_id]" >> "$VPN_CONF"
        echo "name = $vpn_name" >> "$VPN_CONF"
        echo "auth = $auth_type" >> "$VPN_CONF"
        echo "config = $config_file" >> "$VPN_CONF"
        
        echo ""
        log "✅ VPN '$vpn_name' créé avec succès !" "$GREEN"
        echo ""
        echo "Configuration créée :"
        echo "  • $VPN_CONF (entrée ajoutée)"
        echo "  • $config_path (chmod 600)"
    fi
    
    echo ""
    echo -e "${BLUE}Vous pouvez maintenant vous connecter avec :${NC}"
    echo "  vpn connect $(vpn_count)"
    echo ""
    
    return 0
}
