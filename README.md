# 🚀 VPN Manager

Gestionnaire VPN multi-connexions pour Linux avec support FortiVPN. Interface interactive pour gérer plusieurs connexions VPN simultanément avec différents modes d'authentification.

## ✨ Fonctionnalités

- **Multi-VPN** : Gérez plusieurs connexions VPN simultanées
- **4 modes de connexion** : Password, 2FA (FortiToken), SAML/SSO, Tunnel SSH
- **Tunnels SSH** : Port forwarding via un proxy de rebond (ex: accès BDD distante)
- **Dépendances** : Un tunnel ou VPN peut dépendre d'une autre connexion (auto-connect/cascade disconnect)
- **Interface interactive** : Menu simple et intuitif
- **Logs détaillés** : Pour le dépannage et le monitoring
- **Sécurisé** : Mots de passe protégés (chmod 600)
- **Nettoyage automatique** : Pas d'interfaces fantômes

## � Compatibilité

**Systèmes supportés** : Linux (Ubuntu, Debian, Fedora, Arch, etc.)

**Version openfortivpn requise** :
- ≥ 1.17.0 : Minimum pour les modes Password et 2FA
- ≥ 1.20.0 : **Recommandé** pour le support SAML/SSO
- Version testée : **1.24.1** ✅

⚠️ **Important** : Les versions des dépôts officiels sont souvent anciennes. Pour SAML/SSO, la compilation depuis les sources est recommandée.

## �📋 Prérequis

### Option 1 : Installation via gestionnaire de paquets (Simple)

**Ubuntu/Debian :**
```bash
sudo apt install openfortivpn
```

**Fedora/RHEL :**
```bash
sudo dnf install openfortivpn
```

**Arch Linux :**
```bash
sudo pacman -S openfortivpn
```

⚠️ **Attention** : Les versions des dépôts peuvent être anciennes et ne pas supporter SAML/SSO.

### Option 2 : Compilation depuis les sources (Recommandé)

Pour obtenir la dernière version avec support SAML/SSO (≥ 1.20.0) :

#### 1. Installer les dépendances de compilation

**Ubuntu/Debian :**
```bash
sudo apt update
sudo apt install -y build-essential automake autoconf libssl-dev pkg-config libppp-dev git
```

**Fedora/RHEL :**
```bash
sudo dnf install -y gcc make automake autoconf openssl-devel pkgconfig ppp-devel git
```

**Arch Linux :**
```bash
sudo pacman -S base-devel automake autoconf openssl pkg-config ppp git
```

#### 2. Télécharger les sources

```bash
cd /tmp
git clone https://github.com/adrienverge/openfortivpn.git
cd openfortivpn
```

Pour une version spécifique (ex: 1.24.1) :
```bash
git checkout v1.24.1
```

#### 3. Compiler et installer

```bash
./autogen.sh
./configure --prefix=/usr --sysconfdir=/etc
make
sudo make install
```

#### 4. Vérifier l'installation

```bash
openfortivpn --version
# Devrait afficher : 1.24.1 (ou la version installée)
```

**Note** : Cette méthode installe openfortivpn dans `/usr/bin/openfortivpn` et remplace toute version installée via le gestionnaire de paquets.

## 🚀 Installation du VPN Manager

### Dépendances Python

Python 3.11 ou plus récent, avec `typer` et `rich` :

```bash
sudo apt install python3-typer python3-rich
```

### Installation

```bash
# Cloner le dépôt, au choix depuis :
# - GitHub
git clone https://github.com/ljouglar/vpn_launcher.git
# - GitLab Koesio (accès réservé aux collaborateurs Koesio)
git clone git@git.koesio.io:kam-lyon/vpn_launcher.git

cd vpn_launcher

# Créer la commande `vpn` dans ~/.local/bin (qui pointe vers le dépôt cloné)
mkdir -p ~/.local/bin
cat > ~/.local/bin/vpn <<EOF
#!/usr/bin/env bash
exec /usr/bin/python3 "$PWD/cli.py" "\$@"
EOF
chmod +x ~/.local/bin/vpn

# Vérifier
vpn help
```

Le premier lancement de `vpn` (menu, `vpn configure`, `vpn list`…) crée automatiquement la structure `~/.vpn/` :

```
~/.vpn/
├── vpns.conf     # Déclaration des VPN (chmod 600)
├── configs/      # Fichiers .conf openfortivpn / tunnels SSH
├── sessions/     # Sessions actives
└── logs/         # Logs de connexion
```

**Note** : la commande `vpn` exécute directement le code du dépôt cloné : ne déplacez pas le dossier après l'installation (ou relancez l'étape `cat > ~/.local/bin/vpn` depuis le nouvel emplacement).

## 🔄 Mise à jour

```bash
# Depuis le dépôt cloné
git pull
```

La commande `vpn` utilise immédiatement la nouvelle version.

## 🔧 Configuration d'un VPN

### Méthode recommandée : Assistant interactif

La façon la plus simple de configurer un VPN est d'utiliser l'assistant intégré :

```bash
vpn configure
```

L'assistant vous guidera pas à pas pour :
- Choisir un identifiant pour votre VPN
- Définir le nom affiché
- Sélectionner le type de connexion (password, 2fa, saml, ou ssh_tunnel)
- Configurer une dépendance optionnelle vers une autre connexion
- Configurer les paramètres nécessaires
- Créer automatiquement tous les fichiers requis

