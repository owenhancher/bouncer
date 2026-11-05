"""License classification. Only free-reuse, commercial-OK, derivative-OK licenses may be clipped/reposted."""
from __future__ import annotations

import re
from typing import Optional, Tuple

# code -> (human label, attribution required)
ALLOWED = {
    "CC0": ("CC0 (public domain dedication)", False),
    "PD": ("Public domain", False),
    "CC-BY": ("CC BY", True),
    "CC-BY-SA": ("CC BY-SA", True),
    "PEXELS": ("Pexels License", False),
    "PIXABAY": ("Pixabay Content License", False),
    "OWN": ("Bouncer original footage", False),
}
BLOCKED_HINT = "NonCommercial (NC), NoDerivatives (ND), standard/all-rights-reserved and unknown licenses are refused"


def classify(text: Optional[str], url: Optional[str] = None) -> Tuple[str, bool]:
    """Return (code, allowed). Unknown/blank -> ("UNKNOWN", False)."""
    raw = f"{text or ''} {url or ''}".strip()
    t = raw.lower()
    if not t:
        return "UNKNOWN", False
    if t.strip().upper() in ALLOWED:
        code = t.strip().upper()
        return code, True
    # Any NC / ND component disqualifies (check first: "by-nc-sa" contains "by").
    if re.search(r"(\bnc\b|-nc\b|-nc-|noncommercial|non-commercial|/by-nc)", t) or \
       re.search(r"(\bnd\b|-nd\b|-nd-|noderiv|no deriv|/by-nd)", t):
        return "NC-OR-ND", False
    if "pexels" in t:
        return "PEXELS", True
    if "pixabay" in t:
        return "PIXABAY", True
    if "cc0" in t or "publicdomain/zero" in t or "cc-zero" in t:
        return "CC0", True
    if "public domain" in t or "publicdomain/mark" in t or re.search(r"\bpd\b|pd-", t):
        return "PD", True
    if "by-sa" in t or "attribution-sharealike" in t or "attribution share alike" in t or "cc-by-sa" in t:
        return "CC-BY-SA", True
    # YouTube's flag reads "Creative Commons Attribution license (reuse allowed)" -> CC BY 3.0
    if "licenses/by/" in t or "cc-by" in t or "cc by" in t or "creative commons attribution" in t:
        return "CC-BY", True
    if "creative commons" in t:  # CC without a recognisable variant: don't guess
        return "CC-UNSPECIFIED", False
    return "UNKNOWN", False


def is_allowed(code: Optional[str]) -> bool:
    return (code or "").upper() in ALLOWED


def label(code: Optional[str], name: Optional[str] = None) -> str:
    c = (code or "").upper()
    if c in ALLOWED:
        return ALLOWED[c][0]
    return name or c or "Unknown license"


def attribution(creator: Optional[str], code: Optional[str], source_url: Optional[str] = None,
                license_name: Optional[str] = None) -> str:
    """Attribution line auto-appended to every caption, e.g. 'Video: Jane Doe / CC BY · <url>'."""
    who = (creator or "Unknown creator").strip()
    lic = license_name.split(" (")[0] if (license_name and (code or "").upper() in {"CC-BY", "CC-BY-SA"}) else label(code)
    if (code or "").upper() == "OWN":
        return "Video: Bouncer Travel"
    line = f"Video: {who} / {lic}"
    c = (code or "").upper()
    if c in {"CC-BY", "CC-BY-SA"}:
        line += ", edited"  # CC requires indicating changes; BY-SA clips are shared under the same license
    if c == "CC-BY-SA":
        line += " (clip CC BY-SA)"
    if source_url:
        line += f" · {source_url}"
    return line
