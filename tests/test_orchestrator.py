import os,sys,unittest,unittest.mock,tempfile,json
sys.path.insert(0,os.path.join(os.path.dirname(__file__),"..","engine"))
import ai

class OrchestratorTests(unittest.TestCase):
 def setUp(self):
  self.oldp=ai.PROVIDERS.copy()
  ai.PROVIDERS={"groq":("GROQ_API_KEY","https://groq.test/v1","openai"),
                "openai":("OPENAI_API_KEY","https://openai.test/v1","openai")}
  os.environ["GROQ_API_KEY"]="g"; os.environ["OPENAI_API_KEY"]="o"
  os.environ["MM_PERSIST_STATE"]="0"
  for k in ("MM_FREE_ONLY","MM_QUOTA_COOLDOWN","MM_PROVIDER_BUDGET_USD_GROQ",
            "MM_PROVIDER_USED_USD_GROQ","MM_STATE_FILE"):
   os.environ.pop(k,None)

 def tearDown(self):
  ai.PROVIDERS=self.oldp
  for k in ("GROQ_API_KEY","OPENAI_API_KEY","MM_FREE_ONLY","MM_QUOTA_COOLDOWN",
            "MM_PROVIDER_BUDGET_USD_GROQ","MM_PROVIDER_USED_USD_GROQ","MM_STATE_FILE",
            "MM_PERSIST_STATE"):
   os.environ.pop(k,None)

 def test_task_aware_discovery(self):
  old=ai._json
  def fake(url,key,method="GET",body=None,headers=None):
   if method=="GET":
    if "groq" in url:return 200,{"data":[{"id":"openai/gpt-oss-120b","context_length":131072}]},{}
    return 200,{"data":[{"id":"gpt-5.6-sol","context_length":1000000}]},{}
   return 200,{"choices":[{"message":{"role":"assistant","content":"ok"}}],"usage":{"prompt_tokens":1,"completion_tokens":1}},{}
  ai._json=fake
  try:
   o=ai.Orchestrator()
   self.assertEqual(o.available()[0].id,"gpt-5.6-sol")
   self.assertEqual(o.candidates("reasoning",3)[0][0].id,"gpt-5.6-sol")
  finally: ai._json=old

 def test_429_cooldown_and_fallback(self):
  old=ai._json; calls=[]
  def fake(url,key,method="GET",body=None,headers=None):
   if method=="GET":
    if "groq" in url: return 200,{"data":[{"id":"gpt-oss-120b","context_length":131072}],},{}
    return 200,{"data":[{"id":"gpt-5.6-sol","context_length":1000000}]},{}
   calls.append(key)
   if key=="o": raise ai.AIError("rate",429,True,{"Retry-After":"17"})
   return 200,{"choices":[{"message":{"role":"assistant","content":"groq"}}],"usage":{}},{"x-ratelimit-remaining-tokens":"8000"}
  ai._json=fake
  try:
   o=ai.Orchestrator(); result=o.call([{"role":"user","content":"x"}],tier=3)
   self.assertEqual(result["message"]["content"],"groq")
   self.assertGreater(o.health["openai"]["cooldown_until"],0)
   self.assertEqual(o.state["providers"]["openai"]["key_cooldowns"]["0"] > 0,True)
   self.assertEqual(o.health["groq"]["quota"]["tokens_remaining"],8000)
   self.assertTrue(any(e["event"]=="fallback" for e in o.events))
  finally: ai._json=old

 def test_budget_excludes_provider(self):
  os.environ["MM_PROVIDER_BUDGET_USD_GROQ"]="1"; os.environ["MM_PROVIDER_USED_USD_GROQ"]="1"
  old=ai._json
  ai._json=lambda url,key,method="GET",body=None,headers=None:(200,{"data":[{"id":"openai/gpt-oss-120b","context_length":131072}]},{})
  try:
   o=ai.Orchestrator(); rows=o.candidates("general",3)
   self.assertFalse([m for m,_ in rows if m.provider=="groq"])  # over its budget
   self.assertTrue([m for m,_ in rows if m.provider=="openai"])  # the other provider still works
  finally: ai._json=old

 def test_quota_zero_excludes_only_exhausted_key(self):
  os.environ["GROQ_API_KEY_1"]="g2"
  old=ai._json
  def fake(url,key,method="GET",body=None,headers=None):
   return 200,{"data":[{"id":"gpt-oss-120b","context_length":131072}]},{
     "x-ratelimit-remaining-requests":"0" if key=="g" else "20",
     "x-ratelimit-remaining-tokens":"0" if key=="g" else "8000"}
  ai._json=fake
  try:
   o=ai.Orchestrator()
   groq=[(m,k) for m,k in o.candidates("general",1) if m.provider=="groq"]
   self.assertEqual(len(groq),1)  # key 0 has no quota left
   self.assertEqual(groq[0][1],1)  # key 1 still does
  finally:
   ai._json=old
   os.environ.pop("GROQ_API_KEY_1",None)

 def test_quota_zero_excludes_provider(self):
  old=ai._json
  def fake(url,key,method="GET",body=None,headers=None):
   return 200,{"data":[{"id":"openai/gpt-oss-120b","context_length":131072}]},{
     "x-ratelimit-remaining-requests":"0","x-ratelimit-remaining-tokens":"0"}
  ai._json=fake
  try:
   o=ai.Orchestrator()
   self.assertEqual(o.candidates("general",1),[])
  finally: ai._json=old

 def test_adaptive_memory_changes_routing(self):
  old=ai._json
  def fake(url,key,method="GET",body=None,headers=None):
   if method=="GET":
    return 200,{"data":[{"id":"gpt-5.6-sol","context_length":1000000}]},{}
   if key=="o":
    return 200,{"choices":[{"message":{"role":"assistant","content":"openai"}}],"usage":{}},{}
   return 200,{"choices":[{"message":{"role":"assistant","content":"groq"}}],"usage":{}},{}
  ai._json=fake
  try:
   o=ai.Orchestrator()
   # Seed a strong historical advantage for Groq.
   o.state["models"]["groq/gpt-5.6-sol"]={"success":20,"failure":0,"latency_ms":10,
                                              "prompt_tokens":0,"completion_tokens":0}
   o.state["models"]["openai/gpt-5.6-sol"]={"success":0,"failure":10,"latency_ms":5000,
                                                "prompt_tokens":0,"completion_tokens":0}
   self.assertEqual(o.candidates("general",3)[0][0].provider,"groq")
  finally: ai._json=old

 def test_state_persists_and_reloads(self):
  old=ai._json
  def fake(url,key,method="GET",body=None,headers=None):
   if method=="GET":
    return 200,{"data":[{"id":"gpt-5.6-sol","context_length":1000000}]},{}
   return 200,{"choices":[{"message":{"role":"assistant","content":"ok"}}],"usage":{"prompt_tokens":3,"completion_tokens":4}},{}
  ai._json=fake
  with tempfile.TemporaryDirectory() as d:
   path=os.path.join(d,"state.json")
   os.environ["MM_PERSIST_STATE"]="1"; os.environ["MM_STATE_FILE"]=path
   try:
    o=ai.Orchestrator()
    served=o.call([{"role":"user","content":"x"}],tier=3)["provider"]+"/gpt-5.6-sol"
    with open(path,encoding="utf8") as f: saved=json.load(f)
    self.assertEqual(saved["models"][served]["success"],1)
    o2=ai.Orchestrator()
    self.assertEqual(o2.state["models"][served]["completion_tokens"],4)
   finally:
    ai._json=old


 def test_waits_for_a_short_rate_limit_instead_of_failing(self):
  os.environ.pop("OPENAI_API_KEY",None)  # only Groq, like a free setup
  clock={"t":1000.0}; old=ai._json; posts=[]
  def fake(url,key,method="GET",body=None,headers=None):
   if method=="GET": return 200,{"data":[{"id":"gpt-oss-120b","context_length":131072}]},{}
   posts.append(clock["t"])
   if len(posts)==1: raise ai.AIError("Rate limit reached. Please try again in 20.5s",429,True)
   return 200,{"choices":[{"message":{"role":"assistant","content":"dopo l'attesa"}}],"usage":{}},{}
  ai._json=fake
  try:
   with unittest.mock.patch.object(ai.time,"time",lambda: clock["t"]):
    o=ai.Orchestrator(); o._sleep=lambda s: clock.__setitem__("t",clock["t"]+s)
    r=o.call([{"role":"user","content":"x"}],tier=3)
   self.assertEqual(r["message"]["content"],"dopo l'attesa")
   self.assertGreaterEqual(posts[1]-posts[0],20.5)  # retried only after the window Groq asked for
   self.assertTrue(any(e["event"]=="wait" for e in o.events))
  finally: ai._json=old

 def test_gives_up_when_the_wait_is_too_long(self):
  os.environ.pop("OPENAI_API_KEY",None); os.environ["MM_RATE_WAIT_MAX"]="30"
  clock={"t":1000.0}; old=ai._json
  def fake(url,key,method="GET",body=None,headers=None):
   if method=="GET": return 200,{"data":[{"id":"gpt-oss-120b","context_length":131072}]},{}
   raise ai.AIError("rate",429,True,{"Retry-After":"600"})
  ai._json=fake
  try:
   with unittest.mock.patch.object(ai.time,"time",lambda: clock["t"]):
    o=ai.Orchestrator(); slept=[]; o._sleep=slept.append
    with self.assertRaises(ai.AIError): o.call([{"role":"user","content":"x"}],tier=3)
   self.assertEqual(slept,[])  # 10 minutes is over the limit: fail fast, the cycle is skipped
  finally:
   ai._json=old; os.environ.pop("MM_RATE_WAIT_MAX",None)

if __name__=="__main__":unittest.main()
