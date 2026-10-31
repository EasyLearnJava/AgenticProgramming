"""
IT Knowledge Base: Find and Redact Sensitive Data
=================================================

Finds sensitive values in a text and replaces them, so they're never printed, logged or kept. It handles:
  1. Secrets: passwords and keys written as `name: value`, passwords inside URLs, AWS and Google keys, GitHub
     tokens, JSON web tokens and private keys
  2. PCI: payment card numbers (checked with the Luhn algorithm, so other long numbers aren't caught)
  3. PII: email addresses, US Social Security numbers and phone numbers

    redact("Call 555-010-0142")  ->  ("Call [REDACTED:PHONE]", [Finding("phone number", "PII", "***-***-0142")])

A Finding never holds the value itself: only its kind, its category and a masked form that's safe to show.
"""
import re
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    """One sensitive value found: what it is, and a masked form that's safe to show."""
    kind: str        # e.g. "card number"
    category: str    # "secret", "PCI" or "PII"
    masked: str      # e.g. "**** 1111"


def luhn_ok(value: str) -> bool:
    """True for 13 to 19 digits that pass the Luhn check, as every payment card number does."""
    digits = [int(char) for char in value if char.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for place, digit in enumerate(reversed(digits)):
        if place % 2:
            digit = digit * 2 - 9 if digit > 4 else digit * 2
        total += digit
    return total % 10 == 0


def last4(value: str) -> str:
    return re.sub(r"\D", "", value)[-4:]


def hidden(value: str) -> str:
    """A secret is never shown, not even in part: only its length."""
    return f"(hidden, {len(value)} characters)"


def mask_email(value: str) -> str:
    name, domain = value.split("@", 1)
    return f"{name[0]}***@{domain}"


@dataclass(frozen=True)
class Detector:
    kind: str
    category: str
    label: str                                   # the text gets [REDACTED:<label>] in place of the value
    pattern: re.Pattern
    mask: Callable[[str], str]
    check: Callable[[str], bool] = lambda value: True
    group: int = 0                               # the part of a match that's the value (0: all of it)


# In this order: secrets first, then cards before phone numbers, so each value is caught by the right detector
DETECTORS = [
    Detector("private key", "secret", "PRIVATE_KEY",
             re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S), hidden),
    Detector("password in a URL", "secret", "PASSWORD",
             re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/@]+:([^\s@/]+)@", re.I), hidden, group=1),
    Detector("AWS access key", "secret", "AWS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}(?![0-9A-Za-z])"), hidden),
    Detector("Google API key", "secret", "GOOGLE_KEY", re.compile(r"\bAIza[0-9A-Za-z_-]{35}(?![0-9A-Za-z_-])"), hidden),
    Detector("GitHub token", "secret", "GITHUB_TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}"), hidden),
    Detector("JSON web token", "secret", "TOKEN",
             re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), hidden),
    Detector("password or key", "secret", "SECRET",
             re.compile(r"(?i)\b(?:password|passwd|pwd|passcode|secret|api[_ -]?key|access[_ -]?key|token)\s*[:=]\s*"
                        r"([^\s,;]+)"), hidden, group=1),
    Detector("card number", "PCI", "CARD", re.compile(r"(?<![\d-])\d(?:[ -]?\d){12,18}(?![\d-])"),
             lambda value: "**** " + last4(value), check=luhn_ok),
    Detector("Social Security number", "PII", "SSN", re.compile(r"(?<![\d-])\d{3}-\d{2}-\d{4}(?![\d-])"),
             lambda value: "***-**-" + last4(value)),
    Detector("email address", "PII", "EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
             mask_email),
    Detector("phone number", "PII", "PHONE",
             re.compile(r"(?<![\w-])(?:\+?1[ .-]?)?(?:\(\d{3}\) ?|\d{3}[ .-])\d{3}[ .-]\d{4}(?![\w-])"),
             lambda value: "***-***-" + last4(value)),
]


def redact(text: str) -> tuple[str, list[Finding]]:
    """The text with every sensitive value replaced by [REDACTED:<label>], and what was found."""
    findings: list[Finding] = []
    for detector in DETECTORS:
        def replace(match: re.Match, detector: Detector = detector) -> str:
            value = match.group(detector.group)
            if not detector.check(value):
                return match.group(0)
            findings.append(Finding(detector.kind, detector.category, detector.mask(value)))
            start, end = match.start(detector.group) - match.start(), match.end(detector.group) - match.start()
            return match.group(0)[:start] + f"[REDACTED:{detector.label}]" + match.group(0)[end:]
        text = detector.pattern.sub(replace, text)
    return text, findings
