#!/bin/bash
# lib/connect.sh - Logique de connexion VPN

connect() {
    local count=$(vpn_count)

    # Vérifier s'il y a des VPN configurés
    if [ "$count" -eq 0 ]; then
        echo ""
        log "⚠️  Aucun VPN configuré" "$YELLOW"
        echo ""
        echo -e "${BLUE}Pour créer votre premier VPN, utilisez :${NC}"
        echo "  vpn configure"
        echo ""
        return 1
    fi

    # Choisir le VPN
    if [ -z "$1" ]; then
        echo ""
        list_vpns
        echo ""
        read -p "Choisissez un VPN (1-$count): " vpn_choice
    else
        vpn_choice="$1"
    fi

    # Valider le choix
    if ! [[ "$vpn_choice" =~ ^[0-9]+$ ]] || [ "$vpn_choice" -lt 1 ] || [ "$vpn_choice" -gt "$count" ]; then
        log "❌ Choix invalide (1-$count)" "$RED"
        return 1
    fi

    local vpn_id=$(vpn_id_at "$vpn_choice")
    local display_name=$(vpn_get "$vpn_id" "name" "$vpn_id")
    local auth=$(vpn_get "$vpn_id" "auth" "password")
    local config_file=$(vpn_get "$vpn_id" "config")
    local timeout=$(vpn_get "$vpn_id" "timeout" "${DEFAULT_TIMEOUTS[$auth]:-20}")

    # Vérifier si déjà connecté
    if is_vpn_connected "$vpn_id"; then
        log "⚠️  $display_name est déjà connecté" "$YELLOW"
        read -p "Reconnecter ? (o/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Oo]$ ]]; then
            disconnect_one "$vpn_id"
            sleep 2
        else
            return 1
        fi
    fi

    # Mémoriser les interfaces ppp existantes avant connexion
    local ppp_before=$(ip -o link show type ppp 2>/dev/null | awk -F': ' '{print $2}' | sort)
    local vpn_log="$LOG_DIR/${vpn_id}.log"

    # === Branche SAML ===
    if [ "$auth" = "saml" ]; then
        local saml_host=$(vpn_get "$vpn_id" "saml_host")
        local saml_cert=$(vpn_get "$vpn_id" "saml_cert")

        if [ -z "$saml_host" ]; then
            log "❌ saml_host manquant dans la config pour $vpn_id" "$RED"
            return 1
        fi

        if ! command -v openfortivpn &> /dev/null; then
            log "❌ openfortivpn n'est pas installé" "$RED"
            return 1
        fi

        log "🔐 Ce VPN utilise l'authentification SSO (SAML)" "$YELLOW"
        echo ""

        # Lancer openfortivpn en background
        if [ -n "$saml_cert" ]; then
            sudo -b openfortivpn "$saml_host" --saml-login --trusted-cert "$saml_cert" > "$vpn_log" 2>&1
        else
            sudo -b openfortivpn "$saml_host" --saml-login > "$vpn_log" 2>&1
        fi
        sleep 2
        # Récupérer uniquement le PID du vrai processus openfortivpn (pas sudo)
        # Extraire le hostname sans le port pour la recherche
        local saml_host_base=$(echo "$saml_host" | cut -d':' -f1)
        local vpn_pid=$(pgrep -x openfortivpn | while read pid; do
            ps -p "$pid" -o args= | grep -q "$saml_host_base" && echo "$pid" && break
        done)

        # Attendre l'URL SAML (max 10s)
        echo -n "Démarrage"
        local url_found=false
        for i in {1..10}; do
            if [ -f "$vpn_log" ]; then
                local auth_url=$(grep -oP "Authenticate at '\K[^']+" "$vpn_log" 2>/dev/null)
                if [ -n "$auth_url" ]; then
                    url_found=true
                    echo ""
                    echo ""
                    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
                    echo -e "${YELLOW}🌐 Authentification SSO requise${NC}"
                    echo ""
                    echo -e "  ${GREEN}$auth_url${NC}"
                    echo ""
                    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
                    echo ""
                    
                    # Essayer d'ouvrir automatiquement le navigateur
                    if open_browser "$auth_url"; then
                        echo -e "${GREEN}✅ Navigateur ouvert automatiquement${NC}"
                    else
                        echo -e "${YELLOW}⚠️  Impossible d'ouvrir le navigateur automatiquement${NC}"
                        echo -e "${YELLOW}   Veuillez ouvrir l'URL ci-dessus manuellement${NC}"
                    fi
                    echo ""
                    
                    break
                fi
            fi
            echo -n "."
            sleep 1
        done

        if [ "$url_found" = false ]; then
            echo ""
            log "❌ Impossible de récupérer l'URL SAML" "$RED"
            log "📝 Vérifiez les logs: tail -f $vpn_log" "$YELLOW"
            [ -n "$vpn_pid" ] && sudo kill -INT "$vpn_pid" 2>/dev/null
            return 1
        fi

        echo -e "${YELLOW}En attente de l'authentification dans le navigateur...${NC}"
        _wait_for_connection "$vpn_id" "$vpn_pid" "$ppp_before" "$vpn_log" "$timeout"
        return $?
    fi

    # === Branches password / 2fa (nécessitent un fichier de config) ===
    if [ -z "$config_file" ]; then
        log "❌ config manquant dans la config pour $vpn_id" "$RED"
        return 1
    fi

    local config_path="$CONFIG_DIR/$config_file"
    if [ ! -f "$config_path" ]; then
        log "❌ Configuration introuvable: $config_path" "$RED"
        return 1
    fi

    log "🚀 Connexion à $display_name..." "$BLUE"

    if [ "$auth" = "2fa" ]; then
        # === Mode 2FA : prompt OTP puis background ===
        log "🔐 Ce VPN nécessite un code FortiToken" "$YELLOW"
        echo ""
        read -p "$(echo -e "${BLUE}Code FortiToken : ${NC}")" otp_code

        if [ -z "$otp_code" ]; then
            log "❌ Aucun code FortiToken saisi" "$RED"
            return 1
        fi

        sudo -b openfortivpn -c "$config_path" --otp="$otp_code" > "$vpn_log" 2>&1
        sleep 2
        # Récupérer uniquement le PID du vrai processus openfortivpn (pas sudo)
        local vpn_pid=$(pgrep -x openfortivpn | while read pid; do
            ps -p "$pid" -o args= | grep -q "$(basename "$config_path")" && echo "$pid" && break
        done)
    else
        # === Mode password : background direct ===
        sudo -b openfortivpn -c "$config_path" > "$vpn_log" 2>&1
        sleep 2
        # Récupérer uniquement le PID du vrai processus openfortivpn (pas sudo)
        local vpn_pid=$(pgrep -x openfortivpn | while read pid; do
            ps -p "$pid" -o args= | grep -q "$(basename "$config_path")" && echo "$pid" && break
        done)
    fi

    echo -n "Connexion en cours"
    _wait_for_connection "$vpn_id" "$vpn_pid" "$ppp_before" "$vpn_log" "$timeout"
    return $?
}

