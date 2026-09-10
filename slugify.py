import re, unicodedata
def make_slug(value, extra=0):
    value = unicodedata.normalize("NFKD", value).encode("ascii","ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+","-",value).strip("-")
    return f"{slug}-{extra}" if extra else slug
