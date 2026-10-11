"""Values that look like PHI to the detectors but are known not to be."""

import re

from phi_protect.domain.models import EntityType
from phi_protect.domain.rules import US_STATE_CODES

PAYER_NAMES = frozenset(
    {
        "aetna",
        "ameritas",
        "anthem",
        "bcbs",
        "blue cross",
        "blue cross blue shield",
        "cigna",
        "cigna dental",
        "delta dental",
        "dentaquest",
        "geha",
        "guardian",
        "humana",
        "liberty dental",
        "medicaid",
        "medicare",
        "metlife",
        "principal",
        "united concordia",
        "unitedhealthcare",
    }
)

# AI tools the model reads as people's names. Only the bare product name is allowed, so a
# person's full name that starts with one of them is still caught.
PRODUCT_NAMES = frozenset(
    {
        "anthropic",
        "chatgpt",
        "claude",
        "claude code",
        "claude.ai",
        "claude.md",
        "copilot",
        "cursor",
        "gemini",
        "github copilot",
        "hugging face",
        "openai",
    }
)

KNOWN_NON_PHI_NAMES = PAYER_NAMES | PRODUCT_NAMES

NOT_PHI_PATTERNS = [
    # UUID and long lowercase hex such as git commit hashes
    re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"),
    re.compile(r"(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{16,}"),
    re.compile(r"D\d{4}"),  # CDT procedure code
    re.compile(r"(?:270|271|276|277|278|820|834|835|837)[DIP]?"),  # X12 transaction type
    # X12 segment name
    re.compile(
        r"(?:ISA|GS|ST|BHT|NM1|N3|N4|DMG|REF|DTP|CLM|SBR|HL|PRV|SV3|TOO|CAS|SVC|AMT|LX|SE|GE|IEA)"
    ),
    re.compile(r"v\d+(?:\.\d+)*"),  # version
    re.compile(r"\d+(?:ms|s|sec|kb|mb|gb|%)", re.IGNORECASE),  # duration, size, percent
    re.compile(r"(?:YYYY|YY|MM|DD|HH|SS|[/.:\s-])+"),  # date format placeholder
    re.compile(r"\.[A-Za-z0-9_.-]+"),  # hidden file or folder, e.g. .claude
    re.compile(r"[\W_]+"),  # punctuation only
]

# Only detector guesses can be overruled; labeled identifiers (MRN, claim, member ID) never are.
ALLOWLISTABLE_ENTITIES = frozenset(
    {EntityType.PERSON, EntityType.ID, EntityType.PHONE_NUMBER, EntityType.DATE_TIME}
)

# Provider identifiers (NPI, taxonomy, TIN) are not patient identifiers. The gap between the label
# and the value may not contain digits or separators, so the rule cannot reach another identifier.
PROVIDER_ID_LABEL = re.compile(
    r"\b(?:npi|taxonomy|tin|ein|tax\s*id)\b[^\n;,|\d]{0,30}$", re.IGNORECASE
)
PROVIDER_ID_LOOKBACK = 45

# Names with a doctor title are providers. The model labels most patients as providers too,
# so the title is what separates them, not the model's label.
PROVIDER_NAME = re.compile(r"(?:dr|doctor)\.?\s+\S+", re.IGNORECASE)
PROVIDER_TITLE_BEFORE = re.compile(r"\b(?:dr|doctor)\.?\s*$", re.IGNORECASE)
PATIENT_CONTEXT_BEFORE = re.compile(
    r"\b(?:patient|pt|subscriber|insured|member|guarantor|dependent)\b[\s:,.-]*"
    r"(?:(?:dr|doctor)\.?\s*)?$",
    re.IGNORECASE,
)
CONTEXT_LOOKBACK = 30
MIN_PHONE_DIGITS = 7

# The folder right after a home directory root is a login name, not a patient, e.g. /home/<user>/.
HOME_FOLDER_BEFORE = re.compile(r"(?:/home/|/Users/|\\Users\\)$", re.IGNORECASE)
PATH_SEGMENT = re.compile(r"[^\s/\\]+")


def is_allowed(text: str, entity_type: EntityType, start: int, end: int) -> bool:
    if entity_type not in ALLOWLISTABLE_ENTITIES:
        return False
    value = text[start:end].strip()
    if value.lower() in KNOWN_NON_PHI_NAMES or value in US_STATE_CODES:
        return True
    if any(pattern.fullmatch(value) for pattern in NOT_PHI_PATTERNS):
        return True
    if _is_home_folder_name(text, start, value):
        return True
    if entity_type == EntityType.PERSON:
        return _is_provider_name(text, start, value)
    if entity_type == EntityType.PHONE_NUMBER:
        return sum(c.isdigit() for c in value) < MIN_PHONE_DIGITS
    if entity_type == EntityType.ID:
        before = text[max(0, start - PROVIDER_ID_LOOKBACK) : start]
        return bool(PROVIDER_ID_LABEL.search(before))
    return False


def _is_home_folder_name(text: str, start: int, value: str) -> bool:
    before = text[max(0, start - CONTEXT_LOOKBACK) : start]
    return bool(HOME_FOLDER_BEFORE.search(before) and PATH_SEGMENT.fullmatch(value))


def _is_provider_name(text: str, start: int, value: str) -> bool:
    before = text[max(0, start - CONTEXT_LOOKBACK) : start]
    if PATIENT_CONTEXT_BEFORE.search(before):
        return False
    return bool(PROVIDER_NAME.fullmatch(value) or PROVIDER_TITLE_BEFORE.search(before))
