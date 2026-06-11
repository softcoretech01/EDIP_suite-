from sentence_transformers import SentenceTransformer
from typing import List

class MetadataEmbedder:
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        # Load the model locally
        self.model = SentenceTransformer(model_name)

    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single string.
        """
        embedding = self.model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of strings.
        """
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()
