"""Lance le serveur avec de fausses réponses Google/BnF (pour les tests d'interface)."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("CMPL_CAT_DATA_DIR", tempfile.mkdtemp())
import fakenet
from catalogue import ai, sources, server
sources.http_get = fakenet.http_get


def fake_claude(key, model, prompt, max_tokens=400):
    import time; time.sleep(0.2)
    t = prompt.split("\n")[0].replace("Titre : ", "")
    return {"content": [{"type": "text", "text": "Description simulée de « %s » : un ouvrage de référence qui présente clairement les notions essentielles, avec des exemples et des exercices pour s'entraîner. " % t * 2}]}


ai._post = fake_claude
server.main(open_browser=False)
