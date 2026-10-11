from phi_protect.adapters.documents.plain_text_format import PlainTextFormat
from phi_protect.domain.models import EntityType, Finding

text_format = PlainTextFormat()


def test_binary_data_is_not_text():
    assert text_format.supports(b"name,dob\n")
    assert not text_format.supports(b"PK\x03\x04\x00\x00")


async def test_decodes_utf8_and_windows_encodings():
    assert (await text_format.extract("café".encode())).text == "café"
    assert (await text_format.extract("café".encode("cp1252"))).text == "café"


async def test_redaction_replaces_spans_with_labels():
    document = await text_format.extract(b"name\nMaria Lopez\n")
    findings = [Finding(EntityType.PERSON, 5, 16, 0.9)]
    assert (
        await text_format.redact(b"", document, findings, ["[PERSON_1]"]) == b"name\n[PERSON_1]\n"
    )
