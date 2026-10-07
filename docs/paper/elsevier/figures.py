#!/usr/bin/env python3
"""Paper figures and explanatory statistics from retained measurements.

No histograms, generated performance data, or cross-paper speed rankings.
All representative traces are selected by run-level whole-window throughput.
"""
import csv
import json
import math
import statistics as st
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE / "analysis"
plt.rcParams.update({"font.size": 9, "pdf.fonttype": 42, "svg.fonttype": "none",
                     "axes.spines.top": False, "axes.spines.right": False})
COLORS = {"latency": "#0072B2", "throughput": "#D55E00", "auto-fixed": "#009E73",
          "auto-remaining": "#CC79A7", "static": "#555555", "hysteresis": "#0072B2",
          "gate": "#009E73", "gate-force": "#CC79A7"}
DATA = []
REGISTER = []


def read_csv(p):
    with p.open(newline="") as f:
        return list(csv.DictReader(f))


def save(fig, name, evidence, source):
    for ext in ("pdf", "svg", "png"):
        fig.savefig(HERE / f"{name}.{ext}", dpi=180, bbox_inches="tight")
    plt.close(fig)
    REGISTER.append({"figure": name, "evidence": evidence, "sources": source})


def detail(r):
    p = ROOT / r["source_meta"]
    m = json.loads(p.read_text())
    return m, read_csv(p.parent / "requests.csv"), read_csv(p.parent / "series.csv"), json.loads((p.parent / "decisions.json").read_text())


