"""Descriptions écrites par Claude (API Anthropic) pour les livres sans résumé.

Appel direct à l'API HTTP (aucune bibliothèque en plus). La clé reste sur le PC (réglages)."""
import json
import re
import time
import urllib.error
import urllib.request

from . import sources

API = "https://api.anthropic.com/v1/messages"
MODELS = ("claude-sonnet-5-5", "claude-haiku-5-5")          # le 2e sert de secours si le 1er est refusé

SYSTEM = (
    "Tu rédiges les descriptions d'un catalogue de librairie universitaire et professionnelle (éditions CMPL, Madagascar). "
    "Style : français soigné, sobre et informatif, comme une quatrième de couverture d'ouvrage de référence. "
    "Tu t'appuies UNIQUEMENT sur les informations fournies et sur ce que tu sais avec certitude de cet ouvrage. "
    "N'invente jamais : pas de chiffres, de chapitres, de nouveautés d'édition ou de prix qui ne figurent pas dans les données. "
    "Si les données sont minces, reste général (public visé, domaine, utilité de l'ouvrage) plutôt que d'inventer des détails. "
    "Un seul paragraphe, sans titre, sans liste, sans guillemets, sans émojis. "
    "Ne commence pas par le titre du livre ni par « Ce livre » ; ne cite pas les auteurs ni l'éditeur. "
    "Réponds uniquement par le texte de la description."
)


class AIError(Exception):
    pass


def build_prompt(book, max_chars):
    L = [f"Titre : {book.get('titre', '')}"]
    for lab, k in (("Auteurs", "auteurs"), ("Éditeur", "editeur"), ("Collection", "collection"),
                   ("Date de parution", "date"), ("Pages", "pages")):
        v = book.get(k)
        if isinstance(v, list):
            v = " ; ".join(v)
        if v:
            L.append(f"{lab} : {v}")
    if book.get("sujets"):
        L.append("Sujets (notice BnF) : " + " ; ".join(book["sujets"][:8]))
    if book.get("resume"):
        L.append("Texte existant (à reformuler, raccourcir ou traduire en français) : " + book["resume"][:1500])
    L.append("")
    L.append(f"Écris la description : environ {int(max_chars * 0.8)} à {max_chars} caractères au maximum.")
    return "\n".join(L)


def _post(key, model, prompt, max_tokens=400):
    body = json.dumps({"model": model, "max_tokens": max_tokens, "system": SYSTEM,
                       "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
    req = urllib.request.Request(API, data=body, method="POST", headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json",
        "User-Agent": sources.UA["User-Agent"]})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _error_text(e):
    try:
        j = json.loads(e.read().decode("utf-8", "replace"))
        return (j.get("error") or {}).get("message", "")
    except Exception:
        return ""


def describe(book, key, max_chars=420, model=None):
    """Retourne le texte de description. Lève AIError avec un message lisible."""
    if not key:
        raise AIError("pas de clé Claude (Réglages)")
    prompt = build_prompt(book, max_chars)
    models = [model] + [m for m in MODELS if m != model] if model else list(MODELS)
    last = ""
    for m in models:
        for attempt in range(3):
            try:
                j = _post(key, m, prompt)
                txt = "".join(c.get("text", "") for c in j.get("content", []) if c.get("type") == "text").strip()
                if not txt:
                    raise AIError("réponse vide")
                return sources.clean_resume(re.sub(r"^[\"«»\s]+|[\"«»\s]+$", "", txt), max_chars)
            except urllib.error.HTTPError as e:
                msg = _error_text(e)
                if e.code == 401:
                    raise AIError("clé Claude refusée (vérifie-la dans les Réglages)")
                if e.code == 402 or "credit balance" in msg.lower():
                    raise AIError("plus de crédit sur ton compte Claude (console.anthropic.com → Billing)")
                if e.code in (429, 500, 502, 503, 529):
                    last = f"service Claude occupé ({e.code})"
                    time.sleep(2 + 3 * attempt)
                    continue
                if e.code in (400, 404) and ("model" in msg.lower() or e.code == 404):
                    last = "modèle indisponible : " + msg
                    break                                            # on tente le modèle suivant
                raise AIError(f"Claude : {msg or 'erreur ' + str(e.code)}")
            except AIError:
                raise
            except Exception as e:
                last = "connexion impossible : " + str(e)
                time.sleep(1.5)
        else:
            continue
    raise AIError(last or "échec de la génération")
