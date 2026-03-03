#!/bin/bash
# Wrapper pour lancer vpn_tray.py avec l'environnement système natif.
#
# Nécessaire lorsque le lancement se fait depuis un terminal snap
# (ex: VS Code snap) dont les variables d'environnement (LD_LIBRARY_PATH,
# GIO_MODULE_DIR…) pointent vers les libs snap, incompatibles avec
# les modules GTK/AppIndicator3 du système.

# Nettoyer les variables injectées par snap
unset LD_LIBRARY_PATH
unset GIO_MODULE_DIR
unset GTK_PATH
unset GTK_EXE_PREFIX
unset GDK_PIXBUF_MODULE_FILE
unset LOCPATH
unset GI_TYPELIB_PATH

# Restaurer le PATH système (retirer les entrées snap/core*)
export PATH=$(echo "$PATH" | tr ':' '\n' | grep -v '/snap/core' | tr '\n' ':' | sed 's/:$//')

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
exec /usr/bin/python3 "$SCRIPT_DIR/vpn_tray.py" "$@"
