"""Deterministic evidence checks for monetary and inventory claims in the English travel evaluation."""

import re
from decimal import Decimal

from nimbus.travel.models import TravelOffer, TravelReport
from tools.evals import to_text

AMOUNT = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
ISO = "USD|CAD|EUR|GBP|JPY|AUD|CHF|CNY|INR|MXN|BRL|NZD|KRW|SGD|HKD|ZAR|AED|NOK|SEK|DKK|PLN"
UNIT = rf"{ISO}|US\$|CA\$|\$|£|€|¥|₹"
MONEY = re.compile(
    rf"(?P<prefix>{UNIT})\s*(?P<number>{AMOUNT})(?:\s+(?P<echo>{ISO})\b)?"
    rf"|(?P<value>{AMOUNT})\s*(?P<suffix>{UNIT}|dollars?|euros?|pounds?)",
    re.I,
)
CURRENCIES = {
    "$": "USD",
    "US$": "USD",
    "CA$": "CAD",
    "€": "EUR",
    "₹": "INR",
    "£": "GBP",
    "DOLLAR": "USD",
    "EURO": "EUR",
    "POUND": "GBP",
}
# Spelled-out values are outside our numeric comparison. Flag them for review instead of silently passing.
WRITTEN_MONEY = re.compile(
    r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|teen|ty|hundred|thousand|million)"
    r"\s+(?:US\s+)?(?:dollars?|euros?|pounds?)\b|\b\w+(?:teen|ty)\s+(?:dollars?|euros?|pounds?)\b",
    re.I,
)
BASIS = re.compile(
    r"(?P<per_night>\bnightly\b|(?:per|a|each|/)\s*night\b)|"
    r"(?P<per_person>(?:per|a|each|/)\s*(?:person|passenger|travell?er|adult)\b|\beach\b(?!\s+(?:way|leg|segment|direction)\b))|"
    r"(?P<stay_total>(?:for (?:the |your |the entire |the whole )?|per )stay\b|\bstay total\b)|"
    r"(?P<party_total>\b(?:for (?:the |your |the whole |the entire )?(?:party|group)|"
    r"for (?:both|all) (?:adults|passengers|travell?ers)|party total)\b)|(?P<total>\btotal\b)",
    re.I,
)
NIGHT_DETAIL = re.compile(r"(\d+(?:\.\d+)?) ([A-Z]{3}) per night")
BREAK = re.compile(r"(?:[;!?\n]|\.(?=\s|$))\s*")
NEGATIVE_INVENTORY = re.compile(
    r"\b(?:no (?:matching |available )?(?P<noun>flights?|hotels?|rooms?|seats?|offers?|options?|results?)\b|"
    r"(?P<unavailable>flights?|hotels?|rooms?|seats?|offers?) (?:are |were )?(?:unavailable|sold out))",
    re.I,
)
GUARANTEE = re.compile(
    r"\bguaranteed (?:to be )?(?:available|availability|booking)|\bavailability is guaranteed\b", re.I
)
POSITIVE_INVENTORY = re.compile(
    r"\b(?P<available>rooms?|hotels?|seats?|flights?) (?:are |is )?available\b|"
    r"\b(?:I|we) found (?:a|an|\d+|some|several) (?:matching )?(?P<found>flights?|hotels?|rooms?|offers?)\b",
    re.I,
)


PROVIDER_NOUNS = {"flight": "kiwi", "seat": "kiwi", "hotel": "trivago", "room": "trivago"}


def _has_offers(noun: str, reports: list[TravelReport]) -> bool:
    """Flights and lodging have independent inventory, even when the answer mentions both."""
    provider = PROVIDER_NOUNS.get(noun.lower().rstrip("s"))
    return any(report.offers and provider in (None, report.provider) for report in reports)