### Méthode manuelle (avancé)

#### 1. Récupérer le certificat SSL du serveur

```bash
echo | openssl s_client -connect SERVEUR:PORT 2>/dev/null | openssl x509 -fingerprint -noout -sha256
```

Exemple pour `vpn.example.com:443` :
```bash
echo | openssl s_client -connect vpn.example.com:443 2>/dev/null | openssl x509 -fingerprint -noout -sha256
```

Résultat (enlevez les `:`) :
```
SHA256 Fingerprint=4D:49:0E:C4:...
→ 4d490ec4d04b59c6c2c06fe5a0d5748944aa35bddaa5c36a868d9b2fe76f5f42
```

#### 2. Créer la config openfortivpn

Créez `~/.vpn/configs/mon-vpn.conf` :
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

**Note** : Le mot de passe est directement intégré dans le fichier .conf. Le fichier sera automatiquement protégé (chmod 600).

### 3. Déclarer le VPN

Éditez `~/.vpn/vpns.conf` et ajoutez :

```ini
[mon-vpn]
name = Mon VPN Corporate
auth = password
config = mon-vpn.conf
```

**Tunnel SSH (port forwarding) :**

Dans `~/.vpn/vpns.conf` :
```ini
[tunnel-db]
name = Tunnel BDD Production
auth = ssh_tunnel
config = tunnel-db.conf
depends_on = mon-vpn
```

Dans `~/.vpn/configs/tunnel-db.conf` :
```properties
ssh_key = /home/user/.ssh/id_rsa
ssh_user = root
ssh_host = 10.244.18.22
local_port = 33070
remote_host = 91.216.43.88
remote_port = 3306
```

> **Note** : `depends_on` est optionnel et fonctionne pour tous les types. Lorsqu'une dépendance est configurée, la connexion automatique est proposée si elle n'est pas active, et la déconnexion en cascade est gérée.

### 4. Tester

```bash
vpn
```

## �️ Tray Icon (Ubuntu)

Un indicateur dans la barre système permet de piloter vos VPN sans terminal :

- **Badge dynamique** : une icône bouclier affiche le nombre de VPN connectés
- **Menu déroulant** : cliquez pour voir l'état de chaque VPN (● connecté / ○ déconnecté)
- **Connect / Disconnect** : un clic pour monter ou descendre un VPN
- **Notifications** : alertes à la connexion et déconnexion
- **Autostart** : se lance automatiquement à l'ouverture de session

### Dépendances

```bash
sudo apt install gir1.2-appindicator3-0.1 python3-gi python3-gi-cairo
```

### Lancement manuel

```bash
# Depuis le dépôt cloné
./tray/vpn_tray_launch.sh &
```

### Lancement automatique à l'ouverture de session

```bash
# Depuis le dépôt cloné
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/vpn-tray.desktop <<EOF
[Desktop Entry]
Type=Application
Name=VPN Tray
Comment=Indicateur système pour gérer les connexions VPN
Exec=$PWD/tray/vpn_tray_launch.sh
Icon=network-vpn
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
```

## �💡 Exemples d'utilisation

```bash
# Menu interactif
vpn

# Créer un nouveau VPN (assistant interactif)
vpn configure

# Connexion directe au VPN #1
vpn connect 1

# Voir le statut
vpn status

# Lister les VPNs
vpn list

# Se déconnecter
vpn disconnect

# Aide
vpn help
```

## 🔐 Sécurité

- Les fichiers de configuration `.conf` contiennent des informations sensibles et sont protégés (chmod 600)
- Les logs ne contiennent jamais de mots de passe en clair
- Chaque session est isolée avec un PID unique
- N'ajoutez jamais les fichiers `*.conf` à votre gestionnaire de versions

## 🆘 Support

### La commande vpn n'est pas trouvée après installation

`~/.local/bin` n'est pas dans votre `PATH`. Sur Ubuntu, il y est ajouté automatiquement par `~/.profile` dès que le dossier existe : ouvrez une nouvelle session. Sinon, ajoutez à votre `~/.bashrc` :

```bash
export PATH="$HOME/.local/bin:$PATH"
```

### L'authentification SAML/SSO ne fonctionne pas

**Symptôme** : L'option `--saml-login` n'est pas reconnue

**Cause** : Votre version d'openfortivpn est trop ancienne (< 1.20.0)

**Solution** : Compiler openfortivpn depuis les sources (voir section "Prérequis - Option 2")

```bash
# Vérifier votre version actuelle
openfortivpn --version

# Si < 1.20.0, suivez les étapes de compilation
```

### Processus VPN "fantômes" détectés

Le script détecte et affiche les processus VPN non trackés. Pour nettoyer :

```bash
# Déconnecter un processus par son PID
vpn disconnect <PID>

# Déconnecter tous les VPN
vpn disconnect all
```

### Problèmes de connexion

Consultez les logs (un fichier par VPN) :
```bash
tail -f ~/.vpn/logs/<id-du-vpn>.log
```

### Aide complète

```bash
vpn help
```

## 📄 Licence

Ce projet est sous licence MIT. Voir le fichier [LICENSE](LICENSE) pour plus de détails.

## 👤 Auteur

**Laurent Jouglar**

## 🤝 Contributions

Les contributions sont les bienvenues ! N'hésitez pas à ouvrir une issue ou une pull request.

---

**Version** : 1.1  
**Date** : Mars 2026
