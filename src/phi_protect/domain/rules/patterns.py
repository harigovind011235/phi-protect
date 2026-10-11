"""Shape-based rules: identifiers recognizable by their format or by the structure around them."""

import re
from dataclasses import dataclass

from phi_protect.domain.models import EntityType, Finding, FindingSource
from phi_protect.domain.rules.us_states import US_STATE_CODES


@dataclass(frozen=True)
class PatternRule:
    name: str
    entity_type: EntityType
    regex: re.Pattern[str]
    score: float


def _rule(name: str, entity_type: EntityType, regex: str, score: float, flags: int = 0):
    return PatternRule(name, entity_type, re.compile(regex, re.MULTILINE | flags), score)


MBI_LETTER = "[AC-HJKMNP-RT-Y]"
MBI_ALNUM = "[AC-HJKMNP-RT-Y0-9]"
MBI_REGEX = (
    rf"\b[1-9]{MBI_LETTER}{MBI_ALNUM}\d-?{MBI_LETTER}{MBI_ALNUM}\d-?{MBI_LETTER}{{2}}\d{{2}}\b"
)

STATES = "|".join(sorted(US_STATE_CODES))
STREET_SUFFIXES = (
    "Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|Way|Place|Pl|"
    "Parkway|Pkwy|Circle|Cir|Terrace|Ter|Highway|Hwy|Trail|Trl|Square|Sq|Loop|Pike|Plaza|"
    "Alley|Crossing|Grove|Heights|Hills|Manor|Park|Path|Point|Ridge|Row|Run|View|Walk"
)
UNIT = r",?\s+(?:Apt|Suite|Ste|Unit|#)\.?\s*[A-Za-z0-9-]+"
STREET_START = r"\b\d{1,6}(?:\s+[A-Z][A-Za-z'.-]*){1,4}"
CITY = r"[A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){0,2}"
STATE_AND_ZIP = r",?\s+[A-Z]{2}\s+\d{5}(?:-\d{4})?\b"

# Lowercase variants need stronger evidence (a real state code after a comma, or an apartment
# number), otherwise phrases like "copy 2 files to the shared drive" would match.
STREET_START_ANY_CASE = r"\b\d{1,6}(?:\s+[a-z][a-z'.-]*){1,4}"
CITY_ANY_CASE = r"[a-z][a-z.'-]*(?:\s+[a-z][a-z.'-]*){0,2}"
CITY_STATE_ZIP_ANY_CASE = rf"{CITY_ANY_CASE},\s*(?:{STATES})\s+\d{{5}}(?:-\d{{4}})?\b"

US_PHONE_REGEX = (
    r"(?<![\w-])(?:(?:\+?1|001)[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]\d{4}"
    r"(?:\s*(?:x|ext\.?)\s*\d{1,6})?(?![\w-])"
)

PATTERN_RULES = [
    _rule("x12_dmg_birth_date", EntityType.PATIENT_DATE, r"(?<=\bDMG\*D8\*)\d{8}", 0.85),
    _rule("x12_dtp_date", EntityType.PATIENT_DATE, r"(?<=\bDTP\*\d{3}\*D8\*)\d{8}", 0.85),
    _rule(
        "x12_dtp_date_range",
        EntityType.PATIENT_DATE,
        r"(?<=\bDTP\*\d{3}\*RD8\*)\d{8}-\d{8}",
        0.85,
    ),
    _rule("mbi", EntityType.MEDICARE_ID, MBI_REGEX, 0.85),
    _rule(
        "street_suffix",
        EntityType.STREET_ADDRESS,
        rf"{STREET_START}\s+(?:{STREET_SUFFIXES})\b\.?(?:{UNIT})?",
        0.7,
    ),
    _rule("street_unit", EntityType.STREET_ADDRESS, rf"{STREET_START}{UNIT}", 0.7),
    _rule(
        "street_before_city",
        EntityType.STREET_ADDRESS,
        rf"{STREET_START}(?=,\s*{CITY}{STATE_AND_ZIP})",
        0.7,
    ),
    _rule(
        "street_word_any_case",
        EntityType.STREET_ADDRESS,
        rf"(?i){STREET_START_ANY_CASE}?\s+(?:street|avenue|boulevard)\b",
        0.7,
    ),
    _rule(
        "street_before_city_any_case",
        EntityType.STREET_ADDRESS,
        rf"(?i){STREET_START_ANY_CASE}(?=,\s*{CITY_STATE_ZIP_ANY_CASE})",
        0.7,
    ),
    _rule(
        "street_apartment_any_case",
        EntityType.STREET_ADDRESS,
        rf"(?i){STREET_START_ANY_CASE},?\s+(?:apt|suite|ste)\.?\s*#?\s*[a-z0-9-]*\d[a-z0-9-]*",
        0.7,
    ),
    _rule(
        "po_box",
        EntityType.STREET_ADDRESS,
        r"(?i)\b(?:p\.?\s*o\.?\s*box|post\s+office\s+box)\s*#?\s*\d+",
        0.85,
    ),
    _rule("x12_n3_segment", EntityType.STREET_ADDRESS, r"(?<=\bN3\*)[^~\n]+", 0.85),
    _rule("city_before_state_zip", EntityType.LOCATION, rf"\b{CITY}(?={STATE_AND_ZIP})", 0.6),
    _rule(
        "city_state_zip_any_case",
        EntityType.LOCATION,
        rf"(?i)\b{CITY_STATE_ZIP_ANY_CASE}",
        0.7,
    ),
    _rule("x12_n4_segment", EntityType.LOCATION, r"(?<=\bN4\*)[^~\n]+", 0.85),
    _rule("us_phone", EntityType.PHONE_NUMBER, US_PHONE_REGEX, 0.7, re.IGNORECASE),
    _rule("zip_after_state", EntityType.ZIP_CODE, r"(?<=\b[A-Z]{2} )\d{5}(?:-\d{4})?\b", 0.6),
]


def find_pattern_matches(text: str) -> list[Finding]:
    return [
        Finding(rule.entity_type, match.start(), match.end(), rule.score, FindingSource.RULE)
        for rule in PATTERN_RULES
        for match in rule.regex.finditer(text)
        if match.end() > match.start()
    ]
