"""urlopen with a fallback CA bundle: Windows' certificate store sometimes lacks
an intermediate certificate until something else has fetched it, which makes
Python report CERTIFICATE_VERIFY_FAILED for perfectly valid sites."""
import ssl
import urllib.error
import urllib.request

_fallback = None


def _certifi_context():
    global _fallback
    if _fallback is None:
        try:
            import certifi  # noqa: PLC0415 - optional
            _fallback = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            _fallback = False
    return _fallback


def urlopen(req, timeout=30):
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.URLError as e:
        ctx = _certifi_context()
        if ctx and isinstance(getattr(e, "reason", None), ssl.SSLCertVerificationError):
            return urllib.request.urlopen(req, timeout=timeout, context=ctx)
        raise
