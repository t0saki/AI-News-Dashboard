from database import db
import time

def debug_news(ids):
    conn = db.get_conn()
    cursor = conn.cursor()
    placeholders = ','.join('?' for _ in ids)
    cursor.execute(f"SELECT id, title, published_at, l1_score, l2_score, status, l2_title_zh FROM news WHERE id IN ({placeholders})", ids)
    rows = cursor.fetchall()
    
    now = time.time()
    for row in rows:
        nid, title, pub, l1, l2, status, zh = row
        age_hours = (now - pub) / 3600
        print(f"ID: {nid}")
        print(f"Title: {title}")
        print(f"Published: {pub} (Age: {age_hours:.2f} hours)")
        print(f"L1: {l1}, L2: {l2}")
        print(f"Status: {status}")
        print(f"L2 Title: {zh}")
        print("-" * 20)
        
    conn.close()

if __name__ == "__main__":
    debug_news([17, 16, 13, 6])
