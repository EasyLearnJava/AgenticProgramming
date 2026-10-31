"""
Tests for sensitive_data.py: each kind of sensitive value is found, replaced in the text and reported only masked,
and ordinary IT text (dates, ports, error codes, the sample articles) is left alone.

The keys below are built from pieces, so this file never holds a whole key that a secret scanner would flag.
Run them:   python -m pytest tests/test_sensitive_data.py
"""
import csv

import pytest

from knowledge_base_loader import KB_FILE
from sensitive_data import luhn_ok, redact

AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"
GOOGLE_KEY = "AIza" + "Sy" + "A1b2C3d4" * 4 + "x"
GITHUB_TOKEN = "ghp_" + "a1B2c3D4" * 5
JWT = "eyJ" + "hbGciOiJIUzI1" + ".eyJ" + "zdWIiOiIxMjM0" + ".SflKxwRJSMeKKF2QT4"
PRIVATE_KEY = "-----BEGIN RSA " + "PRIVATE KEY-----\nMIIEow\n-----END RSA " + "PRIVATE KEY-----"


@pytest.mark.parametrize("text, redacted, kind, category, masked", [
    ("Call jane.doe@example.com today", "Call [REDACTED:EMAIL] today", "email address", "PII", "j***@example.com"),
    ("Ring 555-010-0142 now", "Ring [REDACTED:PHONE] now", "phone number", "PII", "***-***-0142"),
    ("Ring (555) 010-0199", "Ring [REDACTED:PHONE]", "phone number", "PII", "***-***-0199"),
    ("SSN 123-45-6789 given", "SSN [REDACTED:SSN] given", "Social Security number", "PII", "***-**-6789"),
    ("Card 4111 1111 1111 1111.", "Card [REDACTED:CARD].", "card number", "PCI", "**** 1111"),
    ("Card 4111-1111-1111-1111", "Card [REDACTED:CARD]", "card number", "PCI", "**** 1111"),
    ("password: Winter2026! now", "password: [REDACTED:SECRET] now", "password or key", "secret",
     "(hidden, 11 characters)"),
    ("api_key=zX9q", "api_key=[REDACTED:SECRET]", "password or key", "secret", "(hidden, 4 characters)"),
    ("db postgres://app:S3cr3t@db01/kb", "db postgres://app:[REDACTED:PASSWORD]@db01/kb", "password in a URL", "secret",
     "(hidden, 6 characters)"),
    (f"key {AWS_KEY}", "key [REDACTED:AWS_KEY]", "AWS access key", "secret", "(hidden, 20 characters)"),
    (f"key {GOOGLE_KEY}", "key [REDACTED:GOOGLE_KEY]", "Google API key", "secret", "(hidden, 39 characters)"),
    (f"token {GITHUB_TOKEN}", "token [REDACTED:GITHUB_TOKEN]", "GitHub token", "secret", "(hidden, 44 characters)"),
    (f"header {JWT}", "header [REDACTED:TOKEN]", "JSON web token", "secret", "(hidden, 52 characters)"),
    (f"{PRIVATE_KEY} end", "[REDACTED:PRIVATE_KEY] end", "private key", "secret", "(hidden, 68 characters)"),
])
def test_each_kind_is_found_redacted_and_masked(text, redacted, kind, category, masked):
    out, findings = redact(text)
    assert out == redacted
    assert [(found.kind, found.category, found.masked) for found in findings] == [(kind, category, masked)]


@pytest.mark.parametrize("text", [
    "UDP ports 500 and 4500",
    "Error 0x80070005 on build 10.0.19045",
    "Raised on 2024-01-15 at 10:30",
    "Ticket 1234567890123 (13 digits, but not a card number)",
    "Card 4111 1111 1111 1112 fails the Luhn check",
    "Reset password through the portal; the new password meets the rules",
])
def test_ordinary_it_text_is_left_alone(text):
    assert redact(text) == (text, [])


def test_the_sample_articles_have_no_sensitive_values():
    with open(KB_FILE, encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            for value in row.values():
                assert redact(value) == (value, [])


def test_a_finding_never_holds_the_value():
    for text, value in [("password: Winter2026!", "Winter2026!"), ("Card 4111 1111 1111 1111", "4111 1111 1111 1111"),
                        (f"key {AWS_KEY}", AWS_KEY), ("SSN 123-45-6789", "123-45-6789")]:
        _, findings = redact(text)
        assert value not in repr(findings)


def test_the_luhn_check():
    assert luhn_ok("4111 1111 1111 1111")
    assert luhn_ok("5500-0000-0000-0004")
    assert not luhn_ok("4111 1111 1111 1112")
    assert not luhn_ok("4111")                 # too short to be a card
