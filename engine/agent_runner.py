#!/usr/bin/env python3
"""Provider-neutral Crypto Machine agent runner."""
from __future__ import annotations
import argparse, glob, json, os, re, shlex, subprocess, sys, urllib.parse, urllib.request
from pathlib import Path
from html.parser import HTMLParser
from ai import Router, AIError

STATS = {"input_tokens": 0, "output_tokens": 0, "models": {}}

ROOT = Path(os.environ.get("MM_ROOT") or Path(__file__).resolve().parents[1]).resolve()
AGENTS, COMMANDS = ROOT / "agents", ROOT / "commands"

def frontmatter(text):
    if not text.startswith("---"): return {}, text
    end = text.find("\n---", 3)
    if end < 0: return {}, text
    meta = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            k, v = line.split(":", 1); meta[k.strip()] = v.strip()
    return meta, text[end + 4:].lstrip()

def load_agent(name):
    return frontmatter((AGENTS / f"{name}.md").read_text(encoding="utf8"))

def load_command(name):
    return frontmatter((COMMANDS / f"{name}.md").read_text(encoding="utf8"))

def tier_for(label):
    x = str(label or "").lower()
    if any(k in x for k in ("opus", "pro", "max", "flagship")): return 4
    if any(k in x for k in ("sonnet", "gpt-5", "reason", "120b", "70b", "72b", "32b")): return 3
    if any(k in x for k in ("haiku", "mini", "flash-lite", "8b", "20b")): return 1
    return 2

def run_mm(args):
    p = subprocess.run([sys.executable, str(ROOT/"engine/mm.py"), *args], cwd=ROOT,
                       text=True, capture_output=True, timeout=120)
    return (p.stdout + p.stderr).strip()

def safe_path(value):
    p = (ROOT / value).resolve() if not os.path.isabs(value) else Path(value).resolve()
    if p != ROOT and ROOT not in p.parents: raise RuntimeError("path fuori dal repository")
    return p

class SearchParser(HTMLParser):
    def __init__(self): super().__init__(); self.links=[]; self.in_a=False; self.buf=[]; self.href=""
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            d = dict(attrs); self.href = d.get("href",""); self.in_a=True; self.buf=[]
    def handle_data(self, data):
        if self.in_a: self.buf.append(data)
    def handle_endtag(self, tag):
        if tag == "a" and self.in_a:
            title = " ".join("".join(self.buf).split())
            if title and self.href: self.links.append((title,self.href))
            self.in_a=False

def web_search(query, limit=5):
    url = "https://www.google.com/search?" + urllib.parse.urlencode({"q":query,"num":limit})
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 Money-Machine/2"})
        with urllib.request.urlopen(req,timeout=15) as r: raw=r.read().decode("utf8","replace")
        p=SearchParser(); p.feed(raw); out=[]
        for title,href in p.links:
            if href.startswith("/url?q="):
                href=urllib.parse.parse_qs(urllib.parse.urlsplit(href).query).get("q",[href])[0]
            if href.startswith("http") and "google." not in href:
                out.append({"title":title,"url":href})
            if len(out)>=limit: break
        return json.dumps(out,ensure_ascii=False)
    except Exception as e: return json.dumps({"error":str(e)})

def tool(name,args,allowed):
    if name not in allowed: return "ERRORE: tool non autorizzato"
    try:
        if name=="read": return safe_path(args["path"]).read_text(encoding="utf8")[:120000]
        if name=="write":
            p=safe_path(args["path"]); p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text(args.get("content",""),encoding="utf8"); return f"scritto {p.relative_to(ROOT)}"
        if name=="edit":
            p=safe_path(args["path"]); s=p.read_text(encoding="utf8"); old=args.get("old","")
            if old not in s: return "ERRORE: testo da sostituire non trovato"
            p.write_text(s.replace(old,args.get("new",""),1),encoding="utf8"); return f"modificato {p.relative_to(ROOT)}"
        if name=="glob":
            vals=[str(Path(x).relative_to(ROOT)) for x in glob.glob(str(ROOT/args.get("pattern","**/*")),recursive=True) if Path(x).is_file()]
            return "\n".join(vals[:500])
        if name=="grep":
            needle=args.get("pattern","").lower(); out=[]
            for x in glob.glob(str(ROOT/args.get("glob","**/*")),recursive=True):
                p=Path(x)
                if not p.is_file() or p.stat().st_size>2_000_000: continue
                try: text=p.read_text(encoding="utf8")
                except Exception: continue
                for i,line in enumerate(text.splitlines(),1):
                    if needle in line.lower():
                        out.append(f"{p.relative_to(ROOT)}:{i}:{line[:300]}")
                        if len(out)>=300:return "\n".join(out)
            return "\n".join(out)
        if name=="bash":
            cmd=args.get("command",""); toks=shlex.split(cmd)
            if not toks: return "ERRORE: comando vuoto"
            if toks[0] not in {"mm","python3","ls","mkdir","cat","pwd","find","printf","echo"}:
                return "ERRORE: comando shell non consentito"
            env={**os.environ,"MM_ROOT":str(ROOT),"PATH":str(ROOT/"bin")+os.pathsep+os.environ.get("PATH","")}
            p=subprocess.run(cmd,shell=True,cwd=ROOT,text=True,capture_output=True,timeout=120,env=env)
            return (p.stdout+p.stderr).strip()[:20000]
        if name=="web_search": return web_search(args.get("query",""),int(args.get("limit",5)))
        if name=="web_fetch":
            req=urllib.request.Request(args["url"],headers={"User-Agent":"Mozilla/5.0 Money-Machine/2"})
            with urllib.request.urlopen(req,timeout=20) as r: data=r.read().decode("utf8","replace")
            return re.sub(r"\s+"," ",data)[:30000]
    except Exception as e: return "ERRORE: "+str(e)
    return "ERRORE: tool sconosciuto"

