# VPN Manager - Documentation Développeur

Documentation technique et guide de contribution pour le projet VPN Manager.

## 📁 Structure du projet

```
vpn_launcher/
├── vpn                    → Script principal du gestionnaire VPN (bash)
├── install.sh             → Script d'installation pour les utilisateurs
│
├── README.md              → Documentation utilisateur principale
├── CHANGELOG.md           → Historique des versions
├── LICENSE                → Licence MIT
├── VERSION                → Numéro de version actuel
│
├── .git/                  → Dépôt Git
├── .gitignore             → Fichiers exclus de Git
└── PROJECT_README.md      → Ce fichier (documentation développeur)
```

## 🚀 Démarrage rapide (développeur)

### Cloner le projet

```bash
git clone https://github.com/ljouglar/vpn_launcher.git
cd vpn_launcher
```

### Tester localement sans installer

```bash
# Rendre le script exécutable
chmod +x vpn

# Exécuter directement
./vpn
```

### Installer en mode développement

```bash
# Installation standard
./install.sh

# ~/vpn devient un lien symbolique vers le dépôt
# Vos modifications sont immédiatement visibles, pas besoin de réinstaller !
```

## 🔧 Développement

### Modifier le script principal

Le fichier `vpn` est un script bash standalone qui contient toute la logique. Structure :

- **Variables globales** : Chemins, couleurs, constantes
- **Fonctions utilitaires** : Logging, affichage, parsing config
- **Fonctions métier** : Connexion, déconnexion, status, nettoyage
- **Menu interactif** : Interface TUI
- **Point d'entrée** : Parsing des arguments CLI

### Tester vos modifications

```bash
# Méthode 1 : Test direct (recommandé)
./vpn

# Méthode 2 : Via le lien symbolique (après installation)
~/vpn
# Les modifications sont automatiquement visibles car ~/vpn est un lien symbolique

# Méthode 3 : Test dans un conteneur/VM pour isoler
docker run -it --rm ubuntu:22.04 bash
# puis copier le projet et tester
```

### Standards de code

- **Style bash** : Suivre les conventions ShellCheck
- **Indentation** : 4 espaces
- **Commentaires** : Documenter les fonctions complexes
- **Sécurité** : Ne jamais logger de mots de passe, protéger les fichiers sensibles (chmod 600)

### Vérifier la qualité du code

```bash
# Installer shellcheck
sudo apt install shellcheck  # Ubuntu/Debian
brew install shellcheck      # macOS

# Analyser le code
shellcheck vpn
shellcheck install.sh
```

## 📦 Versioning

Le projet utilise le versioning sémantique (SemVer) : `MAJOR.MINOR.PATCH`

### Créer une nouvelle version

1. **Mettre à jour VERSION**
   ```bash
   echo "1.1.0" > VERSION
   ```

2. **Mettre à jour CHANGELOG.md**
   ```markdown
   ## [1.1.0] - 2026-02-18
   ### Added
   - Nouvelle fonctionnalité X
   ### Fixed
   - Correction du bug Y
   ```

3. **Commit et tag**
   ```bash
   git add VERSION CHANGELOG.md
   git commit -m "Release v1.1.0"
   git tag -a v1.1.0 -m "Version 1.1.0"
   git push origin main --tags
   ```

## 🤝 Contribution

### Workflow de contribution

1. **Fork** le projet sur GitHub
2. **Créer une branche** pour votre fonctionnalité
   ```bash
   git checkout -b feature/ma-fonctionnalite
   ```
3. **Développer** et commiter vos changements
   ```bash
   git add .
   git commit -m "feat: ajout de ma fonctionnalité"
   ```
4. **Tester** votre code
5. **Pousser** sur votre fork
   ```bash
   git push origin feature/ma-fonctionnalite
   ```
6. **Créer une Pull Request** vers `main`

### Convention de commits

