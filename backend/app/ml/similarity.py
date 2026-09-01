"""
Semantic similarity module.

Uses sentence-transformers to embed complaint text, then numpy cosine
similarity to find related complaints within a geographic radius.
"""

from typing import List, Tuple
import numpy as np


def generate_embedding(text: str) -> List[float]:
    """Generate a dense vector embedding for the given text.

    Uses the sentence-transformer model specified in EMBEDDING_MODEL env var.

    Returns:
        List of floats (embedding vector).
    """
    # TODO: load model (cache globally), encode text, return as list
    raise NotImplementedError


def find_similar(
    embedding: List[float],
    lat: float,
    lng: float,
    radius_m: float = 5000.0,
    top_k: int = 5,
) -> List[Tuple[int, float]]:
    """Find complaints similar to the given embedding within a radius.

    Args:
        embedding: query embedding vector.
        lat, lng: center point for geographic filter.
        radius_m: search radius in meters.
        top_k: max results to return.

    Returns:
        List of (complaint_id, cosine_similarity_score) tuples.
    """
    # TODO: fetch embeddings from DB within geo radius
    # TODO: compute cosine similarity using numpy
    # TODO: return top-k matches sorted by score descending
    raise NotImplementedError
