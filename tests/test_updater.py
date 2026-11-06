"""Mise à jour automatique : serveur local simulant GitHub Releases."""
import hashlib, http.server, json, os, sys, tempfile, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
d = tempfile.mkdtemp()
new = b"MZ" + os.urandom(5000)
open(os.path.join(d, "new.exe"), "wb").write(new)
feed = {"version": "9.9.9", "url": "", "sha256": hashlib.sha256(new).hexdigest(), "size": len(new), "notes": "Nouveautés de test"}


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=d, **k)

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
feed["url"] = f"http://127.0.0.1:{port}/new.exe"
json.dump(feed, open(os.path.join(d, "latest.json"), "w"))
target = os.path.join(tempfile.mkdtemp(), "Catalogue-CMPL.exe"); open(target, "wb").write(b"MZold")
os.environ.update(CMPL_UPDATE_URL=f"http://127.0.0.1:{port}/latest.json", CMPL_UPDATE_TARGET=target, CMPL_UPDATE_NOSPAWN="1")
from catalogue import updater


def wait(states, t=10):
    t0 = time.time()
    while updater.STATE["state"] not in states and time.time() - t0 < t:
        time.sleep(0.05)
    return updater.STATE["state"]


updater.check(); assert updater.STATE["state"] == "available" and updater.STATE["latest"]["version"] == "9.9.9"
assert updater.status()["can_apply"] and updater.status()["notes"] == "Nouveautés de test"
updater.start_download(); assert wait(("ready", "error")) == "ready", updater.STATE
updater.apply(); assert open(target, "rb").read() == new and os.path.exists(target + ".old")
updater.cleanup_old(); assert not os.path.exists(target + ".old")
# empreinte incorrecte -> refus, rien d'installé
feed["sha256"] = "0" * 64; json.dump(feed, open(os.path.join(d, "latest.json"), "w"))
updater._set(state="idle"); updater.check(); updater.start_download()
assert wait(("ready", "error")) == "error" and "corrompu" in updater.STATE["error"] and not os.path.exists(target + ".new")
# version plus ancienne -> rien à faire
feed["version"] = "0.0.1"; json.dump(feed, open(os.path.join(d, "latest.json"), "w"))
updater._set(state="idle"); updater.check(); assert updater.STATE["state"] == "none"
print("OK updater")
