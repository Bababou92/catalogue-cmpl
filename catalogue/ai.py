"""Descriptions écrites par Claude (API Anthropic) pour les livres sans résumé.

Appel direct à l'API HTTP (aucune bibliothèque en plus). La clé reste sur le PC (réglages)."""
import json
import re
import time
import urllib.error
import urllib.request

from . import sources, store, usage

API = "https://api.anthropic.com/v1/messages"
MODELS = ("claude-haiku-5-5", "claude-sonnet-5-5")          # Haiku suffit largement ; Sonnet sert de secours si le 1er est refusé

SYSTEM = (
    "Tu rédiges les descriptions d'un catalogue de librairie universitaire et professionnelle (éditions CMPL, Madagascar). "
    "Style : celui des notices professionnelles de librairie — phrases nominales, informatives et sobres, sans enthousiasme, "
    "environ 250 à 400 caractères. Tu t'appuies UNIQUEMENT sur les informations fournies et sur ce que tu sais avec certitude "
    "de cet ouvrage. N'invente jamais : pas de chiffres, de chapitres, de nouveautés d'édition ou de prix qui ne figurent pas dans "
    "les données. Si les données sont minces, reste général (contenu, public visé, utilité) plutôt que d'inventer des détails. "
    "Un seul paragraphe, sans titre, sans liste, sans guillemets, sans émojis. "
    "Ne commence pas par le titre du livre ni par « Ce livre » / « Cet ouvrage » ; ne cite pas les auteurs ni l'éditeur. "
    "Termine toujours par une phrase complète. Réponds uniquement par le texte de la description.\n\n"
    "Exemples du ton attendu :\n"
    "- Un guide pratique pour aider l'étudiant dans toutes les étapes de la rédaction du mémoire ou du rapport de stage : choix du "
    "sujet, conception du plan, gestion du temps, rédaction, mise en forme des citations et de la bibliographie. Il prend également "
    "en compte des problématiques liées à Internet telles que le tri d'informations ou le plagiat.\n"
    "- Présentation pédagogique de la comptabilité permettant d'en acquérir les bases : le rôle de la comptabilité générale, les "
    "documents de synthèse ou encore le plan comptable général. Avec un chapitre abordant la comptabilité environnementale et le "
    "rôle du commissaire aux comptes ainsi que des exemples, des astuces et des exercices corrigés.\n"
    "- En complément du manuel, l'ouvrage propose tous les corrigés détaillés, des applications et des études de cas. Ils sont "
    "assortis de conseils, de rappels méthodologiques et d'un décryptage des compétences.\n"
    "- Cyberattaques sur les infrastructures, hacking, espionnage, fake news, le cyberespace est devenu un champ privilégié des "
    "relations internationales. Panorama des enjeux de la cyberconflictualité."
)


class AIError(Exception):
    pass


class AINetworkError(AIError):
    """Connexion absente ou coupée pendant l'appel à Claude."""


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


_NO_THINKING_OK = set()                  # modèles qui ont refusé le réglage « réflexion désactivée » : on ne le leur envoie plus


def thinking_off():
    """Réglage « Réflexion du modèle » (Réglages > IA). Par défaut elle reste activée : meilleure fiabilité du texte,
    mais ses jetons sont facturés comme du texte de sortie (environ trois fois le coût d'une description)."""
    try:
        return store.load_settings().get("ia_reflexion") == "off"
    except Exception:
        return False


def post_json(key, model, system, prompt, max_tokens=1500):
    """Appel à l'API Claude ; la réflexion adaptative (activée par défaut sur Haiku 5.5) n'est coupée que si le réglage le demande."""
    def call(with_thinking_off):
        d = {"model": model, "max_tokens": max_tokens, "system": system, "messages": [{"role": "user", "content": prompt}]}
        if with_thinking_off:
            d["thinking"] = {"type": "disabled"}
        req = urllib.request.Request(API, data=json.dumps(d).encode("utf-8"), method="POST", headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json",
            "User-Agent": sources.UA["User-Agent"]})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    if model in _NO_THINKING_OK or not thinking_off():
        return call(False)
    try:
        return call(True)
    except urllib.error.HTTPError as e:
        if e.code == 400 and "thinking" in _error_text(e).lower():
            _NO_THINKING_OK.add(model)
            return call(False)
        raise


def _post(key, model, prompt, max_tokens=1500):
    return post_json(key, model, SYSTEM, prompt, max_tokens)


def _error_text(e):
    """Message d'erreur de l'API ; mis en mémoire sur l'exception car le corps ne se lit qu'une fois."""
    if hasattr(e, "_cmpl_msg"):
        return e._cmpl_msg
    try:
        j = json.loads(e.read().decode("utf-8", "replace"))
        msg = (j.get("error") or {}).get("message", "")
    except Exception:
        msg = ""
    try:
        e._cmpl_msg = msg
    except Exception:
        pass
    return msg


def describe(book, key, max_chars=420, model=None):
    """Retourne le texte de description. Lève AIError avec un message lisible."""
    if not key:
        raise AIError("pas de clé Claude (Réglages)")
    prompt = build_prompt(book, max_chars)
    models = [model] + [m for m in MODELS if m != model] if model else list(MODELS)
    last = ""
    netfail = 0
    for m in models:
        for attempt in range(3):
            try:
                j = _post(key, m, prompt)
                netfail = 0
                usage.record("descriptions_nr" if thinking_off() else "descriptions", m, j.get("usage"))
                txt = "".join(c.get("text", "") for c in j.get("content", []) if c.get("type") == "text").strip()
                txt = re.sub(r"^[\"«»\s]+|[\"«»\s]+$", "", txt)
                if j.get("stop_reason") == "max_tokens":          # réponse coupée : on ne l'enregistre jamais
                    last = "réponse coupée par l'IA, réessaie"
                    continue
                txt = sources.clean_resume(txt, max_chars)
                if not txt or (len(txt) < 40 and not re.search(r"[.!?…]$", txt)):
                    last = "réponse vide ou incomplète"
                    continue
                return txt
            except urllib.error.HTTPError as e:
                netfail = 0
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
            except OSError as e:                                     # coupure, délai dépassé, DNS…
                last = "connexion impossible : " + str(e)
                netfail += 1
                time.sleep(1.5)
            except Exception as e:                                   # réponse illisible
                last = "réponse illisible : " + str(e)
                time.sleep(1.5)
        if netfail >= 3:                                      # trois coupures de suite : inutile d'essayer l'autre modèle
            raise AINetworkError(last)
    raise AIError(last or "échec de la génération")
