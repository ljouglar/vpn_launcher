# Changelog

Toutes les modifications notables de ce projet seront documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

## [Unreleased]

### Ajouté
- **Nettoyage interactif des VPNs fantômes**
  - Si vous utilisez `vpn disconnect` sans connexions trackées mais avec des VPNs fantômes
  - Le script propose automatiquement de les nettoyer
  - Confirmation interactive avant le nettoyage
  - Utilise la fonction `cleanup_orphans()` pour un nettoyage complet
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

### Corrigé
- **Déconnexion SAML améliorée** : Kill plus robuste des processus VPN
  - Lancement SAML aligné avec password/2FA (sans `bash -c`)
  - Utilisation de SIGTERM au lieu de SIGINT pour une terminaison plus propre
  - Kill des processus enfants avant le processus parent
  - Timeouts augmentés pour laisser le temps aux processus de se terminer
  - Ordre d'élimination : enfants SIGTERM → parent SIGTERM → enfants SIGKILL → parent SIGKILL
- **Déconnexion robuste** : Vérification que le processus est vraiment tué
  - Le fichier de session n'est supprimé que si le processus est confirmé mort
  - Message d'erreur si le processus ne peut pas être tué
  - Évite la création de VPNs orphelins lors de la déconnexion
- Détection et avertissement pour les interfaces ppp orphelines après déconnexion
- Synchronisation entre l'état réel des VPNs et les fichiers de session
- Les VPNs connectés en dehors du script sont maintenant visibles et gérables

### Modifié
- `install.sh` crée maintenant un lien symbolique `~/vpn` au lieu de copier le script
  - Permet les mises à jour automatiques via `git pull`
  - Facilite le développement et les contributions
  - Documentation mise à jour en conséquence

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
