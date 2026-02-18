#!/bin/bash
# lib/disconnect.sh - Logique de déconnexion VPN

disconnect_one() {
    local vpn_id="$1"
    
    # Si c'est un PID (nombre uniquement), déconnexion directe
    if [[ "$vpn_id" =~ ^[0-9]+$ ]]; then
        local pid="$vpn_id"
        if [ ! -d "/proc/$pid" ]; then
            log "❌ Aucun processus avec le PID $pid" "$RED"
            return 1
        fi
        
        # Vérifier que c'est bien un processus openfortivpn
        if ! ps -p "$pid" -o comm= 2>/dev/null | grep -q "openfortivpn"; then
            log "❌ Le PID $pid n'est pas un processus openfortivpn" "$RED"
            return 1
        fi
        
        log "🔌 Déconnexion du processus (PID: $pid)..." "$YELLOW"
        
        # Tuer les processus enfants d'abord
        local children=$(pgrep -P "$pid" 2>/dev/null)
        if [ -n "$children" ]; then
            echo "$children" | xargs -r sudo kill -TERM 2>/dev/null
        fi
        
        # Envoyer SIGTERM au processus principal
        sudo kill -TERM "$pid" 2>/dev/null
        sleep 3
        
        if [ -d "/proc/$pid" ]; then
            log "Processus encore actif, envoi de SIGKILL..." "$YELLOW"
            # Tuer les enfants avec SIGKILL
            if [ -n "$children" ]; then
                echo "$children" | xargs -r sudo kill -9 2>/dev/null
            fi
            # Tuer le parent avec SIGKILL
            sudo kill -9 "$pid" 2>/dev/null
            sleep 2
            
            # Vérifier que le processus est VRAIMENT mort
            if [ -d "/proc/$pid" ]; then
                log "❌ ERREUR: Impossible de tuer le processus $pid" "$RED"
                log "💡 Le processus pourrait avoir des permissions spéciales" "$YELLOW"
                return 1
            fi
        fi
        
        # Nettoyer toute session orpheline qui pourrait pointer vers ce PID
        for session_file in "$SESSION_DIR"/.session_*; do
            [ -f "$session_file" ] || continue
            local session_pid=$(cat "$session_file" 2>/dev/null)
            if [ "$session_pid" = "$pid" ]; then
                rm -f "$session_file"
            fi
        done
        
        # Attendre un peu et vérifier si les interfaces ppp ont été nettoyées
        sleep 1
        local remaining_ppp=$(ip -o link show type ppp 2>/dev/null | wc -l)
        if [ "$remaining_ppp" -gt 0 ]; then
            local active_vpns=$(ps aux | grep -E "[o]penfortivpn" | wc -l)
            if [ "$active_vpns" -eq 0 ]; then
                log "⚠️  Attention: $remaining_ppp interface(s) ppp restante(s) sans processus VPN" "$YELLOW"
                log "💡 Vous pouvez les nettoyer avec: sudo ip link delete <interface>" "$BLUE"
            fi
        fi
        
        log "✅ Processus déconnecté" "$GREEN"
        return 0
    fi
    
    # Sinon, c'est un ID de VPN normal
    local session_file="$SESSION_DIR/.session_${vpn_id}"

    if [ ! -f "$session_file" ]; then
        log "❌ $vpn_id n'est pas connecté" "$RED"
        return 1
    fi

    local pid=$(cat "$session_file" 2>/dev/null)
    if [ -n "$pid" ] && [ -d "/proc/$pid" ]; then
        log "🔌 Déconnexion de $vpn_id (PID: $pid)..." "$YELLOW"
        
        # Tuer les processus enfants d'abord
        local children=$(pgrep -P "$pid" 2>/dev/null)
        if [ -n "$children" ]; then
            echo "$children" | xargs -r sudo kill -TERM 2>/dev/null
        fi
        
        # Envoyer SIGTERM au processus principal
        sudo kill -TERM "$pid" 2>/dev/null
        sleep 3
        
        if [ -d "/proc/$pid" ]; then
            log "Processus encore actif, envoi de SIGKILL..." "$YELLOW"
            # Tuer les enfants avec SIGKILL
            if [ -n "$children" ]; then
                echo "$children" | xargs -r sudo kill -9 2>/dev/null
            fi
            # Tuer le parent avec SIGKILL
            sudo kill -9 "$pid" 2>/dev/null
            sleep 2
            
            # Vérifier que le processus est VRAIMENT mort
            if [ -d "/proc/$pid" ]; then
                log "❌ ERREUR: Impossible de tuer le processus $pid" "$RED"
                log "⚠️  Le fichier de session est conservé" "$YELLOW"
                log "💡 Utilisez 'sudo kill -9 $pid' manuellement" "$BLUE"
                return 1
            fi
        fi
    fi

    # Ne supprimer la session que si le processus est vraiment mort
    rm -f "$session_file"
    
    # Attendre un peu et vérifier si les interfaces ppp ont été nettoyées
    sleep 1
    local remaining_ppp=$(ip -o link show type ppp 2>/dev/null | wc -l)
    if [ "$remaining_ppp" -gt 0 ]; then
        local active_vpns=$(ps aux | grep -E "[o]penfortivpn" | wc -l)
        if [ "$active_vpns" -eq 0 ]; then
            log "⚠️  Attention: $remaining_ppp interface(s) ppp restante(s) sans processus VPN" "$YELLOW"
            log "💡 Vous pouvez les nettoyer avec: sudo ip link delete <interface>" "$BLUE"
        fi
    fi
    
    log "✅ $vpn_id déconnecté" "$GREEN"
}

