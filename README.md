# 🚀 VPN Manager

Gestionnaire VPN multi-connexions pour Linux avec support FortiVPN. Interface interactive pour gérer plusieurs connexions VPN simultanément avec différents modes d'authentification.

## ✨ Fonctionnalités

- **Multi-VPN** : Gérez plusieurs connexions VPN simultanées
- **3 modes d'authentification** : Password, 2FA (FortiToken), SAML/SSO
- **Interface interactive** : Menu simple et intuitif
- **Logs détaillés** : Pour le dépannage et le monitoring
- **Sécurisé** : Mots de passe protégés (chmod 600)
- **Nettoyage automatique** : Pas d'interfaces fantômes

## 📋 Prérequis

Installer `openfortivpn` :

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

## 🚀 Installation

```bash
# Cloner le dépôt
git clone https://github.com/ljouglar/vpn_launcher.git
cd vpn_launcher

# Lancer l'installation
./install.sh
```

Le script va :
- ✅ Vérifier que `openfortivpn` est installé
- ✅ Créer la structure de dossiers `~/.vpn/`
- ✅ Créer un lien symbolique `~/vpn` vers le script
- ✅ Créer des fichiers de configuration template
- ✅ Créer un README avec toute la documentation

**Note** : `~/vpn` est un lien symbolique vers le dépôt cloné, ce qui permet de mettre à jour facilement.

Après installation, consultez la documentation complète :
```bash
cat ~/.vpn/README.md
```

## 🔄 Mise à jour

```bash
# Se rendre dans le dépôt cloné
cd vpn_launcher

# Mettre à jour
git pull

# Le script ~/vpn est automatiquement à jour (lien symbolique)
```

## 🔧 Configuration d'un VPN

### 1. Récupérer le certificat SSL du serveur

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

### 2. Créer la config openfortivpn

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

### 4. Tester

```bash
~/vpn
```

## 💡 Exemples d'utilisation

```bash
# Menu interactif
~/vpn

# Connexion directe au VPN #1
~/vpn connect 1

# Voir le statut
~/vpn status

# Lister les VPNs
~/vpn list

# Se déconnecter
~/vpn disconnect

# Aide
~/vpn help
```

## 🔐 Sécurité

- Les fichiers de configuration `.conf` contiennent des informations sensibles et sont protégés (chmod 600)
- Les logs ne contiennent jamais de mots de passe en clair
- Chaque session est isolée avec un PID unique
- N'ajoutez jamais les fichiers `*.conf` à votre gestionnaire de versions

## 🆘 Support

### Le script vpn n'est pas trouvé après installation

Soit :
- Utilisez le chemin complet : `~/vpn`
- Ajoutez `~/` au PATH (l'installeur le propose)
- Relancez un nouveau terminal après avoir sourcé `.bashrc`

### Problèmes de connexion

Consultez les logs :
```bash
tail -f ~/.vpn/logs/vpn.log
```

### Aide complète

```bash
~/vpn help
cat ~/.vpn/README.md
```

## 📄 Licence

Ce projet est sous licence MIT. Voir le fichier [LICENSE](LICENSE) pour plus de détails.

## 👤 Auteur

**Laurent Jouglar**

## 🤝 Contributions

Les contributions sont les bienvenues ! N'hésitez pas à ouvrir une issue ou une pull request.

---

**Version** : 1.0  
**Date** : Février 2026