def timestamp(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


def representative(rs):
    middle = st.median(float(r["throughput_tps"]) for r in rs)
    return min(rs, key=lambda r: (abs(float(r["throughput_tps"]) - middle), r["run"]))


def architecture():
    fig, ax = plt.subplots(figsize=(10.5, 4.8))
    ax.set(xlim=(0, 10.7), ylim=(-.3, 4.9)); ax.axis("off")
    def box(x, y, w, h, title, color):
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=.08",fc=color,ec="#555555",lw=1))
        ax.text(x+w/2,y+h/2,title,ha="center",va="center",fontsize=8.5)
    def arrow(a,b,text="",color="#333333",style="->",label_y=.14):
        ax.add_patch(FancyArrowPatch(a,b,arrowstyle=style,mutation_scale=12,color=color,lw=1.3))
        if text:ax.text((a[0]+b[0])/2,(a[1]+b[1])/2+label_y,text,ha="center",fontsize=7.5,color=color)
    box(.15,3.1,1.7,.75,"Client\ntoken IDs + budget", "#eeeeee")
    box(2.6,3.1,1.9,.75,"Router (vm1)\nrequest KV identity", "#d9e8f3")
    box(5.7,3.35,2.45,.75,"Local CPU worker (vm1)\ncontiguous shard", "#fff0d9")
    box(5.7,1.85,2.45,.75,"Remote CPU worker (vm2)\ncontiguous shard", "#fff0d9")
    box(2.6,.5,1.9,.8,"Controller (vm1)\nDP + transition gate", "#dff0e4")
    box(8.3,.5,2.2,.8,"Node agents\nCPU speed + TCP SRTT", "#eeeeee")
    arrow((1.85,3.48),(2.6,3.48),style="<->")
    arrow((4.5,3.65),(5.7,3.72),"RPC + reply",style="<->")
    arrow((4.5,3.22),(5.7,2.23),"RPC + reply",style="<->",label_y=-.27)
    arrow((3.9,3.1),(3.9,1.3),color="#0072B2")
    ax.text(4.0,2.13,"active /\nremaining",fontsize=7.5,color="#0072B2",va="center")
    arrow((2.8,1.3),(2.8,3.1),color="#009E73")
    ax.text(2.7,2.13,"layout +\ngeneration",fontsize=7.5,color="#009E73",ha="right",va="center")
    arrow((8.3,.9),(4.5,.9),"telemetry", "#009E73")
    ax.text(5.35,4.6,"Standalone controller and router-mediated inference",ha="center",weight="bold")
    ax.text(5.35,-.1,"Control paths are schematic. Each worker retains its request-specific KV caches.",ha="center",fontsize=8)
    save(fig,"architecture","Implementation diagram; not a measured performance graph",["worker/router.py","internal/controller/controller.go"])


def frontier(runs):
    fig,axs=plt.subplots(1,2,figsize=(9,3.6),constrained_layout=True)
    for ax,scenario in zip(axs,("stable","network")):
        for arm in ("latency","throughput"):
            for q,marker in ((1,"o"),(2,"s")):
                rs=[r for r in runs if r["matrix"]=="objective" and r["scenario"]==scenario and r["arm"]==arm and int(r["concurrency"])==q]
                xs=[float(r["client_p50_ms"])/1000 for r in rs]; ys=[float(r["throughput_tps"]) for r in rs]
                ax.scatter(xs,ys,c=COLORS[arm],marker=marker,s=35,label=f"{arm}, Q={q}")
        ax.set(title="Stable" if scenario=="stable" else "+120 ms network perturbation",
               xlabel="Run median client completion (s; lower is better)",ylabel="Output tokens/s (higher is better)")
        ax.grid(alpha=.15); ax.legend(fontsize=7)
    save(fig,"objective-frontier","Real-model CPU runs; every run shown",["analysis/per-run.csv"])


def envelope(runs):
    fig,axs=plt.subplots(1,2,figsize=(8.8,3.3),constrained_layout=True)
    for ax,arm in zip(axs,("latency","throughput")):
        for q in (1,2):
            rs=[r for r in runs if r["matrix"]=="objective" and r["scenario"]=="stable" and r["arm"]==arm and int(r["concurrency"])==q]
            predicted=[]; measured=[]
            for r in rs:
                m,_,_,_=detail(r)
                p=m["initial_state"]["pipeline_ms"]; b=m["initial_state"]["bottleneck_ms"]
                proxy=min(1000/b,q*1000/p); obs=float(r["throughput_tps"])
                predicted.append(proxy);measured.append(obs)
                DATA.append({"analysis":"service-envelope","run":r["run"],"q":q,"proxy_tps":proxy,"observed_tps":obs,"observed_over_proxy":obs/proxy})
            ax.scatter([q]*len(rs),measured,color=COLORS[arm],s=24,zorder=4)
            ax.scatter([q]*len(rs),predicted,facecolors="none",edgecolors="black",marker="D",s=40,zorder=3)
        ax.plot([1,2],[st.median(x["observed_tps"] for x in DATA if x["analysis"]=="service-envelope" and x["q"]==q and x["run"] in {r["run"] for r in runs if r["arm"]==arm}) for q in (1,2)],color=COLORS[arm])
        ax.set(title=f"{arm.capitalize()} placement",xlabel="Closed-loop concurrency Q",ylabel="Output tokens/s",xticks=[1,2],ylim=(0,10))
        ax.text(.04,.95,"Filled: observed\nOpen diamonds: startup-profile proxy",transform=ax.transAxes,va="top",fontsize=8)
    save(fig,"service-envelope","Real outcomes versus ideal stationary-model proxy; not a calibrated guarantee",["raw/objective/*/meta.json","analysis/per-run.csv"])


def adaptation(runs):
    fig,axs=plt.subplots(1,2,figsize=(9,3.7),constrained_layout=True)
    for ax,sc in zip(axs,("compute","network")):
        ref={int(r["repeat"]):r for r in runs if r["matrix"]=="vm" and r["scenario"]==sc and r["arm"]=="static"}
        for arm in ("hysteresis","gate","gate-force"):
            rs=[r for r in runs if r["matrix"]=="vm" and r["scenario"]==sc and r["arm"]==arm]
            for r in rs:
                b=ref[int(r["repeat"])]; vals=[100*(float(r[k])/float(b[k])-1) for k in ("fault_completion_tps","throughput_tps")]
                ax.plot([0,1],vals,color=COLORS[arm],marker="o",alpha=.4,linewidth=1)
            medians=[st.median(100*(float(r[k])/float(ref[int(r["repeat"])][k])-1) for r in rs) for k in ("fault_completion_tps","throughput_tps")]
            ax.plot([0,1],medians,color=COLORS[arm],marker="D",linewidth=2,label=arm)
        ax.axhline(0,color="black",ls=":",lw=1);ax.set(title="CPU quota 0.5" if sc=="compute" else "+120 ms network delay",xticks=[0,1],xticklabels=["Fault-phase completions","Whole run + drain"],ylabel="Relative throughput change vs static (%)",ylim=(-15,30));ax.legend(fontsize=8);ax.grid(alpha=.15)
    save(fig,"adaptation-comparison","Real run-level repeat-matched contrasts; lines are not confidence intervals",["analysis/per-run.csv"])


def demand(runs):
    fig,axs=plt.subplots(3,2,figsize=(10,7),constrained_layout=True,sharex=True)
    stats=[]
    for repeat in (1,2):
        col=repeat-1
        for arm in ("throughput","auto-fixed","auto-remaining"):
            r=next(r for r in runs if r["matrix"]=="demand" and int(r["concurrency"])==2 and int(r["repeat"])==repeat and r["arm"]==arm)
            m,rq,series,dec=detail(r);rq=sorted(rq,key=lambda r:float(r["t_end"]))
            ts=[0]; tokens=[0]
            for req in rq:
                ts.append(float(req["t_end"])-m["t0"]);tokens.append(tokens[-1]+(int(req["tokens"]) if req["ok"]=="1" else 0))
            axs[0,col].step(ts,tokens,where="post",color=COLORS[arm],label=arm)
            if arm!="throughput":
                budgets=[(float(s["t"])-m["t0"],json.loads(s["workload_json"])["remaining_tokens"]) for s in series if s.get("workload_json") and json.loads(s["workload_json"]) is not None]
                axs[1,col].plot([t for t,_ in budgets],[b for _,b in budgets],color=COLORS[arm],label=arm)
            for d in dec:
                if d["reason"]=="recovery-or-initial":continue
                t=timestamp(d["time"])-m["t0"]
                axs[2,col].scatter(t,d.get("horizon_s",30),color=COLORS[arm],marker="o" if d["executed"] else "x",s=40)
                if d["executed"]:axs[0,col].axvline(t,color=COLORS[arm],alpha=.4,ls=":")
            moves=[d for d in dec if d["reason"]!="recovery-or-initial" and d["executed"]]
            initial=dec[0]
            for d in moves:
                stats.append({"run":r["run"],"arm":arm,"repeat":repeat,"move_after_measurement_start_s":timestamp(d["time"])-m["t0"],"move_after_initial_assignment_s":timestamp(d["time"])-timestamp(initial["time"]),"horizon_s":d.get("horizon_s"),"remaining_tokens":d.get("remaining_tokens")})
        axs[0,col].set(title=f"Demand matrix, Q=2, repeat {repeat}",ylabel="Tokens attributed at completion");axs[0,col].legend(fontsize=7)
        axs[1,col].set(ylabel="Observed remaining-token budget")
        axs[2,col].set(ylabel="Candidate horizon (s)",xlabel="Time since measurement start (s)",ylim=(0,33))
        axs[2,col].text(.02,.95,"Circle: executed; cross: rejected",transform=axs[2,col].transAxes,fontsize=8,va="top")
        for ax in axs[:,col]:ax.axvline(60,color="black",ls="--",alpha=.4);ax.grid(alpha=.15)
    (OUT/"demand-move-timing.json").write_text(json.dumps(stats,indent=2)+"\n")
    save(fig,"demand-timeline","Both actual repeat blocks; no inferred token-emission timestamps",["raw/demand/*/{requests,series,decisions,meta}"])


def fault_traces(runs):
    fig,axs=plt.subplots(1,3,figsize=(11,3.4),constrained_layout=True)
    chosen=[]
    for ax,sc in zip(axs,("compute","network","loss")):
        for arm in ("static","hysteresis","gate"):
            r=representative([r for r in runs if r["matrix"]=="vm" and r["scenario"]==sc and r["arm"]==arm]);chosen.append(r["run"])
            m,rq,_,_=detail(r);fault=read_csv((ROOT/r["source_meta"]).parent/"faults.csv")
            onset=next(float(x["t_local"]) for x in fault if x["action"]=="on");off=next(float(x["t_local"]) for x in fault if x["action"]=="off")
            ts=[m["t0"]-onset];tokens=[0]
            for req in sorted(rq,key=lambda x:float(x["t_end"])):
                ts.append(float(req["t_end"])-onset);tokens.append(tokens[-1]+(int(req["tokens"]) if req["ok"]=="1" else 0))
                if req["ok"]!="1":ax.plot(ts[-1],tokens[-1],"x",color=COLORS[arm],markersize=5)
            ax.step(ts,tokens,where="post",color=COLORS[arm],label=arm)
            ax.axvline(off-onset,color=COLORS[arm],ls=":",alpha=.25)
        ax.axvline(0,color="black",ls="--",lw=1);ax.set(title=sc.capitalize(),xlabel="Time relative to fault onset (s)",ylabel="Successful completion-attributed tokens");ax.legend(fontsize=7);ax.grid(alpha=.15)
    (OUT/"representative-traces.json").write_text(json.dumps({"rule":"closest to arm median whole-run throughput, ties by run name","runs":chosen},indent=2)+"\n")
    save(fig,"fault-traces","Descriptive real traces; one deterministic representative per arm/scenario",["raw/vm/*/{requests,faults,meta}"])


def cost_gate():
    base=ROOT/"docs/data/paper-ablations-2026-10-04/decision-results"
    costs=read_csv(base/"cost-model.csv");policies=read_csv(base/"policy.csv")
    fig,axs=plt.subplots(1,2,figsize=(9,3.6),constrained_layout=True)
    variants=[("true","true","Full cost model"),("false","true","Omit endpoints"),("true","false","Freeze context"),("false","false","Omit both")]
    for e,c,label in variants:
        rs=sorted([r for r in costs if r["speed_b"]=="1" and r["link_ms"]=="0.5" and r["endpoints"]==e and r["context_table"]==c],key=lambda x:int(x["context"]))
        axs[0].plot([int(r["context"]) for r in rs],[100*float(r["reference_regret_frac"]) for r in rs],marker="o",label=label)
    for margin in ("0","0.13"):
        rs=sorted([r for r in policies if r["speed_b"]=="0.7" and r["link_ms"]=="0.5" and r["horizon_s"]=="30" and r["margin"]==margin and r["transition_model"]=="full-chain" and r["policy"]=="gate"],key=lambda x:int(x["context"]))
        assert len(rs)==4, (margin, len(rs))
        ys=[float(r["margin_acceptance_boundary_s"]) for r in rs]
        axs[1].plot([int(r["context"]) for r in rs],ys,marker="o",label=f"Margin {float(margin):.0%}")
        for r,y in zip(rs,ys):
            if (float(r["current_ms"])-float(r["optimal_ms"]))/float(r["current_ms"])<=.15:
                axs[1].scatter(int(r["context"]),y,marker="x",s=80,color="black",zorder=5)
    axs[0].set(xlabel="Context tokens",ylabel="Common-reference bottleneck regret (%)",title="Placement cost ablation (model only)")
    axs[1].axhline(30,color="black",ls=":",label="30-s horizon");axs[1].set(xlabel="Context tokens",ylabel="Model gate boundary (s)",title="Full-chain replay, speed B = 0.7")
    for ax in axs:ax.legend(fontsize=7);ax.grid(alpha=.15)
    axs[1].text(.03,.95,"Cross: ineligible under 15% threshold",transform=axs[1].transAxes,fontsize=7,va="top")
    save(fig,"cost-and-gate-sensitivity","Analytical quantities, historical profile; not hardware speedup",[str(base.relative_to(ROOT))])


def queue_routing():
    base=ROOT/"docs/data/paper-ablations-2026-10-04"
    q=read_csv(base/"queue-results/aggregate.csv")
    fig,axs=plt.subplots(1,2,figsize=(9,3.6),constrained_layout=True)
    for ax,service in zip(axs,(5,50)):
        rs=sorted([r for r in q if int(r["service_ms"])==service and r["mode"]=="direct"],key=lambda x:int(x["concurrency"]))
        for k,label in (("mean_residual_ms","RPC minus compute"),("mean_server_lock_wait_ms","Worker lock wait"),("mean_queue_corrected_residual_ms","Queue-corrected residual")):
            ax.plot([int(r["concurrency"]) for r in rs],[float(r[k]) for r in rs],marker="o",label=label)
        ax.set(xlabel="Concurrency",ylabel="Equal-weight window mean (ms)",title=f"Synthetic service {service} ms",xticks=[1,2,4]);ax.legend(fontsize=7);ax.grid(alpha=.15)
    save(fig,"queue-decomposition","Synthetic loopback measurements; window-level means",[str((base/"queue-results/aggregate.csv").relative_to(ROOT))])
    b=ROOT/"docs/data/product-direction-2026-10-04"
    r=read_csv(b/"aggregate.csv")
    fig,axs=plt.subplots(1,3,figsize=(10,3.3),constrained_layout=True)
    for ax,w in zip(axs,(1,2,3)):
        for mode in ("pipeline","replicas"):
            rs=sorted([x for x in r if int(x["workers"])==w and x["mode"]==mode],key=lambda x:int(x["concurrency"]))
            ax.plot([int(x["concurrency"]) for x in rs],[float(x["mean_tokens_per_s"]) for x in rs],marker="o",label=mode + (" (cyclic)" if mode=="replicas" else ""))
        if w==3:
            for folder,marker,label in (("routing-baseline","s","Available replica"),("fifo-baseline","D","Available + FIFO")):
                row=next(x for x in read_csv(b/folder/"aggregate.csv") if x["mode"]=="replicas")
                ax.scatter(4,float(row["mean_tokens_per_s"]),marker=marker,s=50,label=label,zorder=5)
        ax.set(title=f"{w} worker(s)",xlabel="Concurrency",ylabel="Output tokens/s",xticks=[1,2,4]);ax.legend(fontsize=6.5);ax.grid(alpha=.15)
    save(fig,"routing-sensitivity","Synthetic simulator; follow-ups were separate exploratory windows",[str(b.relative_to(ROOT))])


def forecast():
    p=ROOT/"docs/data/azure-vm-2026-10-04/replay/input.json"
    observations=json.loads(p.read_text())["Observations"]
    fig,ax=plt.subplots(figsize=(6.5,3.5),constrained_layout=True)
    for sc in ("compute","network"):
        xs=sorted(o["Ms"]/1000 for o in observations if o["Scenario"]==sc)
        ax.step(xs,[(i+1)/len(xs) for i in range(len(xs))],where="post",label=f"{sc}, {len(xs)} grouped observations")
    ax.axvline(3.0542528,color="black",ls="--",label="Profile forecast at C=128")
    ax.set(xlabel="Approximate measured disruption per grouped transition (s)",ylabel="Empirical cumulative fraction",ylim=(0,1.04),title="Transition forecasts versus recorded disruptions")
    ax.legend(fontsize=8);ax.grid(alpha=.15)
    save(fig,"transition-forecast","Approximate event attribution, not independent trials or forecast confidence",[str(p.relative_to(ROOT))])


def main():
    runs=read_csv(OUT/"per-run.csv")
    assert len(runs)==65
    architecture();frontier(runs);envelope(runs);adaptation(runs);demand(runs);fault_traces(runs);cost_gate();queue_routing();forecast()
    (OUT/"figure-provenance.json").write_text(json.dumps(REGISTER,indent=2)+"\n")
    (OUT/"capacity-proxy.json").write_text(json.dumps(DATA,indent=2)+"\n")
    print(f"Generated {len(REGISTER)} source-labelled figures.")


if __name__=="__main__":main()
