import hashlib
import json
from contextlib import contextmanager

from django.conf import settings
from filelock import FileLock, Timeout
from routes.exceptions import ProviderError


def cache_key(prefix: str, value: object) -> str:
    return prefix + ":" + hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


@contextmanager
def request_lock(key: str):
    """Cross-thread/process protection on a single application host."""
    settings.LOCK_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(
            str(settings.LOCK_DIR / (cache_key("lock", key).replace(":", "_") + ".lock")), timeout=40
        ):
            yield
    except Timeout as exc:
        raise ProviderError("Mapping service is busy; please retry.") from exc
