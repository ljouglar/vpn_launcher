#!/bin/bash
# lib/status.sh - Fonctions de statut et détection VPN

check_untracked_vpns() {
    # Récupérer les PIDs trackés
    local tracked_pids=()
    for session_file in "$SESSION_DIR"/.session_*; do
        [ -f "$session_file" ] || continue
        local pid=$(cat "$session_file" 2>/dev/null)
        [ -n "$pid" ] && tracked_pids+=("$pid")
    done

    # Chercher les processus openfortivpn non trackés
    local untracked=0
    while IFS= read -r line; do
        local pid=$(echo "$line" | awk '{print $2}')
        
        # Vérifier si ce PID est tracké
        local is_tracked=false
        for tracked in "${tracked_pids[@]}"; do
            if [ "$tracked" = "$pid" ]; then
                is_tracked=true
                break
            fi
        done
        
        if [ "$is_tracked" = false ]; then
            # Récupérer des infos sur ce processus
            local cmd=$(ps -p "$pid" -o args= 2>/dev/null)
            local ppp_if=$(ip -o link show type ppp 2>/dev/null | awk -F': ' '{print $2}' | tail -n 1)
            local ip=""
            if [ -n "$ppp_if" ] && ip a show "$ppp_if" &>/dev/null; then
                ip=$(ip a show "$ppp_if" | grep "inet " | awk '{print $2}' | cut -d'/' -f1)
            fi
            
            if [ -n "$ip" ]; then
                log "⚠️  VPN non tracké (PID: $pid, IP: $ip)" "$YELLOW"
            else
                log "⚠️  VPN non tracké (PID: $pid)" "$YELLOW"
            fi
            echo "   Commande: $cmd" | head -c 80
            echo ""
            untracked=$((untracked + 1))
        fi
    done < <(ps aux | grep -E "[o]penfortivpn" | awk '$11 == "openfortivpn" {print}')
    
    return $untracked
}

check_status() {
    local connected=0
    local has_sessions=false

    for session_file in "$SESSION_DIR"/.session_*; do
        [ -f "$session_file" ] || continue
        has_sessions=true
        break
    done

    if [ "$has_sessions" = true ]; then
        get_connected_vpns
        connected=$?
    fi

    # Vérifier les VPNs non trackés
    check_untracked_vpns
    local untracked=$?

    if [ $connected -eq 0 ] && [ $untracked -eq 0 ]; then
        log "❌ Aucune connexion VPN active" "$RED"
        return 1
    fi

    if [ $untracked -gt 0 ]; then
        echo ""
        echo -e "${YELLOW}💡 Astuce: Utilisez 'vpn disconnect <pid>' pour déconnecter un VPN non tracké${NC}"
    fi

    return 0
}

list_vpns() {
    local count=$(vpn_count)
    
    if [ "$count" -eq 0 ]; then
        echo -e "${YELLOW}Aucun VPN configuré${NC}"
        echo ""
        echo -e "${BLUE}💡 Utilisez 'vpn configure' pour créer votre premier VPN${NC}"
        return 0
    fi
    
    echo -e "${BLUE}VPNs disponibles:${NC}"
    for i in $(seq 1 "$count"); do
        local vpn_id=$(vpn_id_at "$i")
        local display_name=$(vpn_get "$vpn_id" "name" "$vpn_id")
        local auth=$(vpn_get "$vpn_id" "auth" "password")
        local depends_on=$(vpn_get "$vpn_id" "depends_on")

        # Icône selon le type
        local type_icon="🔒"
        [ "$auth" = "ssh_tunnel" ] && type_icon="🔗"

        # Info dépendance
        local dep_info=""
        if [ -n "$depends_on" ]; then
            local dep_name=$(vpn_get "$depends_on" "name" "$depends_on")
            dep_info=" ${YELLOW}(← $dep_name)${NC}"
        fi

        if is_vpn_connected "$vpn_id"; then
            echo -e "  $i) ${GREEN}● $type_icon $display_name${NC}$dep_info"
        else
            echo -e "  $i) $type_icon $display_name$dep_info"
        fi
    done
}