cleanup_orphans() {
    local cleaned=0
    
    echo ""
    log "🧹 Nettoyage des processus et interfaces orphelins..." "$BLUE"
    
    # 1. Nettoyer les processus openfortivpn orphelins (non trackés)
    local tracked_pids=()
    for session_file in "$SESSION_DIR"/.session_*; do
        [ -f "$session_file" ] || continue
        local pid=$(cat "$session_file" 2>/dev/null)
        [ -n "$pid" ] && tracked_pids+=("$pid")
    done
    
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
            log "  Arrêt du processus orphelin (PID: $pid)..." "$YELLOW"
            sudo kill -9 "$pid" 2>/dev/null
            sleep 0.5
            if ! [ -d "/proc/$pid" ]; then
                cleaned=$((cleaned + 1))
            fi
        fi
    done < <(ps aux | grep -E "[o]penfortivpn" 2>/dev/null || true)
    
    # 2. Nettoyer les interfaces ppp orphelines
    sleep 1
    local active_vpns=$(ps aux | grep -E "[o]penfortivpn" 2>/dev/null | wc -l)
    if [ "$active_vpns" -eq 0 ]; then
        while IFS= read -r ppp_if; do
            log "  Suppression de l'interface orpheline: $ppp_if" "$YELLOW"
            sudo ip link delete "$ppp_if" 2>/dev/null && cleaned=$((cleaned + 1))
        done < <(ip -o link show type ppp 2>/dev/null | awk -F': ' '{print $2}' || true)
    fi
    
    # 3. Nettoyer les fichiers de session orphelins
    for session_file in "$SESSION_DIR"/.session_*; do
        [ -f "$session_file" ] || continue
        local pid=$(cat "$session_file" 2>/dev/null)
        if [ -n "$pid" ] && ! [ -d "/proc/$pid" ]; then
            log "  Nettoyage de la session orpheline: $(basename "$session_file")" "$YELLOW"
            rm -f "$session_file"
            cleaned=$((cleaned + 1))
        fi
    done
    
    echo ""
    if [ "$cleaned" -gt 0 ]; then
        log "✅ Nettoyage terminé ($cleaned éléments nettoyés)" "$GREEN"
    else
        log "✅ Rien à nettoyer" "$GREEN"
    fi
    
    return "$cleaned"
}

