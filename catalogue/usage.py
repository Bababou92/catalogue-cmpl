"""Indicateur de consommation de l'IA : appels et jetons comptés sur ce PC, avec une estimation du coût.

Il s'agit d'une estimation : le programme ne voit pas le solde réel du compte Anthropic (la console fait foi).
Aucune limite n'est imposée. Les montants sont en dollars, comme sur la console Anthropic."""
import json
import os
import threading
import time

from . import store

# dollars par million de jetons (entrée, sortie), tarifs publics d'Anthropic (prompts de moins de 100 000 jetons)
RATES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00)}
DEFAULT_RATE = (2.00, 10.00)                       # modèle inconnu : on prend le tarif le plus haut (estimation prudente)
# consommation moyenne d'un appel tant qu'on n'a pas d'historique : (jetons en entrée, jetons en sortie)
TYPICAL = {"descriptions": (1100, 190), "citations": (650, 700)}      # réflexion désactivée
_lock = threading.Lock()


def _path():
    return os.path.join(store.data_dir(), "usage_ia.json")


def _load():
    try:
        with open(_path(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(d):
    tmp = _path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _path())


def cost_of(model, tin, tout):
    rin, rout = RATES.get(model, DEFAULT_RATE)
    return tin / 1e6 * rin + tout / 1e6 * rout


def _add(box, kind, tin, tout, cost):
    box["calls"] = box.get("calls", 0) + 1
    box["in"] = box.get("in", 0) + tin
    box["out"] = box.get("out", 0) + tout
    box["cost"] = round(box.get("cost", 0.0) + cost, 8)
    k = box.setdefault("kinds2", {}).setdefault(kind, {"calls": 0, "in": 0, "out": 0})
    k["calls"] += 1
    k["in"] += tin
    k["out"] += tout


def record(kind, model, usage):
    """Note un appel à Claude. `usage` = champ « usage » de la réponse ({input_tokens, output_tokens}). Sans effet s'il est absent."""
    if not isinstance(usage, dict):
        return
    try:
        tin, tout = int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)
    except (TypeError, ValueError):
        return
    if tin <= 0 and tout <= 0:
        return
    c = cost_of(model, tin, tout)
    with _lock:
        d = _load()
        _add(d.setdefault("months", {}).setdefault(time.strftime("%Y-%m"), {}), kind, tin, tout, c)
        _add(d.setdefault("total", {}), kind, tin, tout, c)
        try:
            _save(d)
        except OSError:
            pass


def summary():
    with _lock:
        d = _load()
    m = d.get("months", {}).get(time.strftime("%Y-%m"), {})
    t = d.get("total", {})
    pick = lambda b: {"calls": b.get("calls", 0), "in": b.get("in", 0), "out": b.get("out", 0), "cost": round(b.get("cost", 0.0), 4)}
    return {"mois": pick(m), "total": pick(t)}


def estimate(kind, n, model="claude-haiku-5-5"):
    """Coût estimé de n appels : moyenne observée sur ce PC pour ce type d'appel, sinon valeurs typiques."""
    with _lock:
        k = _load().get("total", {}).get("kinds2", {}).get(kind) or {}
    if k.get("calls", 0) >= 5:
        tin, tout = k["in"] / k["calls"], k["out"] / k["calls"]
    else:
        tin, tout = TYPICAL.get(kind, (1000, 300))
    return round(cost_of(model, tin * n, tout * n), 4)
