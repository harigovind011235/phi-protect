import asyncio

from phi_protect.domain.models import EntityType, FindingSource


async def test_finds_names_and_presidio_entities(container):
    text = "Please call Maria Lopez at maria.lopez@example.com"
    findings = await container.phi_detector.detect(text)
    found = {(f.entity_type, text[f.start : f.end]) for f in findings}
    assert (EntityType.PERSON, "Maria Lopez") in found
    assert (EntityType.EMAIL_ADDRESS, "maria.lopez@example.com") in found
    assert {f.source for f in findings} == {FindingSource.DETECTOR}


async def test_returns_raw_candidates_without_rules_or_policy(container):
    findings = await container.phi_detector.detect("Member ID: XGH884213901")
    assert EntityType.MEMBER_ID not in {f.entity_type for f in findings}


async def test_parallel_scans_return_the_same_result(container):
    text = "Patient Maria Lopez, phone (512) 555-0142"
    results = await asyncio.gather(*(container.phi_detector.detect(text) for _ in range(4)))
    assert all(result == results[0] for result in results)
