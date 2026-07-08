"""Standalone test for the L1/L2 binary-split runaway fix.

Stubs config/db/ai_service/response_utils/ranking so the REAL processor source
(l1_filter.py, l2_scorer.py) can be exercised with no external deps, simulating a
Volc-Ark-style content-filter refusal (200 OK with non-JSON refusal text).

Proves:
  A. All-refused batch -> loop TERMINATES (no runaway) and every item is drained.
  B. One poison item -> binary split ISOLATES it (marked refused) and SALVAGES
     the rest (drained normally).
  C. Same guarantees for L2.
"""
import sys, types, json, importlib.util, os

BASE = os.path.dirname(os.path.abspath(__file__))

# ---------- stub: config ----------
cfg = types.ModuleType("config")
class _Cfg:
    L1_BATCH_SIZE = 8
    L2_BATCH_SIZE = 8
    AI_MODEL_L1 = "Task-Model"
    AI_MODEL_L2 = "Task-Model-Pro"
    RANKING_WINDOW_HOURS = 72
    GRAVITY = 1.1
    MAX_L1_LOOPS = 40
    MAX_L2_LOOPS = 40
cfg.config = _Cfg()
sys.modules["config"] = cfg

# ---------- stub: response_utils ----------
ru = types.ModuleType("response_utils")
def parse_json_response(text):
    if not text:
        return None, None
    try:
        return json.loads(text), text
    except Exception:
        return None, None
ru.parse_json_response = parse_json_response
ru.sanitize_text = lambda x: x if isinstance(x, str) else ('' if x is None else str(x))
ru.best_title_match = lambda title, items, threshold=0.6: ((items[0], 1.0) if items else (None, 0.0))
sys.modules["response_utils"] = ru

# ---------- stub: ranking ----------
rk = types.ModuleType("ranking")
rk.calculate_gravity_score = lambda score, published_at, gravity: float(score or 0)
sys.modules["ranking"] = rk

# ---------- stub: database ----------
class FakeDB:
    def __init__(self, items):
        self.items = {it['id']: it for it in items}
    def get_pending_news(self, limit=20):
        p = [it for it in self.items.values() if it['status'] == 'pending']
        return [dict(x) for x in p[:limit]]
    def update_l1_result(self, news_id, score, reason, status):
        self.items[news_id].update(status=status, l1_reason=reason, l1_score=score)
    def get_high_score_pending_l2(self, min_score=70, limit=20):
        p = [it for it in self.items.values() if it['status'] == 'l1_done']
        return [dict(x) for x in p[:limit]]
    def update_l2_result(self, news_id, score, summary, title_zh, category):
        self.items[news_id].update(status='processed', l2_summary=summary, l2_reason=summary)
    def get_recent_processed_news(self, hours=72):
        return []
db_mod = types.ModuleType("database")
db_mod.db = FakeDB([])
sys.modules["database"] = db_mod

# ---------- stub: ai_service (poison-aware) ----------
class FakeAI:
    REFUSAL = "抱歉，您的问题我无法回答。"
    def __init__(self):
        self.count = 0
    def chat_completion(self, messages, model=None, response_format=None):
        self.count += 1
        text = " ".join(m.get("content", "") for m in messages)
        if "REFUSE" in text:
            return self.REFUSAL          # non-JSON refusal -> parse fails
        return json.dumps({"items": [], "feed": []})  # valid, drains as filtered
ai_mod = types.ModuleType("ai_service")
ai_mod.ai_service = FakeAI()
sys.modules["ai_service"] = ai_mod

# ---------- load REAL processor source ----------
def load(name, fname):
    spec = importlib.util.spec_from_file_location(name, os.path.join(BASE, "processors", fname))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m
L1 = load("l1_filter", "l1_filter.py")
L2 = load("l2_scorer", "l2_scorer.py")

def mk(n, poison_ids=()):
    return [dict(id=i, title=("REFUSE sensitive" if i in poison_ids else f"good news {i}"),
                 source_name="src", summary="s", url=f"http://x/{i}", published_at=0.0,
                 status='pending') for i in range(1, n + 1)]

fails = []
def check(cond, msg):
    print(("  ok  " if cond else " FAIL ") + msg)
    if not cond:
        fails.append(msg)

# ===== Test A: all refused -> terminates + drains, bounded calls =====
print("== Test A: L1 all-refused batch ==")
db = FakeDB(mk(5, poison_ids={1,2,3,4,5})); L1.db = db; ai = FakeAI(); L1.ai_service = ai
loops = 0
while loops < 100:
    c = L1.l1_filter.process_pending(batch_size=8); loops += 1
    if c == 0: break
check(loops < 100, f"loop terminated via count==0 (loops={loops})")
check(all(it['status'] != 'pending' for it in db.items.values()), "all items drained (none left pending)")
check(all('unparseable/refused' in (it.get('l1_reason') or '') for it in db.items.values()), "all marked refused")
check(ai.count < 40, f"LLM calls bounded (count={ai.count})")

# ===== Test B: one poison -> isolate it, salvage the rest =====
print("== Test B: L1 one poison among 5 ==")
db = FakeDB(mk(5, poison_ids={3})); L1.db = db; ai = FakeAI(); L1.ai_service = ai
loops = 0
while loops < 100:
    c = L1.l1_filter.process_pending(batch_size=8); loops += 1
    if c == 0: break
poison = db.items[3]; others = [db.items[i] for i in (1,2,4,5)]
check(loops < 100, f"loop terminated (loops={loops})")
check('unparseable/refused' in (poison.get('l1_reason') or ''), "poison item isolated + marked refused")
check(all('unparseable/refused' not in (o.get('l1_reason') or '') for o in others), "other items salvaged (not marked refused)")
check(all(o['status'] != 'pending' for o in others), "salvaged items drained normally")

# ===== Test C: L2 all refused -> terminates + drains =====
print("== Test C: L2 all-refused batch ==")
items = mk(5, poison_ids={1,2,3,4,5})
for it in items: it['status'] = 'l1_done'   # pending L2
db = FakeDB(items); L2.db = db; ai = FakeAI(); L2.ai_service = ai
loops = 0
while loops < 100:
    c = L2.l2_scorer.process_l1_passed(); loops += 1
    if c == 0: break
check(loops < 100, f"L2 loop terminated (loops={loops})")
check(all(it['status'] == 'processed' for it in db.items.values()), "all L2 items drained (processed)")
check(ai.count < 40, f"L2 LLM calls bounded (count={ai.count})")

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURE(S): {fails}")
sys.exit(1 if fails else 0)
