#!/bin/bash
# lib/config.sh - Parseur INI et gestion de la configuration VPN

# Liste ordonnée des IDs de VPN (ordre du fichier)
VPN_IDS=()

# Tableaux associatifs : VPN_PROP[id.clé] = valeur
declare -A VPN_PROP

# Charger la configuration INI
load_config() {
    # Créer le fichier de configuration s'il n'existe pas
    if [ ! -f "$VPN_CONF" ]; then
        mkdir -p "$(dirname "$VPN_CONF")"
        cat > "$VPN_CONF" << 'EOF'
# Configuration VPN Manager
# Format: [id_vpn]
# name = Nom affiché
# auth = password|2fa|saml
# config = fichier.conf (pour password/2fa)
# saml_host = host:port (pour saml)
# saml_cert = certificat (optionnel pour saml)

# Exemple:
# [mon-vpn]
# name = Mon VPN Corporate
# auth = password
# config = mon-vpn.conf

EOF
        echo -e "${YELLOW}📝 Fichier de configuration créé: $VPN_CONF${NC}" >&2
        echo -e "${BLUE}💡 Utilisez 'vpn configure' pour ajouter votre premier VPN${NC}" >&2
    fi

    # Réinitialiser les tableaux
    VPN_IDS=()
    declare -g -A VPN_PROP

    local current_section=""
    while IFS= read -r line || [ -n "$line" ]; do
        # Ignorer lignes vides et commentaires
        [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue

        # Détecter une section [nom]
        if [[ "$line" =~ ^\[([a-zA-Z0-9_-]+)\]$ ]]; then
            current_section="${BASH_REMATCH[1]}"
            VPN_IDS+=("$current_section")
            continue
        fi

        # Lire clé = valeur
        if [[ -n "$current_section" && "$line" =~ ^[[:space:]]*([a-zA-Z0-9_]+)[[:space:]]*=[[:space:]]*(.+)$ ]]; then
            local key="${BASH_REMATCH[1]}"
            local value="${BASH_REMATCH[2]}"
            # Supprimer les espaces en fin de valeur
            value="${value%"${value##*[![:space:]]}"}"
            VPN_PROP["${current_section}.${key}"]="$value"
        fi
    done < "$VPN_CONF"

    # Permettre un fichier vide (pour le configurateur)
    # Pas d'exit si aucun VPN n'est défini
}

# Accéder à une propriété d'un VPN (avec valeur par défaut optionnelle)
vpn_get() {
    local id="$1" key="$2" default="${3:-}"
    local value="${VPN_PROP["${id}.${key}"]}"
    echo "${value:-$default}"
}

# Nombre de VPNs configurés
vpn_count() {
    echo "${#VPN_IDS[@]}"
}

# ID du VPN à l'index donné (1-based)
vpn_id_at() {
    local index=$(( $1 - 1 ))
    echo "${VPN_IDS[$index]}"
}

# Index (1-based) d'un VPN par son id, retourne "" si non trouvé
vpn_index_of() {
    local target="$1"
    for i in "${!VPN_IDS[@]}"; do
        if [ "${VPN_IDS[$i]}" = "$target" ]; then
            echo $(( i + 1 ))
            return
        fi
    done
}
