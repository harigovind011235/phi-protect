import asyncio
import threading

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import SpacyNlpEngine

from phi_protect.adapters.detectors.huggingface_ner_recognizer import HuggingFaceNerRecognizer
from phi_protect.domain.models import EntityType, Finding
from phi_protect.usecases.ports.detectors import PhiDetector

# The Stanford de-identification model labels most patients as HCW (healthcare worker), so HCW
# must stay mapped to PERSON; dropping it cut name recall from 96% to 22%.
MODEL_LABEL_MAPPING = {
    "PATIENT": EntityType.PERSON,
    "HCW": EntityType.PERSON,
    "DATE": EntityType.DATE_TIME,
    "ID": EntityType.ID,
    "PHONE": EntityType.PHONE_NUMBER,
}
# Model entities plus the ones Presidio's built-in recognizers find (SSN, email, credit card, ...).
REQUESTED_ENTITIES = [
    EntityType.PERSON,
    EntityType.DATE_TIME,
    EntityType.ID,
    EntityType.PHONE_NUMBER,
    EntityType.EMAIL_ADDRESS,
    EntityType.US_SSN,
    EntityType.CREDIT_CARD,
]
SPACY_MODEL = "en_core_web_sm"


class PresidioPhiDetector(PhiDetector):
    """Presidio's built-in recognizers plus a Hugging Face NER model.

    Inference is CPU-bound, so it runs in a worker thread (keeping the event loop free), and at most
    `max_concurrent_scans` run at once so parallel requests queue instead of fighting over the CPU.
    """

    def __init__(
        self,
        model_name: str,
        model_revision: str,
        score_threshold: float,
        max_concurrent_scans: int,
    ):
        self._analyzer = _build_analyzer(model_name, model_revision)
        self._score_threshold = score_threshold
        self._scan_slots = threading.BoundedSemaphore(max_concurrent_scans)

    async def detect(self, text: str) -> list[Finding]:
        return await asyncio.to_thread(self._detect, text)

    def _detect(self, text: str) -> list[Finding]:
        with self._scan_slots:
            results = self._analyzer.analyze(
                text=text,
                language="en",
                entities=[entity.value for entity in REQUESTED_ENTITIES],
                score_threshold=self._score_threshold,
            )
        return [Finding(EntityType(r.entity_type), r.start, r.end, r.score) for r in results]


def _build_analyzer(model_name: str, model_revision: str) -> AnalyzerEngine:
    nlp_engine = SpacyNlpEngine(models=[{"lang_code": "en", "model_name": SPACY_MODEL}])
    nlp_engine.load()
    registry = RecognizerRegistry()
    registry.load_predefined_recognizers(nlp_engine=nlp_engine)
    # spaCy is kept for tokens and context words only; names come from the NER model.
    registry.remove_recognizer("SpacyRecognizer")
    label_mapping = {label: entity.value for label, entity in MODEL_LABEL_MAPPING.items()}
    registry.add_recognizer(HuggingFaceNerRecognizer(model_name, model_revision, label_mapping))
    return AnalyzerEngine(nlp_engine=nlp_engine, registry=registry)