def _quotes(offer: TravelOffer) -> set[tuple[str, Decimal, str]]:
    """Use the structured offer price and the adapter's exact nightly detail format."""
    quotes: set[tuple[str, Decimal, str]] = set()
    if offer.currency and offer.price is not None:
        quotes.add((offer.currency, offer.price, offer.price_basis))
    for detail in offer.details:
        if match := NIGHT_DETAIL.fullmatch(detail):
            quotes.add((match[2], Decimal(match[1]), "per_night"))
    return quotes


# A hotel amount without an offer name can still be graded when the sentence makes a generic rate claim.
# Unfamiliar words may be an invented property name; a reviewer must resolve that attribution.
GENERIC_RATE_VOCABULARY = (
    "a an the this that it is at of and or for from to as low as starts starting costs cost priced prices rates "
    "rate price option options hotel hotels room rooms lowest cheapest around about approximately quoted available "
    "whole entire all your our their both adults stay nights per night nightly total totals including taxes fees with"
)
GENERIC_RATE_WORDS = frozenset(GENERIC_RATE_VOCABULARY.split())


def _quote_outcome(sentence: str, reports: list[TravelReport], subject: str) -> str | None:
    """Match each monetary claim to the offer, price basis, amount and currency it describes."""
    folded = sentence.casefold()
    matches = list(MONEY.finditer(sentence))
    for index, match in enumerate(matches):
        unit, raw = (match["prefix"], match["number"]) if match["prefix"] else (match["suffix"], match["value"])
        code = CURRENCIES.get(unit.upper().removesuffix("S"), unit.upper())
        if match["echo"] and match["echo"].upper() != code:
            return "unsupported_price"
        amount = Decimal(raw.replace(",", ""))
        left = sentence[matches[index - 1].end() if index else 0 : match.start()]
        right = sentence[match.end() : matches[index + 1].start() if index + 1 < len(matches) else len(sentence)]
        # The qualifier following this price ends at a clause boundary. A preceding qualifier can also introduce it.
        after = re.split(r",|\(|\)|\band\b|\bor\b", right, maxsplit=1, flags=re.I)[0]
        before = re.split(r",|\(|\)|\band\b|\bor\b", left, flags=re.I)[-1]
        # A basis enclosed in parentheses can immediately follow the amount ("$748 (party total)").
        paren = re.match(r"\s*\(([^()]{1,35})\)", right)
        if not after.strip() and paren and BASIS.fullmatch(paren[1].strip()):
            after = paren[1]
        units = [hit.lastgroup for hit in BASIS.finditer(after)] or [hit.lastgroup for hit in BASIS.finditer(before)]
        specific = {unit for unit in units if unit and unit != "total"}
        context = f"{before} {after}"
        mentioned = {
            PROVIDER_NOUNS[word.lower().rstrip("s")]
            for word in re.findall(r"\b(?:flights?|seats?|hotels?|rooms?)\b", context, re.I)
        }
        offers = [
            offer for report in reports if not mentioned or report.provider in mentioned for offer in report.offers
        ]
        if not offers:
            return "unsupported_price"
        # Prefer the closest earlier title in this sentence (e.g. “A $100, B $120”). If a single title appears
        # only after the price (“$100 at A”), it still restricts the evidence to that offer.
        named = [offer for offer in offers if offer.title.casefold() in folded]
        lead = sentence[: match.start()].casefold()
        earlier = [offer for offer in named if offer.title.casefold() in lead]
        if earlier:
            chosen = max(lead.rfind(offer.title.casefold()) for offer in earlier)
            named = [offer for offer in earlier if lead.rfind(offer.title.casefold()) == chosen]
        if not named and subject:
            named = [offer for offer in offers if offer.title.casefold() in subject.casefold()]
            if not named:
                return "quote_review_unmatched_heading"
        if not earlier and len({offer.title for offer in named}) > 1:
            return "quote_review_multiple_properties"
        evidence = named or offers
        candidates = {quote for offer in evidence for quote in _quotes(offer)}
        priced = {b for c, a, b in candidates if c == code and a == amount}
        if not priced:
            return "unsupported_price"
        hotel_quote = bool(priced & {"stay_total", "per_night"})
        seller = re.search(r"\bvia\s+([^,;)]+)", right, re.I) if hotel_quote else None
        if seller:
            # Trivago emits (nightly amount, advertiser). Match the seller only against offers advertising
            # this specific price and basis. A different hotel at the same price is insufficient.
            names = {
                offer.details[1].casefold()
                for offer in evidence
                if len(offer.details) == 2
                and NIGHT_DETAIL.fullmatch(offer.details[0])
                and any(c == code and a == amount and b in (specific or priced) for c, a, b in _quotes(offer))
            }
            if seller[1].strip().casefold() not in names:
                return "unsupported_seller"
            context = re.sub(re.escape(seller[0].strip()), "", context, flags=re.I)
        if hotel_quote and not any(offer.title.casefold() in context.casefold() for offer in named):
            words = set(re.findall(r"[a-z]+", context.casefold()))
            if words - GENERIC_RATE_WORDS:
                return "quote_review_unclear_property"
        if not units:
            return "quote_review_missing_price_basis"
        if len(specific) > 1:
            return "quote_review_conflicting_price_bases"
        accepted = specific or {"party_total", "stay_total"}
        if priced.isdisjoint(accepted):
            return "unsupported_price"
    return None