Utiliser le format [Conventional Commits](https://www.conventionalcommits.org/) :

- `feat:` Nouvelle fonctionnalité
- `fix:` Correction de bug
- `docs:` Documentation uniquement
- `style:` Formatage, indentation
- `refactor:` Refactoring sans changement fonctionnel
- `test:` Ajout de tests
- `chore:` Maintenance, dépendances

Exemples :
```bash
git commit -m "feat: ajout du support pour OpenVPN"
git commit -m "fix: correction du nettoyage des interfaces"
git commit -m "docs: mise à jour du README avec exemples"
```

### Checklist avant PR

- [ ] Le code passe shellcheck sans erreur
- [ ] Les modifications sont testées localement
- [ ] La documentation (README.md) est mise à jour si nécessaire
- [ ] CHANGELOG.md est mis à jour dans la section [Unreleased]
- [ ] Le commit message suit la convention

## 🧪 Tests

### Tests manuels

```bash
# Tester l'installation complète
./install.sh

# Tester le menu interactif
~/vpn

# Tester les commandes CLI
~/vpn help
~/vpn list
~/vpn status

# Vérifier les logs
tail -f ~/.vpn/logs/vpn.log
```

### Scénarios de test recommandés

1. **Installation fraîche** : Sur un système sans config existante
2. **Mise à jour** : Réinstaller sur un système avec config existante
3. **Multi-VPN** : Connecter 2+ VPNs simultanément
4. **Authentification** : Tester les 3 modes (password, 2FA, SAML)
5. **Nettoyage** : Vérifier qu'aucune interface fantôme ne reste après déconnexion

## 🐛 Debugging

### Activer le mode verbose

```bash
# Éditer le script vpn et ajouter en haut :
set -x  # Active le mode debug bash
```

### Logs utiles

```bash
# Logs du gestionnaire VPN
tail -f ~/.vpn/logs/vpn.log

# Logs système openfortivpn
sudo journalctl -u vpn_* -f

# Logs réseau
ip link show
ip route show
```

### Problèmes courants

**Interface ppp* bloquée**
```bash
# Lister les interfaces
ip link show | grep ppp

# Supprimer manuellement
sudo pkill -f openfortivpn
sudo ip link delete ppp0  # ou ppp1, etc.
```

**Permissions sudo**
```bash
# Vérifier les droits sudo sans mot de passe
sudo -l

# Ajouter si nécessaire (dans /etc/sudoers.d/vpn-manager)
votre_user ALL=(ALL) NOPASSWD: /usr/bin/openfortivpn
```

## 📚 Ressources

### Documentation externe

- [openfortivpn GitHub](https://github.com/adrienverge/openfortivpn)
- [FortiGate VPN](https://docs.fortinet.com/)
- [Bash Scripting Guide](https://www.gnu.org/software/bash/manual/)
- [ShellCheck](https://www.shellcheck.net/)

### Architecture du système VPN

```
┌─────────────┐
│   ~/vpn     │  Script principal (interface utilisateur)
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────┐
│  ~/.vpn/                                        │
│  ├── vpns.conf       → Déclaration des VPNs     │
│  ├── configs/        → Configs openfortivpn     │
│  ├── passwords.conf  → Mots de passe (chmod 600)│
│  └── logs/           → Logs des connexions      │
└──────┬──────────────────────────────────────────┘
       │
       ▼
┌──────────────────────┐
│   openfortivpn       │  Client VPN FortiGate
│   (processus sudo)   │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  ppp0, ppp1, ...     │  Interfaces réseau VPN
└──────────────────────┘
```

## 📝 Licence

Ce projet est sous licence MIT. Voir [LICENSE](LICENSE) pour plus de détails.

## 👤 Mainteneur

**Laurent Jouglar**
- GitHub: [@ljouglar](https://github.com/ljouglar)

## 🔗 Liens utiles

- [Issues](https://github.com/ljouglar/vpn_launcher/issues)
- [Pull Requests](https://github.com/ljouglar/vpn_launcher/pulls)
- [Releases](https://github.com/ljouglar/vpn_launcher/releases)

---

**Pour les utilisateurs finaux**, consultez plutôt [README.md](README.md).
