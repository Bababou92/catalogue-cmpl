"""Lance le serveur avec de fausses réponses Google/BnF (pour les tests d'interface)."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("CMPL_CAT_DATA_DIR", tempfile.mkdtemp())
import fakenet
from catalogue import sources, server
sources.http_get = fakenet.http_get
server.main(open_browser=False)
