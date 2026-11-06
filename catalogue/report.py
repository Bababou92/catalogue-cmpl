"""Rapport « Signaler un problème » : un petit .zip à envoyer par Gmail / WhatsApp, + liens de partage."""
import json
import os
import platform
import subprocess
import sys
import time
import urllib.parse
import webbrowser
import zipfile

from . import errlog, version


def reports_dir(out_dir):
    d = os.path.join(os.path.abspath(os.path.expanduser(out_dir or "~")), "Rapports")
    os.makedirs(d, exist_ok=True)
    return d


def system_info():
    return (f"Programme : Catalogue CMPL {version.VERSION}\n"
            f"Système : {platform.platform()}\n"
            f"Python : {platform.python_version()} ({'exe' if getattr(sys, 'frozen', False) else 'sources'})\n"
            f"Date : {time.strftime('%Y-%m-%d %H:%M:%S')}")


def message_text(description="", error=""):
    """Texte court du message (e-mail / WhatsApp), sans pièce jointe."""
    desc = (description or "").strip() or "(non précisé)"
    err = (error or "").strip()
    out = ["Bonjour,", "",
           f"J'ai un problème avec le catalogue CMPL (version {version.VERSION}).", "",
           f"Ce qui s'est passé : {desc}"]
    if err:
        out += ["", "Message d'erreur : " + err[:400]]
    return "\n".join(out)


def error_text(error="", client_log=None):
    """Message d'erreur complet (à copier / télécharger) avec les infos utiles."""
    parts = [system_info(), "", "Erreur : " + ((error or "").strip() or "(aucun message)")]
    if client_log:
        parts += ["", "Dans la page :"] + [str(x) for x in client_log][-20:]
    parts += ["", "Journal du programme :", errlog.dump()]
    return "\n".join(parts)


def build(out_dir, catalogue, description="", error="", client_log=None):
    """Crée le .zip du rapport ; retourne {path, folder, name, size}."""
    folder = reports_dir(out_dir)
    name = "Rapport-CMPL-" + time.strftime("%Y%m%d-%H%M%S") + ".zip"
    path = os.path.join(folder, name)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("rapport.txt", "Description : " + ((description or "").strip() or "(non précisée)") + "\n\n"
                   + error_text(error, client_log))
        if catalogue is not None:
            z.writestr("catalogue.json", json.dumps(catalogue, ensure_ascii=False))
    return {"path": path, "folder": folder, "name": name, "size": os.path.getsize(path)}


def valid_report_path(path, out_dir):
    fp = os.path.abspath(path or "")
    return fp.lower().endswith(".zip") and os.path.isfile(fp) and os.path.dirname(fp) == reports_dir(out_dir)


# ---------------------------------------------------------------- partage

def gmail_url(to, subject, body):
    q = {"view": "cm", "fs": "1", "su": subject, "body": body}
    if to:
        q["to"] = to
    return "https://mail.google.com/mail/?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)


def whatsapp_url(number, text):
    digits = "".join(ch for ch in (number or "") if ch.isdigit())
    base = f"https://wa.me/{digits}" if digits else "https://wa.me/"
    return base + "?text=" + urllib.parse.quote(text)


def copy_file_to_clipboard(path):
    """Windows : met le fichier dans le presse-papiers (Ctrl+V le colle comme pièce jointe)."""
    if not sys.platform.startswith("win"):
        return False
    try:
        safe = path.replace("'", "''")
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", f"Set-Clipboard -LiteralPath '{safe}'"],
                       timeout=15, creationflags=0x08000000, capture_output=True)
        return True
    except Exception:
        return False


def reveal(path):
    """Ouvre le dossier en sélectionnant le fichier."""
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])
        return True
    except Exception:
        return False


def share(path, how, to="", number="", description="", error=""):
    """how = gmail | whatsapp. Retourne {url, copied, opened}."""
    body = message_text(description, error) + f"\n\nLe rapport est joint : {os.path.basename(path)}"
    if how == "gmail":
        url = gmail_url(to, f"Problème Catalogue CMPL {version.VERSION}", body)
    elif how == "whatsapp":
        url = whatsapp_url(number, body)
    else:
        raise ValueError("mode de partage inconnu")
    if os.environ.get("CMPL_NO_EXTERNAL"):             # essais automatiques : on n'ouvre rien
        return {"url": url, "copied": False, "opened": False}
    copied = copy_file_to_clipboard(path)
    reveal(path)
    try:
        opened = bool(webbrowser.open(url))
    except Exception:
        opened = False
    return {"url": url, "copied": copied, "opened": opened}
