"""Citations de la 4e de couverture : une liste intégrée (auteurs connus, sur la lecture et le livre),
un tirage sans répétition (« Autre citation »), et un bouton IA (Haiku) quand on a fait le tour.

Fonctionnement anti-gaspillage du bouton IA :
- il n'apparaît qu'une fois toutes les citations disponibles passées en revue (le « tour » est fait) ;
- un seul appel rapporte 12 citations, enregistrées sur le PC et ajoutées au tirage : on ne repaie pas pour les revoir ;
- 30 secondes minimum entre deux appels, un seul appel à la fois, et au plus 6 appels par jour ;
- les citations déjà connues sont envoyées à l'IA pour qu'elle n'en propose pas de doublon.
"""
import json
import math
import os
import random
import re
import threading
import time
import unicodedata
import urllib.error

from . import ai, store, usage

QUOTES = [
    ("Un livre est un jardin que l'on porte dans sa poche.", "Proverbe arabe"),
    ("Un lecteur vit mille vies avant de mourir. Celui qui ne lit jamais n'en vit qu'une.", "George R. R. Martin"),
    ("Les livres sont les abeilles qui transportent le pollen d'un esprit à un autre.", "James Russell Lowell"),
    ("Un livre est un rêve que l'on tient dans ses mains.", "Neil Gaiman"),
    ("Lire, c'est boire et manger. L'esprit qui ne lit pas maigrit comme le corps qui ne mange pas.", "Victor Hugo"),
    ("Un livre doit être la hache qui brise la mer gelée en nous.", "Franz Kafka"),
    ("Les livres ne sont pas faits pour qu'on y croie, mais pour qu'on les soumette à l'examen.", "Umberto Eco"),
    ("Là où l'on brûle des livres, on finit par brûler des hommes.", "Heinrich Heine"),
    ("Je me suis toujours imaginé que le Paradis serait une espèce de bibliothèque.", "Jorge Luis Borges"),
    ("Que d'autres se vantent des pages qu'ils ont écrites ; moi, je suis fier de celles que j'ai lues.", "Jorge Luis Borges"),
    ("Le livre est un prolongement de la mémoire et de l'imagination.", "Jorge Luis Borges"),
    ("La lecture est au seuil de la vie spirituelle ; elle peut nous y introduire : elle ne la constitue pas.", "Marcel Proust"),
    ("Les jours de notre enfance que nous avons le plus pleinement vécus sont ceux que nous avons passés avec un livre préféré.", "Marcel Proust"),
    ("Un livre est une fenêtre par laquelle on s'évade.", "Julien Green"),
    ("La lecture est le voyage de ceux qui ne peuvent pas prendre le train.", "Francis de Croisset"),
    ("Il n'existe pas de livres moraux ou immoraux. Les livres sont bien écrits, ou mal écrits. C'est tout.", "Oscar Wilde"),
    ("Celui qui lit beaucoup et marche beaucoup voit beaucoup et sait beaucoup.", "Miguel de Cervantès"),
    ("Les livres sont les plus silencieux et les plus constants des amis.", "Charles W. Eliot"),
    ("Je n'ai jamais eu de chagrin qu'une heure de lecture n'ait dissipé.", "Montesquieu"),
    ("Une pièce sans livres est comme un corps sans âme.", "Cicéron"),
    ("Si vous avez un jardin et une bibliothèque, vous avez tout ce qu'il vous faut.", "Cicéron"),
    ("Lire, c'est aller à la rencontre d'une chose qui va être, et que personne ne sait encore ce qu'elle sera.", "Italo Calvino"),
    ("Un classique est un livre qui n'a jamais fini de dire ce qu'il a à dire.", "Italo Calvino"),
    ("Les livres sont les phares dressés dans le grand océan du temps.", "Edwin Percy Whipple"),
    ("La lecture de tous les bons livres est comme une conversation avec les plus honnêtes gens des siècles passés.", "René Descartes"),
    ("Il y a plus de trésors dans les livres que dans tout le butin des pirates de l'île au trésor.", "Walt Disney"),
    ("Je ne puis vivre sans livres.", "Thomas Jefferson"),
    ("J'ai commencé ma vie comme je la finirai sans doute : au milieu des livres.", "Jean-Paul Sartre"),
    ("La culture, c'est ce qui reste quand on a tout oublié.", "Édouard Herriot"),
    ("Le verbe lire ne supporte pas l'impératif.", "Daniel Pennac"),
    ("Le temps de lire est toujours du temps volé.", "Daniel Pennac"),
    ("Lisez pour vivre.", "Gustave Flaubert"),
    ("Fonder des bibliothèques, c'est construire des greniers publics, thésauriser contre un hiver de l'esprit.", "Marguerite Yourcenar"),
    ("Pour détruire une culture, il n'est pas besoin de brûler les livres : il suffit que les gens cessent de les lire.", "Ray Bradbury"),
    ("Les livres sont une magie unique et portative.", "Stephen King"),
    ("On lit pour savoir que l'on n'est pas seul.", "William Nicholson"),
    ("Il n'est pas de frégate comme un livre pour nous emporter vers des terres lointaines.", "Emily Dickinson"),
    ("Les livres sont des miroirs : on n'y voit que ce que l'on porte déjà en soi.", "Carlos Ruiz Zafón"),
    ("Chaque livre, chaque volume que tu vois ici, a une âme.", "Carlos Ruiz Zafón"),
    ("Sans les mots, sans l'écriture et sans les livres, il n'y aurait pas d'histoire, il n'y aurait pas de notion d'humanité.", "Hermann Hesse"),
    ("Quand j'ai un peu d'argent, j'achète des livres ; s'il m'en reste, j'achète de quoi manger et me vêtir.", "Érasme"),
    ("Celui qui lit aura vécu 5 000 ans ; celui qui ne lit pas n'aura vécu qu'une seule vie : la sienne.", "Umberto Eco"),
    ("Certains livres sont à goûter, d'autres à être avalés, et quelques-uns seulement à être mâchés et digérés.", "Francis Bacon"),
    ("En Afrique, quand un vieillard meurt, c'est une bibliothèque qui brûle.", "Amadou Hampâté Bâ"),
    ("S'il y a un livre que vous voulez lire mais qu'il n'a pas encore été écrit, alors vous devez l'écrire.", "Toni Morrison"),
    ("La littérature est la plus agréable façon d'ignorer la vie.", "Fernando Pessoa"),
    ("Si tu ne lis que les livres que tout le monde lit, tu ne peux penser que ce que tout le monde pense.", "Haruki Murakami"),
    ("Plus tu lis, plus tu sauras de choses. Plus tu apprendras, plus tu iras de lieux.", "Dr. Seuss"),
    ("Le loisir sans les lettres, c'est la mort.", "Sénèque"),
    ("Je ne cherche aux livres qu'à m'y donner du plaisir par un honnête amusement.", "Montaigne"),
    ("Quand une lecture vous élève l'esprit et vous inspire des sentiments nobles et courageux, ne cherchez pas une autre règle pour juger de l'ouvrage : il est bon.", "La Bruyère"),
    ("Le monde est fait pour aboutir à un beau livre.", "Stéphane Mallarmé"),
    ("On ne peut pas lire un livre : on peut seulement le relire.", "Vladimir Nabokov"),
    ("Les classiques sont ces livres dont on entend dire d'ordinaire : “Je suis en train de le relire”, jamais “Je suis en train de le lire”.", "Italo Calvino"),
]

