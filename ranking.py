import time

def calculate_gravity_score(base_score: float, published_at_ts: float, gravity: float = 1.8) -> float:
    """
    Calculate the gravity score based on: Score / (Time + 2)^G
    Time is in hours since publication.
    """
    now = time.time()
    
    # Calculate age in hours
    # Ensure age is at least 0 to avoid issues with future timestamps (clock skew)
    age_hours = max(0, (now - published_at_ts) / 3600)
    
    # Standard HNews Gravity Formula
    # score / (age_hours + 2) ^ gravity
    return base_score / pow((age_hours + 2), gravity)
