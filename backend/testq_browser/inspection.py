"""DOM inspection is read-only: no clicks, submissions, or input values."""
from pathlib import Path
from urllib.parse import urljoin
from .schemas import Element, Form, Link
from .policies import redact, safe_url, same_origin, selectors

SCRIPT = Path(__file__).with_name("inspect.js").read_text(encoding="utf-8-sig")


def resolve_href(base, href):
    try:
        return urljoin(base, href or "")
    except ValueError:
        return "invalid:"


def element(data):
    candidates = selectors(data)
    return Element(**{key: ([redact(x, 500) for x in value] if isinstance(value, list) else
                            redact(value, 500) if isinstance(value, str) else value)
                      for key, value in data.items() if key not in {"test_id", "css"}}, selectors=candidates)


async def inspect_page(page, record, base_url, limit):
    result = await page.evaluate(SCRIPT, limit)
    record.title = redact(await page.title(), 500)
    record.links = [Link(href=safe_url(resolve_href(page.url, item["href"])), text=redact(item["text"],500),
                        source_page=record.url, internal=same_origin(resolve_href(page.url,item["href"]),base_url))
                    for item in result["links"][:limit]]
    record.buttons = [element(item) for item in result["buttons"][:limit]]
    record.inputs = [element(item) for item in result["inputs"][:limit]]
    record.forms = [Form(identifier=redact(item["identifier"],500), action=safe_url(resolve_href(page.url,item["action"])),
                         method=item["method"], controls=[element(x) for x in item["controls"][:limit]],
                         buttons=[element(x) for x in item["buttons"][:limit]]) for item in result["forms"][:25]]
    return result["links"][:limit]
