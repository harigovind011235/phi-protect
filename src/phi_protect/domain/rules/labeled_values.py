"""Values that follow a label: an ID after "Member ID:", a date after "DOB", a name after "Patient".

Only the value is reported, so the label stays readable after de-identification.
"""

import re

from phi_protect.domain.models import EntityType, Finding, FindingSource

LABELED_ID_KEYWORDS = {
    EntityType.MEMBER_ID: r"member|subscriber|insured|policy|beneficiary",
    EntityType.GROUP_NUMBER: r"group|grp",
    EntityType.CLAIM_NUMBER: r"claim|icn|dcn",
    EntityType.ACCOUNT_NUMBER: r"mrn|medical[\s_-]*record|chart|account|acct|patient",
}
ID_SUFFIX = r"(?:[\s_-]*(?:id|identifier|no|num|number|nbr|#))?"
SEPARATOR = r"[\s\"':#=.]{0,4}"
ID_VALUE = r"(?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{3,24}"

PATIENT_DATE_KEYWORDS = (
    r"dob|d\.o\.b\.?|date[\s_-]*of[\s_-]*birth|birth[\s_-]*date|birthdate|dos|"
    r"date[\s_-]*of[\s_-]*service|service[\s_-]*date|admi(?:t|ssion)[\s_-]*date|discharge[\s_-]*date"
)
DATE_VALUE = (
    r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}[/.-]\d{1,2}[/.-]\d{1,2}|\d{8}|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}"
)

SSN_KEYWORDS = r"ssn|social[\s_-]*security(?:[\s_-]*(?:number|num|no|#))?"
# Any SSN-shaped value after an SSN label, including numbers never issued (e.g. 000-...), which
# Presidio's own SSN check rejects.
SSN_VALUE = r"\d{3}[- ]?\d{2}[- ]?\d{4}"

PATIENT_NAME_KEYWORDS = r"patient|pt|guarantor|(?:insured|subscriber|member)[\s_-]*name"
TITLE = r"(?:Dr|Mr|Mrs|Ms|Miss)\.?\s+"
# Capitalized words that commonly follow "Patient" in RCM and code text but are not names.
NOT_NAMES = (
    r"Account|Accounts|Address|Age|Balance|Care|Chart|Claim|Class|Collections?|Communication|"
    r"Copay|Count|Dashboard|Data|Date|DOB|DOS|Email|Gender|Group|Member|MRN|NPI|Phone|Policy|Sex|"
    r"SSN|Subscriber|Demographics|Details|Education|Eligibility|Engagement|Estimates?|Evaluation|"
    r"Experience|Financing|Forms?|Id|ID|Info|Information|Insurance|Intake|Ledger|List|Lookup|"
    r"Model|Module|Name|Notes?|Number|Patient|Payments?|Portal|Portion|Profile|Refunds?|"
    r"Registration|Reports?|Responsibility|Search|Services?|Statements?|Status|Summary|Table|Type|"
    r"Visits?"
)
NAME_WORD = rf"(?!(?:{NOT_NAMES})\b)[A-Z][a-zA-Z'-]+"
PATIENT_NAME_REGEX = (
    rf"\b(?i:{PATIENT_NAME_KEYWORDS})(?i:[\s_-]*name)?[\s\"':=,.-]{{1,4}}(?:{TITLE})?"
    rf"(?P<value>{NAME_WORD}(?:\s+{NAME_WORD}){{0,2}})"
)

LABELED_PATTERNS: list[tuple[EntityType, re.Pattern[str]]] = [
    *(
        (
            entity,
            re.compile(
                rf"\b(?:{keywords}){ID_SUFFIX}{SEPARATOR}(?P<value>{ID_VALUE})\b", re.IGNORECASE
            ),
        )
        for entity, keywords in LABELED_ID_KEYWORDS.items()
    ),
    (
        EntityType.PATIENT_DATE,
        re.compile(
            rf"\b(?:{PATIENT_DATE_KEYWORDS}){SEPARATOR}(?:is\s+)?(?P<value>{DATE_VALUE})\b",
            re.IGNORECASE,
        ),
    ),
    (
        EntityType.US_SSN,
        re.compile(rf"\b(?:{SSN_KEYWORDS}){SEPARATOR}(?P<value>{SSN_VALUE})\b", re.IGNORECASE),
    ),
    (EntityType.PERSON, re.compile(PATIENT_NAME_REGEX)),
]
LABELED_SCORE = 0.85

# X12 NM1 name segment for a person (qualifier 1) who is the subscriber (IL) or patient (QC):
# NM1*IL*1*LAST*FIRST*MIDDLE~. Provider (82, 85, DN) and payer (PR) names are not PHI.
X12_PERSON_NAME = re.compile(
    r"\bNM1\*(?:IL|QC)\*1\*(?P<last>[^*~\n]*)(?:\*(?P<first>[^*~\n]*))?(?:\*(?P<middle>[^*~\n]*))?"
)
X12_NAME_FIELDS = ("last", "first", "middle")


def find_labeled_values(text: str) -> list[Finding]:
    return [
        *(
            _rule_finding(entity, match.start("value"), match.end("value"))
            for entity, pattern in LABELED_PATTERNS
            for match in pattern.finditer(text)
        ),
        *_find_x12_person_names(text),
    ]


def _find_x12_person_names(text: str) -> list[Finding]:
    """Each name field is its own finding, so redaction keeps the segment's * separators."""
    return [
        _rule_finding(EntityType.PERSON, match.start(field), match.end(field))
        for match in X12_PERSON_NAME.finditer(text)
        for field in X12_NAME_FIELDS
        if match.group(field)
    ]


def _rule_finding(entity: EntityType, start: int, end: int) -> Finding:
    return Finding(entity, start, end, LABELED_SCORE, FindingSource.RULE)
