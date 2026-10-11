from presidio_analyzer import EntityRecognizer, RecognizerResult
from transformers import pipeline


class HuggingFaceNerRecognizer(EntityRecognizer):
    """Presidio recognizer running a Hugging Face NER model with its own character offsets.

    Presidio's built-in transformers bridge realigns results to spaCy tokens, which silently drops
    findings it cannot align and logs the input text in its warnings, so it is not used.
    """

    def __init__(self, model_name: str, revision: str, label_mapping: dict[str, str]):
        self._model_name = model_name
        self._revision = revision
        self._label_mapping = label_mapping
        super().__init__(
            supported_entities=sorted(set(label_mapping.values())), name="HuggingFaceNerRecognizer"
        )

    def load(self) -> None:
        self._pipeline = pipeline(
            "token-classification",
            model=self._model_name,
            revision=self._revision,
            aggregation_strategy="max",
            stride=64,
            device="cpu",
        )
        model_labels = set((self._pipeline.model.config.id2label or {}).values())
        missing = set(self._label_mapping) - model_labels
        if missing:
            raise ValueError(
                f"Model {self._model_name} does not produce expected labels: {sorted(missing)}"
            )

    def analyze(self, text, entities, nlp_artifacts=None):
        results = []
        for prediction in self._pipeline(text):
            entity = self._label_mapping.get(prediction["entity_group"])
            if entity is None or entity not in entities:
                continue
            score = float(prediction["score"])
            results.append(RecognizerResult(entity, prediction["start"], prediction["end"], score))
        return results
