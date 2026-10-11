from phi_protect.domain.models import Finding


def placeholders(text: str, findings: list[Finding]) -> list[str]:
    """One label per finding; the same value always gets the same label, e.g. [PERSON_1]."""
    labels: dict[tuple[str, str], str] = {}
    counts: dict[str, int] = {}
    result = []
    for finding in findings:
        key = (finding.entity_type, text[finding.start : finding.end].lower())
        if key not in labels:
            counts[finding.entity_type] = counts.get(finding.entity_type, 0) + 1
            labels[key] = f"[{finding.entity_type}_{counts[finding.entity_type]}]"
        result.append(labels[key])
    return result


def replace_spans(text: str, findings: list[Finding], labels: list[str]) -> str:
    parts: list[str] = []
    cursor = 0
    for finding, label in zip(findings, labels, strict=True):
        parts.append(text[cursor : finding.start])
        parts.append(label)
        cursor = finding.end
    parts.append(text[cursor:])
    return "".join(parts)


def deidentify(text: str, findings: list[Finding]) -> str:
    return replace_spans(text, findings, placeholders(text, findings))
