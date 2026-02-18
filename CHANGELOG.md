# Changelog

Toutes les modifications notables de ce projet seront documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

## [Unreleased]

### Ajouté
- Détection des VPNs non trackés (processus orphelins)
  - `vpn status` affiche maintenant les VPNs connectés mais non trackés
  - Affichage du PID, IP et commande des VPNs orphelins
  - Message d'aide pour les déconnecter
- Déconnexion par PID pour gérer les VPNs non trackés
  - `vpn disconnect <pid>` : déconnexion par PID (ex: `vpn disconnect 322169`)
  - Vérifie que le PID est bien un processus openfortivpn
  - Nettoie automatiquement les sessions orphelines associées
- Déconnexion en ligne de commande avec arguments
  - `vpn disconnect <id>` : déconnexion par ID de VPN (ex: `vpn disconnect koesio-sso`)
  - `vpn disconnect <numéro>` : déconnexion par position (ex: `vpn disconnect 1`)
  - `vpn disconnect all` : déconnexion de tous les VPNs (trackés et non trackés)
  - Mode interactif conservé si aucun argument fourni
- Ouverture automatique du navigateur pour l'authentification SAML
  - Utilise `xdg-open` (standard Linux) avec fallbacks pour GNOME, KDE
  - Essaie également Firefox, Chrome, Chromium si disponibles
  - Message d'information si l'ouverture automatique échoue

### Modifié
- `install.sh` crée maintenant un lien symbolique `~/vpn` au lieu de copier le script
  - Permet les mises à jour automatiques via `git pull`
  - Facilite le développement et les contributions
  - Documentation mise à jour en conséquence

### Corrigé
- Synchronisation entre l'état réel des VPNs et les fichiers de session
- Les VPNs connectés en dehors du script sont maintenant visibles et gérables

## [1.0.0] - 2026-02-18

### Ajouté
- Script principal `vpn` avec menu interactif
- Support de 3 modes d'authentification (password, 2FA, SAML)
- Gestion multi-VPN (connexions simultanées)
- Parseur INI pur bash pour la configuration
- Système de logs détaillés
- Gestion sécurisée des mots de passe (chmod 600)
- Installeur automatique (`install.sh`)
- Documentation complète pour utilisateurs et développeurs
- Templates de configuration avec exemples
- Menu interactif pour sélection/déconnexion des VPNs
- Auto-nettoyage des sessions et fichiers temporaires
- Support des timeouts personnalisables par VPN
- Détection automatique des interfaces ppp et adresses IP

### Fonctionnalités techniques
- Tracking de session par PID
- Gestion des routes VPN
- Support de certificats SSL (trusted-cert)
- Logs séparés par VPN pour le dépannage
- Interface CLI complète (connect, disconnect, status, list, help)
- Couleurs dans l'interface pour meilleure lisibilité

[1.0.0]: https://github.com/ljouglar/vpn_launcher/releases/tag/v1.0.0