MAX_LEN = 200                      # caractères d'une citation (3 lignes dans le bandeau)
LOCK = threading.Lock()
AI_STATE = {"last": 0.0, "busy": False}
AI_COOLDOWN = 30.0                 # secondes entre deux appels
AI_PER_DAY = 6
AI_BATCH = 12


def _norm(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _path():
    return os.path.join(store.data_dir(), "citations_ia.json")


def _load_ia():
    try:
        with open(_path(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_ia(d):
    tmp = _path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _path())


def pool():
    """Toutes les citations disponibles : intégrées + celles rapportées par l'IA. [(texte, auteur, ia)]"""
    out = [(t, a, False) for t, a in QUOTES]
    out += [(q["t"], q["a"], True) for q in _load_ia().get("quotes", []) if q.get("t") and q.get("a")]
    return out


def _key(q):
    return _norm(q[0])


def current(meta):
    """(texte, auteur, ia) affichés sur la 4e de couverture, ou None (« sans citation »)."""
    if meta.get("citation_off") == "1":
        return None
    t = (meta.get("citation") or "").strip()
    if t:
        return t, (meta.get("citation_auteur") or "").strip(), meta.get("citation_ia") == "1"
    p = pool()
    seed = sum(ord(c) for c in (meta.get("titre", "") + meta.get("date", "")))
    return p[seed % len(p)]


def _apply(meta, q):
    meta["citation"], meta["citation_auteur"], meta["citation_ia"] = q[0], q[1], "1" if q[2] else "0"
    meta.pop("citation_off", None)


def _bag(meta):
    try:
        return [k for k in json.loads(meta.get("citation_bag") or "[]") if isinstance(k, str)]
    except Exception:
        return []


def _hist(meta):
    try:
        return [h for h in json.loads(meta.get("citation_hist") or "[]") if isinstance(h, list) and len(h) == 3]
    except Exception:
        return []


def status(meta):
    """Pour l'interface : citation actuelle, nombre restantes, tour fait ?, état du bouton IA."""
    p = pool()
    keys = {_key(q) for q in p}
    bag = [k for k in _bag(meta) if k in keys]
    cur = current(meta)
    today = time.strftime("%Y-%m-%d")
    ia = _load_ia()
    used = ia.get("day_count", 0) if ia.get("day") == today else 0
    wait = max(0, math.ceil(AI_COOLDOWN - (time.time() - AI_STATE["last"])))
    return {
        "texte": cur[0] if cur else "", "auteur": cur[1] if cur else "", "ia": bool(cur and cur[2]), "off": cur is None,
        "total": len(p), "ia_total": len(ia.get("quotes", [])), "restantes": len(bag),
        "tour_fait": meta.get("citation_tour") == "1",
        "peut_prev": len(_hist(meta)) > 0,
        "ia_restant": max(0, AI_PER_DAY - used), "ia_attente": wait, "ia_occupe": AI_STATE["busy"],
    }


def next_quote(meta):
    """Citation suivante : tirage dans un « sac » mélangé, jamais deux fois la même avant la fin du tour."""
    by = {_key(q): q for q in pool()}
    cur = current(meta)
    ck = _key(cur) if cur else None
    hist = _hist(meta)
    if cur:
        hist.append([cur[0], cur[1], "1" if cur[2] else "0"])
    meta["citation_hist"] = json.dumps(hist[-30:], ensure_ascii=False)
    bag = [k for k in _bag(meta) if k in by and k != ck]
    if not bag:                                              # nouveau tour : tout est remélangé (sauf celle affichée)
        bag = [k for k in by if k != ck]
        random.shuffle(bag)
    k = bag.pop(0)
    meta["citation_bag"] = json.dumps(bag)
    if not bag:
        meta["citation_tour"] = "1"                          # la dernière du tour est affichée : le bouton IA se débloque
    _apply(meta, by[k])
    return status(meta)


def prev_quote(meta):
    hist = _hist(meta)
    if not hist:
        return status(meta)
    t, a, ia = hist.pop()
    meta["citation_hist"] = json.dumps(hist, ensure_ascii=False)
    _apply(meta, (t, a, ia == "1"))
    return status(meta)


def set_custom(meta, texte, auteur):
    texte = (texte or "").strip()
    if not texte:
        meta.pop("citation", None)
        meta.pop("citation_auteur", None)
        meta.pop("citation_ia", None)
        return status(meta)
    meta["citation"], meta["citation_auteur"], meta["citation_ia"] = texte[:300], (auteur or "").strip()[:80], "0"
    meta.pop("citation_off", None)
    return status(meta)


def set_off(meta, off=True):
    if off:
        meta["citation_off"] = "1"
    else:
        meta.pop("citation_off", None)
    return status(meta)


# ---------------------------------------------------------------- IA
SYSTEM = (
    "Tu aides une librairie à choisir la citation de sa 4e de couverture. Tu proposes uniquement de VRAIES citations, "
    "de vrais auteurs, sur la lecture, les livres, les bibliothèques ou les librairies. Si tu n'es pas certain qu'une citation "
    "existe et qu'elle est bien de cet auteur, ne la propose pas : mieux vaut en donner moins. Pas de proverbe sans origine, "
    "pas de citation inventée ou paraphrasée. En français (traduction courante si l'original est étranger), 200 caractères maximum. "
    "Réponds uniquement par un tableau JSON : [{\"t\": \"citation\", \"a\": \"Auteur\"}, ...]"
)


def ia_available(meta):
    s = status(meta)
    if not s["tour_fait"]:
        return False, "Le bouton IA se débloque quand tu as fait le tour des citations."
    if s["ia_occupe"]:
        return False, "Une demande est déjà en cours."
    if s["ia_attente"]:
        return False, f"Patiente encore {s['ia_attente']} s."
    if s["ia_restant"] <= 0:
        return False, f"Limite de {AI_PER_DAY} demandes par jour atteinte (les citations déjà reçues restent disponibles)."
    return True, ""


def _parse(txt):
    m = re.search(r"\[.*\]", txt, re.S)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except Exception:
        return []
    out = []
    for q in arr if isinstance(arr, list) else []:
        if isinstance(q, dict):
            t = re.sub(r"\s+", " ", str(q.get("t") or "")).strip().strip("«»\" ")
            a = re.sub(r"\s+", " ", str(q.get("a") or "")).strip()
            if 12 <= len(t) <= MAX_LEN and 2 <= len(a) <= 60:
                out.append((t, a))
    return out


def fetch_ai(meta, key, call=None):
    """Demande AI_BATCH citations à Haiku, les enregistre. Retourne (nombre ajoutées, statut). Lève ai.AIError."""
    ok, why = ia_available(meta)
    if not ok:
        raise ai.AIError(why)
    if not key:
        raise ai.AIError("pas de clé Claude (Réglages)")
    with LOCK:
        if AI_STATE["busy"]:
            raise ai.AIError("Une demande est déjà en cours.")
        AI_STATE["busy"] = True
    try:
        known = pool()
        auteurs = sorted({q[1] for q in known})
        prompt = (f"Propose {AI_BATCH} citations différentes. Évite celles-ci (déjà connues) et varie les auteurs et les époques.\n"
                  f"Auteurs déjà utilisés : {' ; '.join(auteurs)[:900]}")
        txt = ""
        last = ""
        for model in ai.MODELS:
            try:
                j = (call or ai_post)(key, model, prompt)
                usage.record("citations", model, j.get("usage"))
                txt = "".join(c.get("text", "") for c in j.get("content", []) if c.get("type") == "text")
                break
            except urllib.error.HTTPError as e:
                msg = ai._error_text(e)
                if e.code == 401:
                    raise ai.AIError("clé Claude refusée (vérifie-la dans les Réglages)")
                if e.code == 402 or "credit balance" in msg.lower():
                    raise ai.AIError("plus de crédit sur ton compte Claude (console.anthropic.com → Billing)")
                last = f"service Claude indisponible ({e.code})"
            except Exception as e:
                last = "connexion impossible : " + str(e)
                break
        AI_STATE["last"] = time.time()                       # le délai court même en cas d'échec : pas de rafale
        if not txt:
            raise ai.AIError(last or "réponse vide")
        have = {_key(q) for q in known}
        new = []
        for t, a in _parse(txt):
            if _norm(t) not in have:
                have.add(_norm(t))
                new.append({"t": t, "a": a})
        d = _load_ia()
        today = time.strftime("%Y-%m-%d")
        d["day_count"] = (d.get("day_count", 0) if d.get("day") == today else 0) + 1
        d["day"] = today
        d["quotes"] = d.get("quotes", []) + new
        _save_ia(d)
        if new:                                              # elles rejoignent le tirage : on repart pour un nouveau tour
            meta["citation_bag"] = json.dumps(sorted({_norm(q["t"]) for q in new}))
            meta["citation_tour"] = "0"
        return len(new)
    finally:
        AI_STATE["busy"] = False


def ai_post(key, model, prompt):
    return ai.post_json(key, model, SYSTEM, prompt, 1500)
