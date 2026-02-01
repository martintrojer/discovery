"""Shared regex patterns for Discovery."""

from __future__ import annotations

import re

EDITION_PATTERNS = [
    r"\s*\(.*?(edition|remaster|deluxe|version|expanded).*?\)\s*$",
    r"\s*-\s*.*?(edition|remaster|deluxe|version|expanded).*$",
    r"\s*:\s*.*?(edition|remaster|deluxe|version|expanded).*$",
    r"\s+\(remastered\)\s*$",
    r"\s+\(deluxe\)\s*$",
]

ROMAN_NUMERAL_SUFFIX_RE = re.compile(r"\s+[ivxlcdm]+$", re.IGNORECASE)
DIGIT_SUFFIX_RE = re.compile(r"\s+\d+$")

NETFLIX_ROW_RE = re.compile(r'<li class="retableRow">(.*?)</li>', re.S)
NETFLIX_DATE_RE = re.compile(r'<div class="col date nowrap">(.*?)</div>')
NETFLIX_TITLE_RE = re.compile(r'<div class="col title">\s*<a href="[^"]+">(.*?)</a>')
NETFLIX_RATED_RE = re.compile(r'aria-label="Already rated: (.*?)\(click to remove rating\)"')
