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

    # Vérifier les dépendances
    local depends_on=$(vpn_get "$vpn_id" "depends_on")
    if [ -n "$depends_on" ]; then
        if ! is_vpn_connected "$depends_on"; then
            local dep_name=$(vpn_get "$depends_on" "name" "$depends_on")
            log "⚠️  $display_name dépend de $dep_name qui n'est pas connecté" "$YELLOW"
            read -p "Connecter $dep_name d'abord ? (O/n) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                local dep_index=$(vpn_index_of "$depends_on")
                if [ -n "$dep_index" ]; then
                    connect "$dep_index"
                    if ! is_vpn_connected "$depends_on"; then
                        log "❌ Impossible de connecter la dépendance $dep_name" "$RED"
                        return 1
                    fi
                else
                    log "❌ Dépendance '$depends_on' non trouvée dans la configuration" "$RED"
                    return 1
                fi
            else
                log "❌ Connexion annulée (dépendance non satisfaite)" "$RED"
                return 1
            fi
        else
            local dep_name=$(vpn_get "$depends_on" "name" "$depends_on")
            log "✅ Dépendance satisfaite: $dep_name est connecté" "$GREEN"
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

    # === Branche SSH Tunnel ===
    if [ "$auth" = "ssh_tunnel" ]; then
        local ssh_key=$(vpn_get "$vpn_id" "ssh_key")
        local ssh_user=$(vpn_get "$vpn_id" "ssh_user")
        local ssh_host=$(vpn_get "$vpn_id" "ssh_host")
        local local_port=$(vpn_get "$vpn_id" "local_port")
        local remote_host=$(vpn_get "$vpn_id" "remote_host")
        local remote_port=$(vpn_get "$vpn_id" "remote_port")

        # Valider les champs requis
        local missing_fields=""
        [ -z "$ssh_key" ] && missing_fields="${missing_fields} ssh_key"
        [ -z "$ssh_user" ] && missing_fields="${missing_fields} ssh_user"
        [ -z "$ssh_host" ] && missing_fields="${missing_fields} ssh_host"
        [ -z "$local_port" ] && missing_fields="${missing_fields} local_port"
        [ -z "$remote_host" ] && missing_fields="${missing_fields} remote_host"
        [ -z "$remote_port" ] && missing_fields="${missing_fields} remote_port"

        if [ -n "$missing_fields" ]; then
            log "❌ Champs manquants pour le tunnel SSH $vpn_id:$missing_fields" "$RED"
            return 1
        fi

        # Vérifier que la clé SSH existe
        if [ ! -f "$ssh_key" ]; then
            log "❌ Clé SSH introuvable: $ssh_key" "$RED"
            return 1
        fi

        # Vérifier que le port local n'est pas déjà utilisé
        if ss -tlnp 2>/dev/null | grep -q ":${local_port} "; then
            log "⚠️  Le port local $local_port est déjà utilisé" "$YELLOW"
            return 1
        fi

        log "🔗 Tunnel SSH: localhost:$local_port → $remote_host:$remote_port via $ssh_user@$ssh_host" "$BLUE"

        # Lancer le tunnel SSH (-f: passe en background après authentification)
        ssh -i "$ssh_key" \
            -L "${local_port}:${remote_host}:${remote_port}" \
            -N -f \
            -o ExitOnForwardFailure=yes \
            -o ServerAliveInterval=30 \
            -o ServerAliveCountMax=3 \
            -o ConnectTimeout="$timeout" \
            "$ssh_user@$ssh_host" >> "$vpn_log" 2>&1

        local ssh_exit=$?
        if [ $ssh_exit -ne 0 ]; then
            log "❌ Échec du tunnel SSH (code: $ssh_exit)" "$RED"
            log "📝 Vérifiez les logs: cat $vpn_log" "$YELLOW"
            return 1
        fi

        # Trouver le PID du processus SSH
        sleep 1
        local tunnel_pid=$(pgrep -f "ssh.*-L ${local_port}:${remote_host}:${remote_port}.*${ssh_user}@${ssh_host}" | head -1)

        if [ -z "$tunnel_pid" ]; then
            log "❌ Impossible de trouver le processus du tunnel SSH" "$RED"
            return 1
        fi

        # Sauvegarder la session
        echo "$tunnel_pid" > "$SESSION_DIR/.session_${vpn_id}"

        echo ""
        log "✅ Tunnel SSH ouvert: localhost:$local_port → $remote_host:$remote_port" "$GREEN"
        echo ""
        echo -e "${BLUE}Détails du tunnel:${NC}"
        echo "  Port local  : $local_port"
        echo "  Destination : $remote_host:$remote_port"
        echo "  Proxy SSH   : $ssh_user@$ssh_host"
        echo "  PID         : $tunnel_pid"
        echo ""
        log "📝 Logs: tail -f $vpn_log" "$BLUE"
        return 0
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
