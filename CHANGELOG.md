# Changelog

Toutes les modifications notables de ce projet seront documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

## [1.0.0] - 2026-02-18

### Ajouté
- Script principal `vpn` avec menu interactif
- Support de 3 modes d'authentification (password, 2FA, SAML)
- Gestion multi-VPN (connexions simultanées)
- Parseur INI pur bash pour la configuration
- Système de logs détaillés
- Gestion sécurisée des mots de passe (chmod 600)
- Installeur automatique (`install.sh`)
- Documentation complète (README, QUICKSTART, guide de distribution)
- Script de création de package (`create-package.sh`)
- Templates de configuration avec exemples
- Menu interactif pour sélection/déconnexion des VPNs
- Auto-nettoyage des sessions et fichiers temporaires
- Support des timeouts personnalisables par VPN
- Détection automatique des interfaces ppp et adresses IP
- Template d'email pour la distribution

### Fonctionnalités techniques
- Tracking de session par PID
- Gestion des routes VPN
- Support de certificats SSL (trusted-cert)
- Logs séparés par VPN pour le dépannage
- Interface CLI complète (connect, disconnect, status, list, help)
- Couleurs dans l'interface pour meilleure lisibilité

[1.0.0]: https://github.com/votre-org/vpn-launcher/releases/tag/v1.0.0
