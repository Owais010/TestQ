"""URL, privacy, selector and bounded frontier policies (no browser dependency)."""
import re
from collections import deque
from urllib.parse import urlsplit, urlunsplit, urljoin, unquote, quote
from .schemas import SelectorCandidate

SECRET = re.compile(r'''(?i)(["']?(?:authorization|cookie|set-cookie|password|passwd|token|access_token|refresh_token|api[-_]?key|secret)["']?\s*[:=]\s*)["']?[^\s,;"'}]+''')
JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")


def redact(text: str, limit=4000):
    text = re.sub(r"(?i)Bearer\s+[^\s\"']+", "Bearer [REDACTED]", str(text))
    text = SECRET.sub(r"\1[REDACTED]", text)
    text = JWT.sub("[REDACTED]", text)
    text = re.sub(r"https?://[^\s<>\"']+", lambda m: safe_url(m.group()), text)
    return text[:limit]


def origin(url):
    try:
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            return None
        return (parsed.scheme.lower(), parsed.hostname.lower(), parsed.port or (443 if parsed.scheme.lower() == "https" else 80))
    except ValueError:
        return None


def same_origin(url, base):
    return origin(url) is not None and origin(url) == origin(base)


def safe_url(url):
    """Evidence URLs contain no credentials, query strings or fragment values."""
    try:
        parsed = urlsplit(url)
        if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
            return parsed.scheme.lower() + ":"
        host = parsed.hostname or ""
        port = parsed.port
        host = f"[{host}]" if ":" in host else host
        default_port = 443 if parsed.scheme.lower() == "https" else 80
        netloc = host + (f":{port}" if port and port != default_port else "")
        # Redact common credentials embedded in path segments as well.
        path = re.sub(r"(?i)(/(?:token|secret|api[-_]?key|password)/)[^/]+", r"\1[REDACTED]", parsed.path)
        return urlunsplit((parsed.scheme.lower(), netloc, path or "/", "", ""))[:2000]
    except ValueError:
        return "[invalid URL]"


def normalize_url(href, base):
    """V1 crawls paths, not query/fragment variants; never credentialled URLs."""
    if not isinstance(href, str) or len(href) > 4096 or any(ord(c) < 32 for c in href) or "\\" in href:
        return None
    try:
        absolute = urljoin(base, href.strip())
    except ValueError:
        return None
    if not same_origin(absolute, base):
        return None
    parsed = urlsplit(absolute)
    # Decode only unreserved characters; never turn encoded '/' into a new route.
    path = re.sub(r"%([0-9a-fA-F]{2})", lambda m: chr(int(m[1], 16)) if chr(int(m[1], 16)) in
                  "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~" else m[0].upper(), parsed.path)
    parts = []
    for part in path.split("/"):
        if part == "..":
            if parts: parts.pop()
        elif part and part != ".":
            parts.append(part)
    path = "/" + "/".join(parts)
    if parsed.path.endswith("/") and path != "/":
        path += "/"
    return urlunsplit((origin(base)[0], urlsplit(base).netloc.lower(), path, "", ""))


class Frontier:
    def __init__(self, base, max_pages, max_depth):
        self.base, self.max_pages, self.max_depth = base, max_pages, max_depth
        self.queue, self.seen = deque(), set()
        self.limited = False
        self.add("/", 0, base)

    def add(self, href, depth, source):
        url = normalize_url(href, source)
        if not url or not same_origin(url, self.base) or url in self.seen:
            return False
        if depth > self.max_depth or len(self.seen) >= self.max_pages:
            self.limited = True
            return False
        self.seen.add(url)
        self.queue.append((url, depth))
        return True


def selectors(data):
    result = []
    def add(strategy, value, role=None):
        if value and len(value) <= 1000:
            result.append(SelectorCandidate(strategy=strategy, value=redact(value, 1000), role=role))
    add("test_id", data.get("test_id"))
    if data.get("role") and data.get("accessible_name"):
        add("role", data["accessible_name"], data["role"])
    add("id", data.get("element_id"))
    add("name", data.get("name"))
    if data.get("placeholder"):
        add("attribute", "placeholder=" + data["placeholder"])
    add("css", data.get("css"))
    return result
