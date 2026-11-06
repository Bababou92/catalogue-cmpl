"""Lance le serveur avec de fausses réponses Google/BnF (pour les tests d'interface)."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("CMPL_CAT_DATA_DIR", tempfile.mkdtemp())
import fakenet
from catalogue import ai, citations, net, sources, server
sources.http_get = fakenet.http_get


def fake_claude(key, model, prompt, max_tokens=400):
    import time; time.sleep(0.2)
    t = prompt.split("\n")[0].replace("Titre : ", "")
    return {"content": [{"type": "text", "text": "Description simulée de « %s » : un ouvrage de référence qui présente clairement les notions essentielles, avec des exemples et des exercices pour s'entraîner. " % t * 2}]}


ai._post = fake_claude


def fake_quotes(key, model, prompt):
    import json, time; time.sleep(0.3)
    n = len(citations._load_ia().get("quotes", []))
    return {"content": [{"type": "text", "text": json.dumps([{"t": "Citation simulée numéro %d pour les essais." % (n + i), "a": "Auteur %d" % (n + i)} for i in range(12)])}]}


citations.ai_post = fake_quotes
citations.AI_COOLDOWN = 3.0
_flag = os.environ.get("CMPL_FAKE_OFFLINE_FILE")
if _flag:                                              # essais : le fichier existe = pas d'internet
    net.online = lambda force=False: not os.path.exists(_flag)
server.main(open_browser=False)