_wait_for_connection() {
    local vpn_id="$1"
    local vpn_pid="$2"
    local ppp_before="$3"
    local vpn_log="$4"
    local timeout="${5:-20}"
    local display_name=$(vpn_get "$vpn_id" "name" "$vpn_id")

    for i in $(seq 1 "$timeout"); do
        local ppp_after=$(ip -o link show type ppp 2>/dev/null | awk -F': ' '{print $2}' | sort)
        local new_ppp=$(comm -13 <(echo "$ppp_before") <(echo "$ppp_after") | head -1)

        if [ -n "$new_ppp" ]; then
            local ip=$(ip a show "$new_ppp" | grep "inet " | awk '{print $2}' | cut -d'/' -f1)

            echo "$vpn_pid" > "$SESSION_DIR/.session_${vpn_id}"

            echo ""
            log "✅ Connecté à $display_name (IP: $ip, interface: $new_ppp)" "$GREEN"
            echo ""
            echo -e "${BLUE}Routes VPN actives:${NC}"
            ip route show | grep "$new_ppp" | head -5
            echo ""
            log "📝 Logs: tail -f $vpn_log" "$BLUE"
            return 0
        fi

        # Vérifier si le processus a crashé
        if [ -n "$vpn_pid" ] && ! [ -d "/proc/$vpn_pid" ]; then
            echo ""
            log "❌ Le processus openfortivpn s'est arrêté" "$RED"
            log "📝 Vérifiez les logs: cat $vpn_log" "$YELLOW"
            return 1
        fi

        echo -n "."
        sleep 1
    done

    echo ""
    log "❌ Timeout: connexion non établie après ${timeout}s" "$RED"
    log "📝 Vérifiez les logs: tail -f $vpn_log" "$YELLOW"
    [ -n "$vpn_pid" ] && sudo kill -INT "$vpn_pid" 2>/dev/null
    return 1
}
