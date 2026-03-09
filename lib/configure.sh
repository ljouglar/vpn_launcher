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
    echo "  1) password    - Mot de passe simple"
    echo "  2) 2fa         - Authentification 2FA (FortiToken)"
    echo "  3) saml        - Authentification SSO/SAML"
    echo "  4) ssh_tunnel  - Tunnel SSH (port forwarding)"
    read -p "Votre choix [1-4] : " auth_choice
    
    case $auth_choice in
        1) auth_type="password" ;;
        2) auth_type="2fa" ;;
        3) auth_type="saml" ;;
        4) auth_type="ssh_tunnel" ;;
        *)
            log "❌ Choix invalide" "$RED"
            return 1
            ;;
    esac
    
    # 3b. Dépendance optionnelle
    local depends_on=""
    local existing_count=$(vpn_count)
    if [ "$existing_count" -gt 0 ]; then
        echo ""
        echo -e "${YELLOW}Dépendance (optionnel)${NC}"
        echo "Ce VPN/tunnel dépend-il d'une autre connexion ?"
        echo "  0) Aucune dépendance"
        for i in $(seq 1 "$existing_count"); do
            local dep_id=$(vpn_id_at "$i")
            local dep_display=$(vpn_get "$dep_id" "name" "$dep_id")
            echo "  $i) $dep_display"
        done
        read -p "Votre choix [0-$existing_count] : " dep_choice
        
        if [[ "$dep_choice" =~ ^[0-9]+$ ]] && [ "$dep_choice" -ge 1 ] && [ "$dep_choice" -le "$existing_count" ]; then
            depends_on=$(vpn_id_at "$dep_choice")
        fi
    fi
    
    # 4. Configuration selon le type
    if [ "$auth_type" = "ssh_tunnel" ]; then
        # === Mode SSH Tunnel ===
        echo ""
        echo -e "${YELLOW}Configuration du tunnel SSH${NC}"
        echo ""
        read -p "Clé SSH (ex: /home/$USER/.ssh/id_rsa) : " ssh_key
        
        if [ -z "$ssh_key" ]; then
            ssh_key="$HOME/.ssh/id_rsa"
            echo "  → Utilisation de la clé par défaut: $ssh_key"
        fi
        
        if [ ! -f "$ssh_key" ]; then
            log "⚠️  Attention: la clé $ssh_key n'existe pas encore" "$YELLOW"
        fi
        
        read -p "Utilisateur SSH (ex: root) : " ssh_user
        if [ -z "$ssh_user" ]; then
            log "❌ L'utilisateur SSH est obligatoire" "$RED"
            return 1
        fi
        
        read -p "Hôte SSH / proxy de rebond (ex: 10.244.18.22) : " ssh_host
        if [ -z "$ssh_host" ]; then
            log "❌ L'hôte SSH est obligatoire" "$RED"
            return 1
        fi
        
        echo ""
        echo -e "${YELLOW}Port forwarding${NC}"
        read -p "Port local (ex: 33070) : " local_port
        if [ -z "$local_port" ]; then
            log "❌ Le port local est obligatoire" "$RED"
            return 1
        fi
        
        read -p "Hôte distant / destination (ex: 91.216.43.88) : " remote_host
        if [ -z "$remote_host" ]; then
            log "❌ L'hôte distant est obligatoire" "$RED"
            return 1
        fi
        
        read -p "Port distant (ex: 3306) : " remote_port
        if [ -z "$remote_port" ]; then
            log "❌ Le port distant est obligatoire" "$RED"
            return 1
        fi
        
        # Créer le fichier de configuration du tunnel
        local config_file="${vpn_id}.conf"
        local config_path="$CONFIG_DIR/$config_file"
        
        cat > "$config_path" << EOF
# Configuration Tunnel SSH: $vpn_name
ssh_key = $ssh_key
ssh_user = $ssh_user
ssh_host = $ssh_host
local_port = $local_port
remote_host = $remote_host
remote_port = $remote_port
EOF
        
        # Protéger le fichier (peut contenir des infos sensibles)
        chmod 600 "$config_path"
        
        # Créer l'entrée dans vpns.conf
        echo "" >> "$VPN_CONF"
        echo "[$vpn_id]" >> "$VPN_CONF"
        echo "name = $vpn_name" >> "$VPN_CONF"
        echo "auth = ssh_tunnel" >> "$VPN_CONF"
        echo "config = $config_file" >> "$VPN_CONF"
        if [ -n "$depends_on" ]; then
            echo "depends_on = $depends_on" >> "$VPN_CONF"
        fi
        
        echo ""
        log "✅ Tunnel SSH '$vpn_name' créé avec succès !" "$GREEN"
        echo ""
        echo "Configuration créée :"
        echo "  • $VPN_CONF (entrée ajoutée)"
        echo "  • $config_path (chmod 600)"
        echo ""
        echo -e "${BLUE}Résumé du tunnel:${NC}"
        echo "  ssh -i $ssh_key -L $local_port:$remote_host:$remote_port -N $ssh_user@$ssh_host"
        if [ -n "$depends_on" ]; then
            local dep_display=$(vpn_get "$depends_on" "name" "$depends_on")
            echo -e "  ${YELLOW}Dépendance: $dep_display${NC}"
        fi
        
    elif [ "$auth_type" = "saml" ]; then
        # === Mode SAML ===
        echo ""
        echo -e "${YELLOW}Configuration SAML${NC}"
        echo ""
        read -p "Hôte:port (ex: vpn.example.com:444) : " saml_host
        
        if [ -z "$saml_host" ]; then
            log "❌ L'hôte SAML est obligatoire" "$RED"
            return 1
        fi
        
        # Créer l'entrée dans vpns.conf
        echo "" >> "$VPN_CONF"
        echo "[$vpn_id]" >> "$VPN_CONF"
        echo "name = $vpn_name" >> "$VPN_CONF"
        echo "auth = saml" >> "$VPN_CONF"
        echo "saml_host = $saml_host" >> "$VPN_CONF"
        if [ -n "$depends_on" ]; then
            echo "depends_on = $depends_on" >> "$VPN_CONF"
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
        if [ -n "$depends_on" ]; then
            echo "depends_on = $depends_on" >> "$VPN_CONF"
        fi
        
        echo ""
        log "✅ VPN '$vpn_name' créé avec succès !" "$GREEN"
        echo ""
        echo "Configuration créée :"
        echo "  • $VPN_CONF (entrée ajoutée)"
        echo "  • $config_path (chmod 600)"
    fi
    
    # Recharger la configuration pour mettre à jour VPN_IDS
    load_config
    
    # Trouver l'index du VPN qu'on vient de créer
    local vpn_index=$(vpn_index_of "$vpn_id")
    
    echo ""
    echo -e "${BLUE}Vous pouvez maintenant vous connecter avec :${NC}"
    if [ -n "$vpn_index" ]; then
        echo "  vpn connect $vpn_index"
    else
        echo "  vpn connect"
    fi
    echo ""
    
    return 0
}
