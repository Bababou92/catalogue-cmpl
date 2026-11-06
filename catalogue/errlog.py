"""Petit journal d'erreurs gardé en mémoire (80 dernières entrées) pour le rapport « Signaler un problème »."""
import collections
import threading
import time
import traceback

_LOG = collections.deque(maxlen=80)
_lock = threading.Lock()


def record(where, exc=None, text=None):
    """Note une erreur. exc = exception (traceback complet) ou text = message libre."""
    if exc is not None:
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
    else:
        detail = str(text or "")
    with _lock:
        _LOG.append({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "where": where, "detail": detail})


def last():
    with _lock:
        return dict(_LOG[-1]) if _LOG else None


def dump(n=40):
    with _lock:
        items = list(_LOG)[-n:]
    return "\n\n".join(f"[{i['time']}] {i['where']}\n{i['detail']}" for i in items) or "(aucune erreur enregistrée)"


def install_thread_hook():
    """Les erreurs dans les tâches de fond (lot Excel…) sont aussi notées."""
    def hook(args):
        record("tâche de fond " + (args.thread.name if args.thread else ""), args.exc_value)
    threading.excepthook = hook
