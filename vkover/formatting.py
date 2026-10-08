"""HTML to VK format_data converter for messages."""

import re

_TAGS = {
    "b": "bold",
    "strong": "bold",
    "i": "italic",
    "em": "italic",
    "u": "underline",
    "ins": "underline",
    "s": "strike",
    "strike": "strike",
    "del": "strike",
    "spoiler": "spoiler",
}

_TAG_RE = re.compile(
    r"<(/?)(b|strong|i|em|u|ins|s|strike|del|spoiler|a|code|pre)\b([^>]*)>",
    re.IGNORECASE,
)
_ATTR_RE = re.compile(r'href\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)


def html_to_format_data(html: str) -> tuple[str, dict | None]:
    """Convert simple HTML to (plain_text, format_data).

    Supported: b/strong, i/em, u/ins, s/strike/del, spoiler,
    a href (url). Code/pre are stripped to plain text.
    """
    text_parts: list[str] = []
    entities: list[dict] = []
    stack: list[tuple[str, int, str]] = []

    pos = 0
    for m in _TAG_RE.finditer(html):
        text_parts.append(html[pos:m.start()])
        pos = m.end()

        closing, tag, attrs = m.group(1), m.group(2).lower(), m.group(3)
        if closing:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == tag:
                    name, start, url = stack.pop(i)
                    entities.append({
                        "offset": start,
                        "length": len("".join(text_parts)) - start,
                        "type": "url" if name == "a" else _TAGS[name],
                        "url": url,
                    })
                    if tag == "a":
                        break
                    if name == "a":
                        continue
                    break
        elif tag == "a":
            href = _ATTR_RE.search(attrs)
            stack.append((tag, len("".join(text_parts)), href.group(1) if href else ""))
        elif tag in ("code", "pre"):
            pass
        elif tag in _TAGS:
            stack.append((tag, len("".join(text_parts)), ""))

    text_parts.append(html[pos:])
    text = "".join(text_parts)
    text = re.sub(r"</?(?:code|pre)[^>]*>", "", text, flags=re.IGNORECASE)

    if not entities:
        return text, None
    return text, {"version": "1", "items": entities}
