import time

def calculate_gravity_score(base_score: float, published_at_ts: float, gravity: float = 1.8) -> float:
    """
    Calculate the gravity score with score-adaptive decay.
    
    Goal: "Absolute hotness" (High L2 score) should persist longer.
    New items (<2h) should not dominate just by being new.
    
    Strategy:
    1. Base Offset = 6 hours (Flattens the curve for the first few hours).
    2. Dynamic Gravity: 
       - Low scores decay with full gravity.
       - High scores (near 100) decay with significantly reduced gravity (up to 50% less).
    3. Normalization: Ensures t=0 score is close to base_score.
    """
    now = time.time()
    age_hours = max(0, (now - published_at_ts) / 3600)
    
    # 1. Base Offset: Larger offset means time matters LESS in the beginning.
    # HN uses 2. We use 6 to suppress the "newness spike".
    offset = 6.0
    
    # 2. Dynamic Gravity
    # Reduce gravity for high scores to give them "longevity".
    # We want Score 92 @ 12h to beat Score 75 @ 1h.
    # To achieve this, high scores need extremely low gravity.
    # New Logic: Linear scaling that drops gravity significantly for scores > 80.
    # Score 100 -> factor ~0.2
    # Score 75  -> factor ~0.4
    # Score 50  -> factor ~0.6
    
    # Formula: 1.0 - (score / 100) * 0.8
    # Score 100 -> 0.2
    # Score 0   -> 1.0
    gravity_factor = 1.0 - (base_score / 100.0) * 0.8
    
    # Clamp factor to safety range [0.15, 1.2]
    # We allow it to go very low (0.15) for practically zero decay on perfect scores during the window.
    gravity_factor = max(0.15, min(1.2, gravity_factor))
    
    effective_gravity = gravity * gravity_factor

    # 3. Calculation with Normalization
    # We multiply by (offset^effective_gravity) so that at age=0, ratio is 1.0.
    # Result = Score * (offset / (age + offset)) ^ effective_gravity
    
    time_decay = pow(offset / (age_hours + offset), effective_gravity)
    
    return base_score * time_decay
