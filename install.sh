#!/bin/bash
# Script d'installation VPN Manager
# Ce script installe et configure le gestionnaire VPN multi-connexions

set -e

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}══════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}   Installation du Gestionnaire VPN Multi-Connexions ${NC}"
echo -e "${BLUE}══════════════════════════════════════════════════════${NC}"
echo ""

# Vérifier les prérequis
echo -e "${YELLOW}Vérification des prérequis...${NC}"

if ! command -v openfortivpn &> /dev/null; then
    echo -e "${RED}❌ openfortivpn n'est pas installé${NC}"
    echo ""
    echo "Pour installer openfortivpn :"
    echo "  • Ubuntu/Debian: sudo apt install openfortivpn"
    echo "  • Fedora/RHEL:   sudo dnf install openfortivpn"
    echo "  • Arch:          sudo pacman -S openfortivpn"
    exit 1
fi

echo -e "${GREEN}✅ openfortivpn est installé${NC}"

# Créer la structure de dossiers
VPN_DIR="$HOME/.vpn"
CONFIG_DIR="$VPN_DIR/configs"
LOG_DIR="$VPN_DIR/logs"
SESSION_DIR="$VPN_DIR/sessions"

echo ""
echo -e "${YELLOW}Création de la structure de dossiers...${NC}"

mkdir -p "$CONFIG_DIR" "$LOG_DIR" "$SESSION_DIR"

# Créer un lien symbolique vers le script principal
SCRIPT_SOURCE="$(cd "$(dirname "$0")" && pwd)/vpn"
SCRIPT_DEST="$HOME/vpn"

if [ ! -f "$SCRIPT_SOURCE" ]; then
    echo -e "${RED}❌ Le fichier 'vpn' n'a pas été trouvé dans le dossier d'installation${NC}"
    exit 1
fi

echo -e "${YELLOW}Installation du script vpn...${NC}"

# Supprimer le lien/fichier existant si présent
if [ -L "$SCRIPT_DEST" ] || [ -f "$SCRIPT_DEST" ]; then
    rm -f "$SCRIPT_DEST"
fi

# Créer le lien symbolique
ln -s "$SCRIPT_SOURCE" "$SCRIPT_DEST"
chmod +x "$SCRIPT_SOURCE"
echo -e "${GREEN}✅ Lien symbolique créé : ~/vpn -> $SCRIPT_SOURCE${NC}"

# Créer le fichier vpns.conf si inexistant
VPNS_CONF="$VPN_DIR/vpns.conf"
if [ ! -f "$VPNS_CONF" ]; then
    echo -e "${YELLOW}Création du fichier de configuration...${NC}"
    cat > "$VPNS_CONF" << 'EOF'
# Configuration des VPN
# Format INI : chaque section [id] définit un VPN
#
# Propriétés :
#   name           = Nom affiché (obligatoire)
#   auth           = Mode d'authentification : password | 2fa | saml (obligatoire)
#   config         = Fichier de config openfortivpn dans ~/.vpn/configs/ (pour password et 2fa)
#   saml_host      = Hôte:port pour authentification SAML (pour saml)
#   saml_cert      = Certificat de confiance pour SAML (pour saml)
#   timeout        = Timeout de connexion en secondes (défaut : 20 pour password, 30 pour 2fa, 60 pour saml)

# Exemple : VPN avec authentification par mot de passe
# [mon-vpn]
# name = Mon VPN Corporate
# auth = password
# config = mon-vpn.conf

# Exemple : VPN avec authentification 2FA (FortiToken)
# [vpn-prod]
# name = Production VPN
# auth = 2fa
# config = vpn-prod.conf

# Exemple : VPN avec authentification SAML (SSO)
# [vpn-sso]
# name = SSO VPN
# auth = saml
# saml_host = vpn.example.com:444
# saml_cert = 166fe8f33b64afc49c64f6c632b409d6f4c204ff1e90ce81d1e7da7b98e3fbf1

EOF
    echo -e "${GREEN}✅ Fichier de configuration créé${NC}"
else
    echo -e "${BLUE}ℹ️  Le fichier vpns.conf existe déjà, il n'a pas été modifié${NC}"
fi

