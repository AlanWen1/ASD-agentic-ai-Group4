"""Terminal client for the local Multi-Agent workflow."""
import argparse, json, os, sys
from pathlib import Path
import requests

DEFAULT_URL=os.getenv("MULTI_AGENT_URL","http://127.0.0.1:5102").rstrip("/")
DEFAULT_KEY=os.getenv("MULTI_AGENT_API_KEY","local-dev-key-change-me")

def request_json(method,url,**kwargs):
    headers=dict(kwargs.pop("headers",{}) or {}); headers["X-Multi-Agent-Key"]=DEFAULT_KEY
    try: response=requests.request(method,url,headers=headers,timeout=kwargs.pop("timeout",420),**kwargs)
    except requests.RequestException as exc: raise RuntimeError(f"Cannot connect to {DEFAULT_URL}. Start it with ./run_local.sh first. {exc}") from exc
    try: data=response.json()
    except ValueError: data={"error":response.text or f"HTTP {response.status_code}"}
    if not response.ok: raise RuntimeError(data.get("error",f"HTTP {response.status_code}"))
    return data

def show_review(run):
    print("\n"+"="*72); print("RUN:",run["run_id"],"| MODULE:",run["module"],"| STATUS:",run["status"])
    print("\nPLANNER PLAN"); print(json.dumps(run.get("plan") or {},indent=2,ensure_ascii=False))
    print("\nWORKER PROPOSAL\n"+str(run.get("worker_output") or "(empty)"))
    print("\nREVIEWER ASSESSMENT"); print(json.dumps(run.get("review") or {},indent=2,ensure_ascii=False))
    print("\nHuman decision required: [a]pprove, [c]orrect, [r]eject")

def main():
    parser=argparse.ArgumentParser(description="Run Planner -> Worker -> Reviewer with mandatory human review.")
    parser.add_argument("--module",required=True,choices=["budget","expenses","income","bills","savings"])
    parser.add_argument("--task",required=True); parser.add_argument("--evidence-file")
    parser.add_argument("--evidence-json"); parser.add_argument("--user-id",default="terminal")
    parser.add_argument("--url",default=DEFAULT_URL); args=parser.parse_args()
    if args.evidence_file and args.evidence_json: parser.error("use either --evidence-file or --evidence-json, not both")
    try:
        if args.evidence_file: evidence=json.loads(Path(args.evidence_file).read_text(encoding="utf-8"))
        elif args.evidence_json: evidence=json.loads(args.evidence_json)
        else: evidence={"note":"No application evidence was supplied. Identify evidence gaps and do not invent account data."}
        url=args.url.rstrip("/")
        run=request_json("POST",url+"/runs",json={"module":args.module,"task":args.task,"evidence":evidence,"user_id":args.user_id})
        while True:
            show_review(run); action=input("\nChoose a/c/r: ").strip().lower()
            if action in {"a","approve"}:
                run=request_json("POST",url+"/runs/"+run["run_id"]+"/decision",json={"module":args.module,"user_id":args.user_id,"decision":"approve"})
                print("\nApproved by human. Final status:",run["status"]); return 0
            if action in {"r","reject"}:
                feedback=input("Reason for rejection (optional): ").strip()
                run=request_json("POST",url+"/runs/"+run["run_id"]+"/decision",json={"module":args.module,"user_id":args.user_id,"decision":"reject","feedback":feedback})
                print("\nRejected by human. Final status:",run["status"]); return 0
            if action in {"c","correct"}:
                feedback=input("What should the Worker correct or reconsider? ").strip()
                if not feedback: print("Correction feedback cannot be empty.",file=sys.stderr); continue
                run=request_json("POST",url+"/runs/"+run["run_id"]+"/decision",json={"module":args.module,"user_id":args.user_id,"decision":"correct","feedback":feedback})
                if run["status"]!="awaiting_human_review": print("Correction did not return a reviewable result:",run["status"]); return 1
                continue
            print("Enter a for approve, c for correction, or r for reject.")
    except (OSError,json.JSONDecodeError,RuntimeError) as exc:
        print("Error:",exc,file=sys.stderr); return 1
if __name__=="__main__": raise SystemExit(main())