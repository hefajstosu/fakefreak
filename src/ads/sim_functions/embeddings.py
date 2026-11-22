"""Optional embedding backend. Not imported by default: sentence-transformers is not in
requirements.txt yet (append it in its own PR if the team adopts this)."""
from __future__ import annotations


class E5Embedder:
    """Callable list[str] -> list[list[float]] using multilingual-e5 (the model named in
    config/cluster.yaml). e5 expects a 'passage: ' prefix on both sides for symmetric
    similarity. Results are cached per text, so each profile field is embedded once."""

    def __init__(self, model_name: str = "intfloat/multilingual-e5-small", prefix: str = "passage: "):
        self.model_name = model_name
        self.prefix = prefix
        self._model = None
        self._cache = {}

    def __call__(self, texts):
        missing = [t for t in dict.fromkeys(texts) if t not in self._cache]
        if missing:
            if self._model is None:
                from sentence_transformers import SentenceTransformer  # lazy import
                self._model = SentenceTransformer(self.model_name)
            vecs = self._model.encode([self.prefix + t for t in missing], normalize_embeddings=True)
            self._cache.update(zip(missing, (v.tolist() for v in vecs)))
        return [self._cache[t] for t in texts]