def schemas(allowed):
    d={
      "read":("Leggi un file del repository",{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}),
      "write":("Scrivi un file del repository",{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}),
      "edit":("Sostituisci una sola occorrenza",{"type":"object","properties":{"path":{"type":"string"},"old":{"type":"string"},"new":{"type":"string"}},"required":["path","old","new"]}),
      "glob":("Trova file",{"type":"object","properties":{"pattern":{"type":"string"}},"required":["pattern"]}),
      "grep":("Cerca testo",{"type":"object","properties":{"pattern":{"type":"string"},"glob":{"type":"string"}},"required":["pattern"]}),
      "bash":("Esegui un comando shell consentito",{"type":"object","properties":{"command":{"type":"string"}},"required":["command"]}),
      "web_search":("Cerca sul web",{"type":"object","properties":{"query":{"type":"string"},"limit":{"type":"integer"}},"required":["query"]}),
      "web_fetch":("Scarica una pagina pubblica",{"type":"object","properties":{"url":{"type":"string"}},"required":["url"]})
    }
    return [{"type":"function","function":{"name":n,"description":desc,"parameters":par}} for n,(desc,par) in d.items() if n in allowed]

def allowed_tools(meta):
    m={"Read":"read","Write":"write","Edit":"edit","Glob":"glob","Grep":"grep","Bash":"bash","WebSearch":"web_search","WebFetch":"web_fetch"}
    return {m[x.strip()] for x in meta.get("tools","").split(",") if x.strip() in m}

def delegate(router,name,prompt,depth):
    if depth>=2: return "ERRORE: profondità deleghe massima"
    meta,body=load_agent(name)
    return agent_loop(router,name,meta,body,prompt,depth+1)

def agent_loop(router,name,meta,body,user_prompt,depth=0):
    allowed=allowed_tools(meta)
    system=f"""Sei l'agente {name} della Crypto Machine.

{body}

ROOT: {ROOT}
Usa esclusivamente i tool concessi. Non inventare dati. Le azioni esterne richiedono le approvazioni previste dalla POLICY. Rispondi in modo conciso."""
    messages=[{"role":"system","content":system},{"role":"user","content":user_prompt}]
    tools=schemas(allowed)
    # Agent/Task are implemented by this runner, not by a provider-specific API.
    if "Agent" in meta.get("tools","") or "Task" in meta.get("tools",""):
        tools.append({"type":"function","function":{"name":"delegate","description":"Delega a un sub-agente Crypto Machine",
          "parameters":{"type":"object","properties":{"agent":{"type":"string"},"prompt":{"type":"string"}},"required":["agent","prompt"]}}})
    tier=tier_for(meta.get("model"))
    if name=="ceo" or name.endswith("-lead"): tier=max(tier,3)
    for _ in range(int(os.getenv("MM_MAX_TURNS","40"))):
        res=router.call(messages,tools=tools,tier=tier,max_tokens=int(os.getenv("MM_MAX_OUTPUT_TOKENS","4096")))
        usage=res.get("usage") or {}
        STATS["input_tokens"] += int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        STATS["output_tokens"] += int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        key=f'{res.get("provider","unknown")}/{res.get("model","unknown")}'
        mu=STATS["models"].setdefault(key, {"inputTokens":0,"outputTokens":0,"costUSD":0})
        mu["inputTokens"] += int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        mu["outputTokens"] += int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        msg=res["message"]; messages.append(msg); calls=msg.get("tool_calls") or []
        if not calls:return msg.get("content","")
        for call in calls:
            fn=call.get("function",{}); fname=fn.get("name")
            try: args=json.loads(fn.get("arguments") or "{}")
            except Exception: args={}
            if fname=="delegate":
                result=delegate(router,args.get("agent","").replace("crypto-machine:",""),args.get("prompt",""),depth)
            else: result=tool(fname,args,allowed)
            messages.append({"role":"tool","tool_call_id":call.get("id",fname),"name":fname,"content":str(result)[:30000]})
    return "STOP: limite turn raggiunto."

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--command",default=os.getenv("MM_COMMAND","/crypto-machine:cycle"))
    ap.add_argument("--list-models",action="store_true")
    args=ap.parse_args()
    router=Router()
    if args.list_models:
        print(json.dumps([m.__dict__ for m in router.available()],ensure_ascii=False,indent=2)); return 0
    command=args.command.split()[0].replace("/crypto-machine:","")
    load_command(command)
    head={"cycle":"ceo","risk-manager":"yield-lead","social":"social-lead"}.get(command,"ceo")
    brief_cmd={"cycle":["begin-cycle"],"risk-manager":["growth-brief"],"social":["social-brief"]}.get(command,["brief"])
    run_mm(["apply"])
    brief="\n".join(run_mm(x) for x in brief_cmd)
    prompt=load_command(command)[1]+"\n\nBRIEF ATTUALE:\n"+brief
    if os.getenv("MM_EXTRA_PROMPT"): prompt+="\n\nISTRUZIONI EXTRA:\n"+os.getenv("MM_EXTRA_PROMPT")
    result=agent_loop(router,head,*load_agent(head),prompt)
    print(json.dumps({"type":"result","result":result[:10000],
                      "total_cost_usd":float(os.getenv("MM_REPORTED_COST_USD","0") or 0),
                      "usage":{"input_tokens":STATS["input_tokens"],"output_tokens":STATS["output_tokens"]},
                      "modelUsage":STATS["models"]},ensure_ascii=False))
    return 0
if __name__=="__main__": raise SystemExit(main())
