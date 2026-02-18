#!/bin/bash
# lib/session.sh - Gestion des sessions VPN

is_vpn_connected() {
    local vpn_id="$1"
    local session_file="$SESSION_DIR/.session_${vpn_id}"

    if [ ! -f "$session_file" ]; then
        return 1
    fi

    local pid=$(cat "$session_file" 2>/dev/null)
    if [ -n "$pid" ] && [ -d "/proc/$pid" ]; then
        return 0
    fi

    rm -f "$session_file"
    return 1
}

get_connected_vpns() {
    local connected=0
    for session_file in "$SESSION_DIR"/.session_*; do
        [ -f "$session_file" ] || continue
        local vpn_id=$(basename "$session_file" | sed 's/^.session_//')
        local pid=$(cat "$session_file" 2>/dev/null)

        if [ -n "$pid" ] && [ -d "/proc/$pid" ]; then
            local display_name=$(vpn_get "$vpn_id" "name" "$vpn_id")

            # Chercher une interface ppp active
            local ppp_if=$(ip -o link show type ppp 2>/dev/null | awk -F': ' '{print $2}' | sed -n "$((connected+1))p")
            local ip=""
            if [ -n "$ppp_if" ] && ip a show "$ppp_if" &>/dev/null; then
                ip=$(ip a show "$ppp_if" | grep "inet " | awk '{print $2}' | cut -d'/' -f1)
            fi

            if [ -n "$ip" ]; then
                log "✅ $display_name (PID: $pid, IP: $ip)" "$GREEN"
            else
                log "✅ $display_name (PID: $pid)" "$GREEN"
            fi
            connected=$((connected + 1))
        else
            rm -f "$session_file"
        fi
    done

    return $connected
}
