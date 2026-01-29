import time

def calculate_gravity_score(base_score: float, published_at_ts: float, gravity: float = 1.8) -> float:
    """
    Calculate the gravity score with score-aware time decay.
    
    High-scoring items decay slower than low-scoring items.
    Formula: Score / (Time + base_offset + score_bonus)^effective_gravity
    
    - base_offset: 0.5 (reduced from 2 to make decay faster overall)
    - score_bonus: 0 to 3 hours extra buffer based on score (0-100)
    - effective_gravity: slightly reduced for high scores
    
    This ensures truly important news (high L2 score) stays relevant longer,
    while regular items decay more quickly.
    """
    now = time.time()
    
    # Calculate age in hours
    age_hours = max(0, (now - published_at_ts) / 3600)
    
    # Base offset reduced from 2 to 0.5 for faster overall decay
    base_offset = 0.5
    
    # Score bonus: high scores get up to 3 hours of extra buffer
    # Normalized assuming L2 scores range 0-100
    # score 0 -> 0h bonus, score 50 -> 1.5h bonus, score 100 -> 3h bonus
    score_bonus = (base_score / 100) * 3.0
    
    # Effective gravity: high scores decay slightly slower
    # score 0 -> gravity, score 100 -> gravity * 0.85
    gravity_reduction = (base_score / 100) * 0.15
    effective_gravity = gravity - gravity_reduction
    
    # Combined offset
    total_offset = base_offset + score_bonus
    
    # Final formula
    return base_score / pow((age_hours + total_offset), effective_gravity)