disconnect() {
    local target="$1"

    local connected_vpns=()
    for session_file in "$SESSION_DIR"/.session_*; do
        [ -f "$session_file" ] || continue
        local vpn_id=$(basename "$session_file" | sed 's/^.session_//')
        local pid=$(cat "$session_file" 2>/dev/null)
        if [ -n "$pid" ] && [ -d "/proc/$pid" ]; then
            connected_vpns+=("$vpn_id")
        else
            rm -f "$session_file"
        fi
    done

    # Si un argument est fourni (ID, numéro, ou PID)
    if [ -n "$target" ]; then
        # Vérifier si c'est "all" pour tout déconnecter
        if [[ "$target" = "all" || "$target" = "a" ]]; then
            for vpn_id in "${connected_vpns[@]}"; do
                disconnect_one "$vpn_id"
            done
            
            # Aussi déconnecter tous les VPNs non trackés
            while IFS= read -r line; do
                local pid=$(echo "$line" | awk '{print $2}')
                disconnect_one "$pid"
            done < <(ps aux | grep -E "[o]penfortivpn")
            
            return
        fi
        
        # Si c'est un nombre, vérifier d'abord si c'est un PID valide
        if [[ "$target" =~ ^[0-9]+$ ]]; then
            # Vérifier si c'est un PID de processus openfortivpn
            if [ -d "/proc/$target" ] && ps -p "$target" -o comm= 2>/dev/null | grep -q "openfortivpn"; then
                # C'est un PID valide, déconnecter directement
                disconnect_one "$target"
                return
            fi
            
            # Sinon, c'est peut-être un index de position
            if [ "$target" -ge 1 ] && [ "$target" -le ${#connected_vpns[@]} ]; then
                disconnect_one "${connected_vpns[$((target - 1))]}"
                return
            else
                # Aucune des deux interprétations ne fonctionne
                log "❌ '$target' n'est ni un PID valide ni un index valide (VPNs trackés: ${#connected_vpns[@]})" "$RED"
                return 1
            fi
        fi
        
        # Sinon, c'est un ID de VPN
        # Vérifier que ce VPN est bien connecté
        local found=false
        for vpn_id in "${connected_vpns[@]}"; do
            if [ "$vpn_id" = "$target" ]; then
                found=true
                break
            fi
        done
        
        if [ "$found" = true ]; then
            disconnect_one "$target"
            return
        else
            log "❌ VPN '$target' n'est pas connecté" "$RED"
            return 1
        fi
    fi

    # Mode interactif : vérifier s'il y a des VPNs connectés
    if [ ${#connected_vpns[@]} -eq 0 ]; then
        log "❌ Aucune connexion trackée active" "$RED"
        
        # Vérifier s'il y a des VPNs non trackés
        if ps aux | grep -E "[o]penfortivpn" &>/dev/null; then
            echo ""
            log "⚠️  Des VPNs fantômes ont été détectés (non trackés par le script)" "$YELLOW"
            read -p "Voulez-vous nettoyer ces connexions fantômes ? (o/N) " cleanup_choice
            
            if [[ "$cleanup_choice" =~ ^[oO]$ ]]; then
                echo ""
                log "🧹 Nettoyage des connexions fantômes en cours..." "$BLUE"
                local cleaned_count=$(cleanup_orphans)
                if [ "$cleaned_count" -gt 0 ]; then
                    log "✅ $cleaned_count élément(s) nettoyé(s)" "$GREEN"
                else
                    log "ℹ️  Aucun élément à nettoyer" "$BLUE"
                fi
            else
                log "💡 Vous pouvez aussi utiliser 'vpn status' pour voir les détails et 'vpn disconnect <pid>' pour déconnecter manuellement" "$BLUE"
            fi
        fi
        return 1
    fi

    # Mode interactif : si un seul VPN connecté, le déconnecter directement
    if [ ${#connected_vpns[@]} -eq 1 ]; then
        disconnect_one "${connected_vpns[0]}"
        return
    fi

    # Mode interactif : plusieurs VPNs connectés
    echo -e "${BLUE}VPNs actuellement connectés :${NC}"
    local idx=1
    for vpn_id in "${connected_vpns[@]}"; do
        local display_name=$(vpn_get "$vpn_id" "name" "$vpn_id")
        echo "  $idx) $display_name"
        idx=$((idx + 1))
    done
    echo "  a) Tout déconnecter"
    echo ""
    read -p "Quel VPN déconnecter ? " dc_choice

    if [[ "$dc_choice" = "a" || "$dc_choice" = "A" ]]; then
        for vpn_id in "${connected_vpns[@]}"; do
            disconnect_one "$vpn_id"
        done
    elif [[ "$dc_choice" =~ ^[0-9]+$ ]] && [ "$dc_choice" -ge 1 ] && [ "$dc_choice" -le ${#connected_vpns[@]} ]; then
        disconnect_one "${connected_vpns[$((dc_choice - 1))]}"
    else
        log "❌ Choix invalide" "$RED"
    fi
}
