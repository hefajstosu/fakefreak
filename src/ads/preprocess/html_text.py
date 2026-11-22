"""Visible text of an HTML page (saved file, HAR body or live response), without scripts, styles and picklists."""
import html as htmllib
import re

MAX_TEXT = 40000
# Long phone-country picklists in sign-up widgets ("Afghanistan +93 Albania +355 ...") are noise.
PICKLIST = re.compile(r"(?:[A-ZÅÇ][^\s+]*(?: [^\s+]+){0,3} \+\d{1,4}\s+){8,}")


def html_to_text(path: str) -> str:
    return html_str_to_text(open(path, encoding="utf-8", errors="ignore").read())


def html_str_to_text(s: str) -> str:
    s = re.sub(r"(?is)<!--.*?-->", "", s)
    s = re.sub(r"(?is)<(script|style|noscript|svg|head|template)[^>]*>.*?</\1>", "", s)
    s = re.sub(r"(?i)</(p|div|li|h\d|tr|section|article)>|<br\s*/?>", "\n", s)
    t = htmllib.unescape(re.sub(r"<[^>]+>", " ", s))
    lines = [re.sub(r"[ \t\xa0]+", " ", ln).strip() for ln in t.split("\n")]
    text = "\n".join(ln for ln in lines if ln)
    text = PICKLIST.sub(" ", text)
    return text[:MAX_TEXT].strip()
