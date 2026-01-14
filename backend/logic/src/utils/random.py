import random
import hashlib
from typing import List, Optional
import numpy as np

def get_random_value(user_id: str, report_id: int) -> float:
    data = f"{user_id}|{report_id}".encode("utf-8")
    seed = int(hashlib.sha256(data).hexdigest(), 16)
    rng = random.Random(seed)
    if rng.random() < 0.5:
      return 0.0
    rng = random.Random(seed+1)
    return rng.random() 

def add_noise_to_vector(vector : List[float], random_value: float, seed : Optional[int] = None):
    query = np.array(vector)

    if seed is not None:
        np.random.seed(seed)

    direction = np.random.normal(0.0, 1.0, size=len(query))

    # make it orthogonal to query
    direction -= np.dot(direction, query) * query
    direction /= np.linalg.norm(direction)

    # target cosine goes linearly from 1 → 0
    cos_target = 1.0 - random_value
    sin_target = np.sqrt(1.0 - cos_target**2)

    # spherical interpolation
    new_query = cos_target * query + sin_target * direction

    query = new_query
    return query