# Créer un exemple de configuration openfortivpn
EXAMPLE_CONF="$CONFIG_DIR/example.conf"
if [ ! -f "$EXAMPLE_CONF" ]; then
    echo -e "${YELLOW}Création d'un exemple de configuration openfortivpn...${NC}"
    cat > "$EXAMPLE_CONF" << 'EOF'
# Exemple de configuration openfortivpn
# Copiez ce fichier et adaptez-le pour chaque VPN
#
# Pour obtenir le certificat d'un serveur VPN :
# echo | openssl s_client -connect SERVEUR:PORT 2>/dev/null | openssl x509 -fingerprint -noout -sha256
#
# IMPORTANT : Ce fichier contient des informations sensibles (mot de passe)
# Il sera automatiquement protégé avec chmod 600

host = vpn.example.com
port = 443
username = votre.nom@example.com
password = votre_mot_de_passe_secret
trusted-cert = votre_certificat_sha256_ici
set-routes = 1
set-dns = 0
pppd-use-peerdns = 0

EOF
    chmod 600 "$EXAMPLE_CONF"
    echo -e "${GREEN}✅ Exemple de configuration créé (chmod 600)${NC}"
fi

# Protéger tous les fichiers .conf existants
echo -e "${YELLOW}Protection des fichiers de configuration...${NC}"
find "$CONFIG_DIR" -type f -name "*.conf" -exec chmod 600 {} \;
echo -e "${GREEN}✅ Permissions des fichiers .conf définies à 600${NC}"

# Créer le README
README_FILE="$VPN_DIR/README.md"
if [ ! -f "$README_FILE" ]; then
    echo -e "${YELLOW}Création du README...${NC}"
    cat > "$README_FILE" << 'EOF'
# VPN Manager - Guide de configuration 🚀

## 📋 Prérequis

- `openfortivpn` doit être installé
- Accès sudo pour établir les connexions VPN

## 🔧 Configuration

### 1. Obtenir les informations du serveur VPN

Pour chaque VPN, vous avez besoin de :
- **Hôte et port** (ex: vpn.example.com:443)
- **Nom d'utilisateur**
- **Certificat SSL** (fingerprint SHA256)
- **Mot de passe**
- **Mode d'authentification** (password, 2fa ou saml)

### 2. Récupérer le certificat SSL

```bash
echo | openssl s_client -connect SERVEUR:PORT 2>/dev/null | openssl x509 -fingerprint -noout -sha256
```

Exemple de sortie :
```
SHA256 Fingerprint=4D:49:0E:C4:D0:4B:59:C6:C2:C0:6F:E5:A0:D5:74:89:44:AA:35:BD:DA:A5:C3:6A:86:8D:9B:2F:E7:6F:5F:42
```

Utilisez la valeur sans les `:` → `4d490ec4d04b59c6c2c06fe5a0d5748944aa35bddaa5c36a868d9b2fe76f5f42`

### 3. Créer un fichier de configuration openfortivpn

Dans `~/.vpn/configs/`, créez un fichier pour chaque VPN (ex: `mon-vpn.conf`) :

```properties
host = vpn.example.com
port = 443
username = votre.nom@example.com
password = votre_mot_de_passe_secret
trusted-cert = 4d490ec4d04b59c6c2c06fe5a0d5748944aa35bddaa5c36a868d9b2fe76f5f42
set-routes = 1
set-dns = 0
pppd-use-peerdns = 0
```

**Note** : Le mot de passe est directement dans le fichier .conf. Il sera protégé avec chmod 600.

### 4. Déclarer le VPN dans vpns.conf

Éditez `~/.vpn/vpns.conf` et ajoutez une section :

**Pour un VPN avec mot de passe simple :**
```ini
[mon-vpn]
name = Mon VPN Corporate
auth = password
config = mon-vpn.conf
```

**Pour un VPN avec 2FA (FortiToken) :**
```ini
[vpn-prod]
name = Production VPN
auth = 2fa
config = vpn-prod.conf
```

**Pour un VPN avec SAML/SSO :**
```ini
[vpn-sso]
name = SSO VPN
auth = saml
saml_host = vpn.example.com:444
saml_cert = 166fe8f33b64afc49c64f6c632b409d6f4c204ff1e90ce81d1e7da7b98e3fbf1
```