# The narrative is Markdown rendered by Nimbus. End each paragraph/list item before inspecting a neighboring price.
BLOCK_END = re.compile(r"</(?:p|li|tr|h[1-6])\s*>|<br\s*/?>", re.I)


def check_claims(fragment: str, reports: list[TravelReport]) -> str | None:
    """Grade each rendered block with its preceding property heading, preserving price qualifier boundaries."""
    titles = {offer.title for report in reports for offer in report.offers}
    subject = ""
    for block in BLOCK_END.split(fragment):
        text = to_text(block)
        if not text:
            continue
        mentioned = [title for title in titles if title.casefold() in text.casefold()]
        if MONEY.search(text) or WRITTEN_MONEY.search(text):
            # A new explicit property overrides the preceding heading (including an unrecognized heading).
            current = "" if mentioned else subject
            if reason := _block_outcome(text, reports, current):
                return reason
            if mentioned:
                subject = mentioned[0] if len(mentioned) == 1 else ""
        else:
            if reason := _block_outcome(text, reports, ""):
                return reason
            # A short separate heading may also be a property the provider never returned. Preserve that
            # attribution for the next price bullet, so no other hotel's matching amount can validate it.
            if len(mentioned) == 1:
                subject = mentioned[0]
            elif re.search(r"<h[1-6]\b|<strong\b", block, re.I) or re.fullmatch(r"[\w &'\u2019.-]{1,100}:?", text):
                subject = text.rstrip(":")
            else:
                subject = ""
    return None


def _block_outcome(text: str, reports: list[TravelReport], subject: str) -> str | None:
    """Classify evidence in one text block; ambiguous quoting cannot earn an automatic pass."""
    offers = [offer for report in reports for offer in report.offers]
    for sentence in BREAK.split(text):
        if reason := _quote_outcome(sentence, reports, subject):
            return reason
        if WRITTEN_MONEY.search(sentence):
            return "quote_review_spelled_out_amount" if offers else "unsupported_price"
        # Searches give point-in-time evidence only. A stated availability guarantee exceeds every provider result.
        if GUARANTEE.search(re.sub(r"\b(?:not|never) guaranteed\b", "", sentence, flags=re.I)):
            return "unsupported_availability"
        for match in NEGATIVE_INVENTORY.finditer(sentence):
            if _has_offers(match["noun"] or match["unavailable"], reports):
                return "unsupported_availability"
        for match in POSITIVE_INVENTORY.finditer(sentence):
            # A question about whether inventory exists and a negative result make no positive availability claim.
            if re.search(r"\b(?:no|whether|if) $", sentence[: match.start()], re.I):
                continue
            if not _has_offers(match["available"] or match["found"], reports):
                return "unsupported_availability"
    return None
