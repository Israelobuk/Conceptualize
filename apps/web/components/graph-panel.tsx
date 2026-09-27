"use client";
import { useState, useRef, useEffect } from "react";
import dynamic from "next/dynamic";
import { Filter, Maximize, Minimize, X } from "lucide-react";
import type { ProjectGraph } from "@/lib/types";
const DependencyGraph=dynamic(()=>import("./dependency-graph"),{ssr:false,loading:()=> <div className="graph-canvas panel-empty">Loading context graph…</div>});
export default function GraphPanel({graph,selected,onSelect,large=false}:{graph:ProjectGraph|null;selected:string;onSelect:(p:string)=>void;large?:boolean}) {
  const [mode,setMode]=useState<"tree"|"dependencies">("tree");
  const [filterOpen,setFilterOpen]=useState(false);
  const [filter,setFilter]=useState("");
  const [fullscreen,setFullscreen]=useState(false);
  const ref=useRef<HTMLElement>(null);
  useEffect(()=>{const onChange=()=>setFullscreen(document.fullscreenElement===ref.current);document.addEventListener("fullscreenchange",onChange);return()=>document.removeEventListener("fullscreenchange",onChange);},[]);
  const folders=[...new Set(graph?.nodes.filter(n=>n.kind==="file"&&n.id.includes("/")).map(n=>n.id.split("/")[0]))];
  async function toggleFullscreen(){if(document.fullscreenElement)await document.exitFullscreen();else await ref.current?.requestFullscreen();}
  return <section ref={ref} className={`panel context-graph-panel${large?" large-graph":""}${fullscreen?" graph-fullscreen":""}`}>
    <div className="panel-heading"><div><h2>Project context graph</h2><p>Structural view of your repository</p></div><div className="graph-toolbar"><span>View</span><label><span className="sr-only">Graph view</span><select value={mode} onChange={e=>setMode(e.target.value as typeof mode)}><option value="tree">File tree</option><option value="dependencies">Dependencies</option></select></label><button className={filterOpen?"control-button active":"control-button"} title="Filter graph" aria-label="Filter graph" aria-expanded={filterOpen} onClick={()=>setFilterOpen(!filterOpen)}><Filter size={15}/></button><button className="control-button" aria-label={fullscreen?"Exit graph fullscreen":"Graph fullscreen"} onClick={()=>void toggleFullscreen()}>{fullscreen?<Minimize size={15}/>:<Maximize size={15}/>}</button></div></div>
    {filterOpen && <div className="graph-filter"><label>Project area <select aria-label="Graph area" value={filter} onChange={e=>setFilter(e.target.value)}><option value="">All folders</option>{folders.map(f=><option key={f}>{f}</option>)}</select></label>{filter && <button className="icon-button" aria-label="Clear graph filter" onClick={()=>setFilter("")}><X size={13}/></button>}</div>}
    {graph?<DependencyGraph graph={graph} selected={selected} onSelect={onSelect} mode={mode} filter={filter}/>:<div className="graph-canvas panel-empty">Loading project structure…</div>}
    <div className="graph-footer"><span>{selected||"Repository overview"}</span><span>{graph?.truncated?`Showing part of ${graph.total_nodes} indexed nodes`:"Click a node to inspect context"}</span></div>
  </section>;
}