## 🚀 Utilisation

### Lancer le menu interactif
```bash
~/vpn
```

### Commandes directes
```bash
~/vpn connect 1      # Se connecter au VPN #1
~/vpn status         # Voir le statut
~/vpn disconnect     # Se déconnecter
~/vpn list           # Lister les VPNs
~/vpn help           # Aide
```

### Connexion rapide
```bash
~/vpn c 1    # Connecter au VPN #1
~/vpn d      # Déconnecter
~/vpn s      # Statut
```

## 📝 Logs

```bash
# Logs généraux
tail -f ~/.vpn/logs/vpn.log

# Logs d'une connexion spécifique
tail -f ~/.vpn/logs/mon-vpn.log
```

## 🔐 Sécurité

- Les fichiers `.conf` contiennent des informations sensibles et sont protégés (chmod 600)
- Les mots de passe ne sont jamais affichés dans les logs
- N'ajoutez jamais les fichiers `*.conf` à votre gestionnaire de versions

## 🆘 Dépannage

### Connexion échoue
1. Vérifiez les logs : `tail -f ~/.vpn/logs/mon-vpn.log`
2. Vérifiez le certificat SSL du serveur
3. Testez manuellement : `sudo openfortivpn -c ~/.vpn/configs/mon-vpn.conf`

### Interface réseau non créée
- Vérifiez que `pppd` est installé : `which pppd`
- Vérifiez les droits sudo

## 🌟 Fonctionnalités

✅ Multi-VPN : connectez-vous à plusieurs VPNs simultanément
✅ 1 seule interface par VPN (pas d'interfaces fantômes)
✅ Support password, 2FA et SAML
✅ Nettoyage automatique à la déconnexion
✅ Logs détaillés pour le dépannage
✅ Gestion de mots de passe sécurisée
✅ Menu interactif simple

EOF
    echo -e "${GREEN}✅ README créé${NC}"
fi

# Ajouter au PATH si nécessaire (optionnel)
echo ""
echo -e "${YELLOW}Configuration du PATH (optionnel)...${NC}"

if [[ ":$PATH:" != *":$HOME:"* ]]; then
    echo -e "${BLUE}Le dossier ~/vpn n'est pas dans le PATH${NC}"
    echo -e "${YELLOW}Pour exécuter 'vpn' depuis n'importe où, ajoutez cette ligne à votre ~/.bashrc ou ~/.zshrc :${NC}"
    echo ""
    echo "  export PATH=\"\$HOME:\$PATH\""
    echo ""
    read -p "Voulez-vous l'ajouter automatiquement à ~/.bashrc ? (o/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Oo]$ ]]; then
        if ! grep -q "# VPN Manager PATH" "$HOME/.bashrc"; then
            echo "" >> "$HOME/.bashrc"
            echo "# VPN Manager PATH" >> "$HOME/.bashrc"
            echo "export PATH=\"\$HOME:\$PATH\"" >> "$HOME/.bashrc"
            echo -e "${GREEN}✅ PATH ajouté à ~/.bashrc${NC}"
            echo -e "${YELLOW}Exécutez 'source ~/.bashrc' ou ouvrez un nouveau terminal${NC}"
        else
            echo -e "${BLUE}ℹ️  PATH déjà présent dans ~/.bashrc${NC}"
        fi
    fi
else
    echo -e "${GREEN}✅ Le script vpn est déjà accessible${NC}"
fi

# Résumé final
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
echo ""
echo -e "${YELLOW}🔄 Pour mettre à jour le script :${NC}"
echo "   cd $(dirname "$SCRIPT_SOURCE") && git pull"
echo ""
echo -e "${YELLOW}📋 Prochaines étapes :${NC}"
echo "   1. Configurez vos VPNs dans ~/.vpn/vpns.conf"
echo "   2. Créez les fichiers de config (avec mots de passe) dans ~/.vpn/configs/"
echo "   3. Lancez : ~/vpn"
echo ""
echo -e "${BLUE}📖 Documentation complète : cat ~/.vpn/README.md${NC}"
echo ""
