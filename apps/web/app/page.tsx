"use client";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Activity, ArrowDown, ArrowRight, ArrowUp, Box, CalendarDays, Check, ChevronDown, CircleDot, FileCode2, Folder, GitBranch, Github, Layers, RefreshCw, Search, Settings2, Terminal, Workflow, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import GraphPanel from "@/components/graph-panel";
import RepositoryTree from "@/components/repository-tree";
import TracePanel from "@/components/trace-panel";
import { activityBars, compactNumber, filterActivity, formatNumber, inputLabel, periodMetrics, relativeTime, type Range } from "@/lib/dashboard-data";
import type { GitInfo, Overview, ProjectGraph, Trace, TraceDetail } from "@/lib/types";

type View="overview"|"activity"|"graph"|"repository"|"traces"|"settings";
type Inspection={context:string;included_files:string[];relationships:{source:string;target:string;kind:string}[];metrics:{returned_tokens:number;token_budget:number};trace_id:string;operation:string};
const navigation=[{key:"overview",label:"Overview",icon:Layers},{key:"activity",label:"Agent activity",icon:Activity},{key:"graph",label:"Context graph",icon:GitBranch},{key:"repository",label:"Repository",icon:FileCode2},{key:"traces",label:"Traces",icon:Workflow},{key:"settings",label:"Settings",icon:Settings2}] as const;
const opIcons:Record<string,typeof Box>={map:Layers,search:Search,dependencies:GitBranch,expand:FileCode2,pack:Box};
async function api<T>(path:string,body?:unknown):Promise<T>{
 const response=await fetch("/api/"+path,{cache:"no-store",...(body?{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}:{})});
 const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==="string"?data.detail:"Context request failed");return data;
}
export default function Dashboard(){
 const [view,setView]=useState<View>("overview");
 const [overview,setOverview]=useState<Overview|null>(null);
 const [traces,setTraces]=useState<Trace[]>([]);
 const [graph,setGraph]=useState<ProjectGraph|null>(null);
 const [git,setGit]=useState<GitInfo>({});
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState("");
 const [range,setRange]=useState<Range>("7");
 const [operation,setOperation]=useState("");
 const [tableQuery,setTableQuery]=useState("");
 const [selected,setSelected]=useState("");
 const [selectedTrace,setSelectedTrace]=useState<TraceDetail|null>(null);
 const [fullTrace,setFullTrace]=useState<TraceDetail|null>(null);
 const [inspection,setInspection]=useState<Inspection|null>(null);
 const [inspectLoading,setInspectLoading]=useState(false);
 const [searchOpen,setSearchOpen]=useState(false);
 const [search,setSearch]=useState("");
 const [compact,setCompact]=useState(true);
 const [showHeuristics,setShowHeuristics]=useState(true);
 const [changesOnly,setChangesOnly]=useState(false);
 const [activityPage,setActivityPage]=useState(0);
 const [repositoryPath,setRepositoryPath]=useState("");
 const [indexing,setIndexing]=useState(false);
 const [indexMessage,setIndexMessage]=useState("");
 const requestNumber=useRef(0);
 const refresh=useCallback(async()=>{
  setLoading(true);setError("");
  try{
   const [stats,activity,structure,history]=await Promise.all([api<Overview>("overview"),api<{items:Trace[]}>("traces?limit=100"),api<ProjectGraph>("graph"),api<GitInfo>("git")]);
   let all=activity.items;
   // Paginate observations only; core selection remains in the runtime.
   for(let offset=100;all.length<Math.min(stats.total_operations,1000)&&offset<1000;offset+=100){const page=await api<{items:Trace[]}>(`traces?limit=100&offset=${offset}`);all=[...all,...page.items];if(page.items.length<100)break;}
   setOverview(stats);setTraces(all);setGraph(structure);setGit(history);
   if(!selectedTrace&&all.length)setSelectedTrace(await api<TraceDetail>("traces/"+all[0].id));
  }catch(e){setError(e instanceof Error?e.message:"Unable to connect to the runtime");}
  finally{setLoading(false);}
 },[selectedTrace]);
 useEffect(()=>{void refresh();},[]); // Initial project snapshot, refreshed explicitly thereafter.
 useEffect(()=>{const handler=(e:KeyboardEvent)=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==="k"){e.preventDefault();setSearchOpen(v=>!v);}};window.addEventListener("keydown",handler);return()=>window.removeEventListener("keydown",handler);},[]);
 useEffect(()=>{setActivityPage(0);},[range,operation,tableQuery]);
 const filePaths=useMemo(()=>graph?.nodes.filter(n=>n.kind==="file").map(n=>n.id)||[],[graph]);
 const metrics=periodMetrics(traces,range);
 const filtered=filterActivity(traces,range,operation,tableQuery);
 const preview=filtered.slice(0,5);
 const repositoryPaths=changesOnly?filePaths.filter(p=>git.changed_files?.includes(p)):filePaths;
 const displayGraph=graph&&!showHeuristics?{...graph,edges:graph.edges.filter(e=>!e.heuristic)}:graph;
 const rangeLabel=range==="all"?"All time":`Last ${range} days`;
 const projectName=overview?.project.name.replace(/^Conceptualize\s*[·:]\s*/,"")||"Local repository";
 function navigate(next:View){setView(next);setFullTrace(null);setInspection(null);setError("");}
 async function chooseTrace(id:string,open=false){
  setError("");setInspection(null);setInspectLoading(true);
  try{const trace=await api<TraceDetail>("traces/"+id);setSelectedTrace(trace);if(open)setFullTrace(trace);}
  catch(e){setError(e instanceof Error?e.message:"Unable to load trace");}finally{setInspectLoading(false);}
 }
 async function inspect(target:string,kind="dependencies"){
  const version=++requestNumber.current;setSelected(target);setInspection(null);setInspectLoading(true);setError("");
  try{const result=await api<Inspection>("runtime",{operation:kind,...(kind==="search"?{query:target}:kind==="map"?{path:target}:{target}),token_budget:3000});if(version===requestNumber.current)setInspection(result);}
  catch(e){if(version===requestNumber.current)setError(e instanceof Error?e.message:"Inspection failed");}
  finally{if(version===requestNumber.current)setInspectLoading(false);}
 }
 function selectPath(path:string){void inspect(path,path?"dependencies":"map");}
 async function indexRepository(event:FormEvent<HTMLFormElement>){
  event.preventDefault();setIndexing(true);setIndexMessage("");setError("");
  try{const result=await api<{files:number;symbols:number;languages:string[];git_branch?:string|null}>("index",{path:repositoryPath});await refresh();setIndexMessage(`Indexed ${formatNumber(result.files)} files, ${formatNumber(result.symbols)} symbols across ${result.languages.length} languages${result.git_branch?` on ${result.git_branch}`:""}.`);}
  catch(e){setIndexMessage(`Index failed: ${e instanceof Error?e.message:"check the repository path and API connection."}`);}
  finally{setIndexing(false);}
 }
 const searchTerm=search.trim().toLowerCase();
 const searchFiles=searchTerm?filePaths.filter(p=>p.toLowerCase().includes(searchTerm)).slice(0,6):[];
 const searchSymbols=searchTerm?graph?.nodes.filter(n=>n.kind==="symbol"&&n.name?.toLowerCase().includes(searchTerm)).slice(0,5)||[]:[];
 const searchTraces=searchTerm?traces.filter(t=>`${inputLabel(t)} ${t.id} ${t.client}`.toLowerCase().includes(searchTerm)).slice(0,4):[];
 const statCards=[{label:"Context operations",value:metrics.operations,metric:"operations",icon:Activity},{label:"Tokens delivered",value:metrics.tokens,metric:"tokens",icon:Layers},{label:"Avg. context size",value:metrics.averageSize,metric:"averageSize",icon:FileCode2},{label:"Avg. latency",value:metrics.averageLatency,metric:"averageLatency",icon:Zap}] as const;
 return <div className={`shell${compact?" compact":""}`}>
  <aside className="sidebar">
   <a href="/" className="brand" aria-label="Conceptualize home"><Box/><span>conceptualize<span className="brand-dot">.</span></span></a>
   <div className="workspace-heading"><span>Workspace</span><ChevronDown size={14}/></div>
   <DropdownMenu><DropdownMenuTrigger asChild><button className="workspace"><span className="workspace-icon"><FileCode2 size={22}/></span><span className="workspace-copy"><strong>{projectName}</strong><small>Local repository</small><span className="workspace-status"><i className={overview?.indexed_at?"status-dot":"status-dot offline"}/>{overview?.indexed_at?"Indexed":"Not indexed"}</span></span><ChevronDown size={13}/></button></DropdownMenuTrigger><DropdownMenuContent align="start"><DropdownMenuLabel>Current project</DropdownMenuLabel><DropdownMenuItem onSelect={()=>navigate("repository")}>Browse indexed repository</DropdownMenuItem><DropdownMenuItem onSelect={()=>navigate("settings")}>Project & connection details</DropdownMenuItem></DropdownMenuContent></DropdownMenu>
   <nav aria-label="Main navigation">{navigation.map(({key,label,icon:Icon})=><button key={key} className={view===key&&!fullTrace?"nav-item active":"nav-item"} aria-current={view===key&&!fullTrace?"page":undefined} onClick={()=>navigate(key)}><Icon size={20}/><span>{label}</span></button>)}</nav>
   <div className="runtime-status"><div><CircleDot size={16}/><strong>Context runtime</strong></div><div><span className="runtime-running"><i className={overview&&!error?"status-dot":"status-dot offline"}/>{overview&&!error?"Running":"Disconnected"}</span><small>v0.1.0</small></div></div>
  </aside>
  <main>
   <header className="topbar"><button className="global-search" onClick={()=>setSearchOpen(true)}><Search size={18}/><span>Search files, symbols, or traces...</span><kbd>⌘ K</kbd></button><div className="topbar-actions">
    <DropdownMenu><DropdownMenuTrigger asChild><button className="branch-control"><Github size={20}/><span>{git.branch||"Local"}</span><ChevronDown size={14}/></button></DropdownMenuTrigger><DropdownMenuContent align="end"><DropdownMenuLabel>Indexed Git snapshot</DropdownMenuLabel><DropdownMenuItem disabled>{git.branch||"No Git branch metadata"}{git.branch&&<Check size={14}/>}</DropdownMenuItem><DropdownMenuSeparator/><DropdownMenuItem onSelect={()=>{setChangesOnly(true);navigate("repository");}}>View working-tree changes</DropdownMenuItem><DropdownMenuItem onSelect={()=>{setChangesOnly(false);navigate("repository");}}>View all indexed files</DropdownMenuItem></DropdownMenuContent></DropdownMenu>
    <DropdownMenu><DropdownMenuTrigger asChild><button className="profile-control" aria-label="Local developer menu"><span className="avatar">L</span><ChevronDown size={14}/></button></DropdownMenuTrigger><DropdownMenuContent align="end"><DropdownMenuLabel>Local developer</DropdownMenuLabel><DropdownMenuItem onSelect={()=>navigate("settings")}>Settings</DropdownMenuItem><DropdownMenuItem onSelect={()=>void refresh()}>Refresh project data</DropdownMenuItem></DropdownMenuContent></DropdownMenu>
   </div></header>
   <div className={`content${view==="overview"&&!fullTrace?" overview-content":""}`}>
    {error&&<div className="error" role="alert"><strong>Connection needs attention</strong><p>{error}</p><button onClick={()=>void refresh()}>Retry connection</button></div>}
    {indexMessage.startsWith("Indexed")&&<div className="index-banner" role="status">{indexMessage}</div>}
    {fullTrace?<TracePanel detail={fullTrace} onBack={()=>setFullTrace(null)}/>:<>
     <div className="page-heading"><div><div className="page-kicker">{navigation.find(n=>n.key===view)?.label.toUpperCase()}</div><h1>{view==="overview"?<>Context that moves with <span>your agent.</span></>:view==="activity"?"Agent activity":view==="graph"?"Navigate your project context.":view==="repository"?"Repository intelligence.":view==="traces"?"Every context decision, traced.":"Runtime settings."}</h1><p>{view==="overview"?"Real project understanding for AI agents. Inspect usage, explore structure, and trace every interaction.":view==="settings"?"Your local project, connection, and dashboard preferences.":"Inspect the indexed project and follow how context reaches your agent."}</p></div><label className="date-filter"><CalendarDays size={16}/><span className="sr-only">Date range</span><select aria-label="Date range" value={range} onChange={e=>setRange(e.target.value as Range)}><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="all">All time</option></select></label></div>
     {view==="overview"&&!overview&&!loading?<section className="panel onboarding-panel"><div className="onboarding-mark"><Box size={23}/></div><div className="page-kicker">LOCAL WORKSPACE SETUP</div><h2>Connect Conceptualize</h2><p>{error||"Connect to your local Conceptualize API to continue."}</p><label className="setup-command-label">Create an empty project and API key</label><code className="setup-command">conceptualize seed --name "My repository" --email "developer@localhost"</code><small>Copy the one-time key into <code>CONCEPTUALIZE_API_KEY</code> in the project root .env, then restart the dashboard. This creates no sample repository or activity.</small><Button variant="outline" size="sm" onClick={()=>void refresh()}>Retry connection</Button></section>:view==="overview"&&overview&&overview.indexed_at===null?<section className="panel onboarding-panel"><div className="onboarding-mark"><FileCode2 size={23}/></div><div className="page-kicker">YOUR WORKSPACE</div><h2>No repository indexed</h2><p>Connect a local repository to build its context graph and start recording real agent activity.</p><form onSubmit={indexRepository}><label htmlFor="repository-path">Local repository path</label><div><input id="repository-path" value={repositoryPath} onChange={e=>setRepositoryPath(e.target.value)} placeholder="C:\\path\\to\\your\\repository" required disabled={indexing}/><Button type="submit" disabled={indexing||!repositoryPath.trim()}>{indexing?<><RefreshCw data-icon="inline-start"/>Indexing…</>:<>Index repository <ArrowRight data-icon="inline-end"/></>}</Button></div></form>{indexMessage&&<p className={indexMessage.startsWith("Indexed")?"index-success":"index-error"} role="status">{indexMessage}</p>}<small>Only supported project files are indexed. Secrets, dependencies, build output and ignored files are excluded.</small></section>:view==="overview"&&<>
      <section className="stats" aria-label="Project overview">{statCards.map(({label,value,metric,icon:Icon})=>{const bars=activityBars(traces,range,metric);const max=Math.max(1,...bars);const change=metrics.change[metric];return <div className="stat" key={label}><span className="stat-icon"><Icon size={20}/></span><div className="stat-body"><div className="stat-label">{label}</div><div className="stat-value"><strong>{overview?compactNumber(value):"—"}{metric==="averageLatency"&&overview&&<span> ms</span>}</strong>{change!==null?<span className="stat-change">{change>=0?<ArrowUp size={12}/>:<ArrowDown size={12}/>}{Math.abs(change)}%</span>:<small className="no-comparison" title="No observed activity in the preceding period">No prior period</small>}</div><div className="spark-bars" aria-label={`${label} over ${rangeLabel}`} title="Bars show observed operations only">{bars.map((n,i)=><span key={i} style={{height:n?`${Math.max(3,n/max*25)}px`:"1px",opacity:n?1:.35}}/>)}</div></div></div>;})}</section>
      <div className="overview-grid"><GraphPanel graph={displayGraph} selected={selected} onSelect={selectPath}/><section className="panel repository-panel"><div className="panel-heading"><div><h2>Repository structure</h2><p>Indexed project overview</p></div></div><RepositoryTree paths={filePaths} selected={selected} onSelect={selectPath}/></section><ActivityTable traces={preview} selected={selectedTrace?.id||""} onSelect={id=>void chooseTrace(id)} onOpen={id=>void chooseTrace(id,true)} onViewAll={()=>navigate("activity")}/><TracePreview detail={selectedTrace} inspection={inspection} loading={inspectLoading} target={selected} onOpen={()=>inspection?void chooseTrace(inspection.trace_id,true):selectedTrace&&setFullTrace(selectedTrace)} onExpand={()=>void inspect(selected||"repository","expand")} onClear={()=>setInspection(null)}/></div>
     </>}
     {(view==="activity"||view==="traces")&&<><div className="activity-filters"><label><Search size={16}/><input aria-label="Filter activity" placeholder="Filter requests, agents, or trace IDs" value={tableQuery} onChange={e=>setTableQuery(e.target.value)}/></label><select aria-label="Filter operation" value={operation} onChange={e=>setOperation(e.target.value)}><option value="">All operations</option>{["map","search","dependencies","expand","pack"].map(op=><option key={op}>{op}</option>)}</select><Button variant="outline" size="sm" onClick={()=>void refresh()} disabled={loading}><RefreshCw data-icon="inline-start"/>Refresh</Button></div><div className="activity-layout"><ActivityTable traces={filtered.slice(activityPage*15,activityPage*15+15)} selected={selectedTrace?.id||""} onSelect={id=>void chooseTrace(id)} onOpen={id=>void chooseTrace(id,true)} emptyMessage={view==="activity"?"No agent activity yet. Connect Conceptualize to an MCP-compatible agent to begin.":"No traces recorded yet."}/><TracePreview detail={selectedTrace} inspection={null} loading={inspectLoading} target="" onOpen={()=>selectedTrace&&setFullTrace(selectedTrace)}/></div><div className="pagination"><span>{filtered.length} operations · {rangeLabel}</span><div><Button variant="outline" size="sm" disabled={!activityPage} onClick={()=>setActivityPage(p=>p-1)}>Previous</Button><Button variant="outline" size="sm" disabled={(activityPage+1)*15>=filtered.length} onClick={()=>setActivityPage(p=>p+1)}>Next</Button></div></div></>}
     {view==="graph"&&<div className="explorer-layout"><GraphPanel graph={displayGraph} selected={selected} onSelect={selectPath} large/><TracePreview detail={selectedTrace} inspection={inspection} loading={inspectLoading} target={selected} onOpen={()=>inspection&&void chooseTrace(inspection.trace_id,true)} onExpand={()=>void inspect(selected,"expand")} onClear={()=>setInspection(null)}/></div>}
     {view==="repository"&&<div className="explorer-layout"><section className="panel"><div className="panel-heading"><div><h2>Repository structure</h2><p>{overview?.indexed_files||0} indexed files · {overview?.indexed_symbols||0} symbols</p></div><label className="changes-filter"><input type="checkbox" checked={changesOnly} onChange={e=>setChangesOnly(e.target.checked)}/> Changed files</label></div><RepositoryTree paths={repositoryPaths} selected={selected} onSelect={selectPath} expandedView/>{changesOnly&&!repositoryPaths.length&&<p className="panel-note">No working-tree changes were recorded in this index snapshot.</p>}</section><TracePreview detail={selectedTrace} inspection={inspection} loading={inspectLoading} target={selected} onOpen={()=>inspection&&void chooseTrace(inspection.trace_id,true)} onExpand={()=>void inspect(selected,"expand")}/></div>}
     {view==="settings"&&<section className="panel settings-panel"><div className="panel-heading"><div><h2>Project & runtime</h2><p>Connection details remain local to your dashboard server.</p></div></div><dl><div><dt>Project</dt><dd>{overview?.project.name||"Not connected"}</dd></div><div><dt>Project ID</dt><dd><code>{overview?.project.id||"—"}</code></dd></div><div><dt>Index revision</dt><dd>{overview?.project.revision??"—"}</dd></div><div><dt>Indexed at</dt><dd>{overview?.indexed_at?new Date(overview.indexed_at).toLocaleString():"Not indexed"}</dd></div><div><dt>Cache hit rate</dt><dd>{overview?`${Math.round(overview.cache_hit_rate*100)}%`:"—"}</dd></div><div><dt>Authentication</dt><dd>Project-scoped API key · server-side</dd></div></dl><div className="settings-preferences"><h2>Dashboard preferences</h2><label><input type="checkbox" checked={compact} onChange={e=>setCompact(e.target.checked)}/> Compact activity rows</label><label><input type="checkbox" checked={showHeuristics} onChange={e=>setShowHeuristics(e.target.checked)}/> Include heuristic relationships in graph views</label><p>Context reflects the last repository index. Reindex after source changes.</p><Button variant="outline" size="sm" onClick={()=>void refresh()}><RefreshCw data-icon="inline-start"/>Refresh runtime data</Button></div></section>}
     <footer className="page-footer"><span><span className="status-dot"/>{overview?`${overview.indexed_files} files · ${overview.indexed_symbols} symbols · index revision ${overview.project.revision}`:"Connecting to runtime…"}</span><span>{traces.length< (overview?.total_operations||0)?`Latest ${traces.length} operations loaded · `:""}Context selection within caller constraints.</span></footer>
    </>}
   </div>
  </main>
  <Dialog open={searchOpen} onOpenChange={setSearchOpen}><DialogContent className="search-dialog"><DialogTitle>Search project context</DialogTitle><div className="search-input"><Search size={19}/><input autoFocus placeholder="Search files, symbols, or traces..." aria-label="Search files, symbols, or traces" value={search} onChange={e=>setSearch(e.target.value)}/><kbd>ESC</kbd></div><div className="search-results">{!searchTerm?<p>Search your indexed repository and recorded agent activity.</p>:<>{searchFiles.length>0&&<h3>Files</h3>}{searchFiles.map(p=><button key={p} onClick={()=>{setSearchOpen(false);navigate("repository");selectPath(p);}}><FileCode2 size={15}/><code>{p}</code><ArrowRight size={14}/></button>)}{searchSymbols.length>0&&<h3>Symbols</h3>}{searchSymbols.map(n=><button key={n.id} onClick={()=>{setSearchOpen(false);navigate("graph");void inspect(n.name||n.id,"expand");}}><Box size={15}/><span>{n.name}<small>{n.id.split("::")[0]}</small></span><ArrowRight size={14}/></button>)}{searchTraces.length>0&&<h3>Traces</h3>}{searchTraces.map(t=><button key={t.id} onClick={()=>{setSearchOpen(false);void chooseTrace(t.id,true);}}><Workflow size={15}/><span>{inputLabel(t)}<small>{t.operation} · {t.id.slice(0,8)}</small></span><ArrowRight size={14}/></button>)}<button className="search-repository-action" onClick={()=>{setSearchOpen(false);navigate("graph");void inspect(search,"search");}}><Search size={15}/>Search repository contents for “{search}”<ArrowRight size={14}/></button></>}</div><div className="search-footer">Indexed files and symbols · select a result to inspect context</div></DialogContent></Dialog>
 </div>;
}

function ActivityTable({traces,selected,onSelect,onOpen,onViewAll,emptyMessage="No context operations yet."}:{traces:Trace[];selected:string;onSelect:(id:string)=>void;onOpen:(id:string)=>void;onViewAll?:()=>void;emptyMessage?:string}){
 return <section className="panel activity-panel"><div className="panel-heading"><div><h2>Recent agent activity</h2><p>Latest MCP operations and context delivery</p></div>{onViewAll&&<button className="outlined-button" onClick={onViewAll}>View all <ArrowRight size={14}/></button>}</div><div className="table-scroll"><table><thead><tr><th>TIME</th><th>AGENT</th><th>OPERATION</th><th>INPUT</th><th>CONTEXT (TOKENS)</th><th>LATENCY</th><th><span className="sr-only">Open trace</span></th></tr></thead><tbody>{traces.map(trace=>{const Icon=opIcons[trace.operation]||Activity;return <tr key={trace.id} className={selected===trace.id?"selected-row":""} onClick={()=>onSelect(trace.id)}><td><button className="row-select" onClick={e=>{e.stopPropagation();onSelect(trace.id);}} title={new Date(trace.timestamp).toLocaleString()}><CircleDot size={12}/>{relativeTime(trace.timestamp)}</button></td><td><span className="agent-cell"><span className="agent-icon"><Terminal size={13}/></span>{trace.client}</span></td><td><span className="operation-cell"><Icon size={15}/>{trace.operation}</span></td><td><code className="input-text" title={inputLabel(trace)}>{inputLabel(trace)}</code></td><td><div className="context-cell"><span>{formatNumber(trace.returned_tokens)} <small>/ {formatNumber(trace.token_budget)}</small></span><div className="mini-meter"><span style={{width:`${Math.min(100,trace.returned_tokens/trace.token_budget*100)}%`}}/></div></div></td><td className="mono">{trace.latency_ms} ms</td><td><button className="icon-button" aria-label={`Inspect ${trace.operation} trace`} onClick={e=>{e.stopPropagation();onOpen(trace.id);}}><ArrowRight size={14}/></button></td></tr>;})}</tbody></table></div>{!traces.length&&<div className="panel-empty">{emptyMessage}</div>}</section>;
}
function TracePreview({detail,inspection,loading,target,onOpen,onExpand,onClear}:{detail:TraceDetail|null;inspection:Inspection|null;loading:boolean;target:string;onOpen:()=>void;onExpand?:()=>void;onClear?:()=>void}){
 const result=detail?.result;
 if(inspection)return <section className="panel trace-preview context-inspector"><div className="panel-heading"><div><h2>Context inspector</h2><p>{target||"Repository overview"}</p></div><button className="outlined-button" onClick={onOpen}>Open <ArrowRight size={13}/></button></div><div className="inspector-content"><span className="inspector-mode">{inspection.operation} · {inspection.metrics.returned_tokens} tokens</span><pre>{inspection.context||"No matching context found."}</pre><div className="inspector-actions">{onExpand&&<button className="outlined-button" disabled={loading} onClick={onExpand}>Read source <FileCode2 size={13}/></button>}{onClear&&<button className="text-button" onClick={onClear}>Back to trace</button>}</div></div></section>;
 const rows=[{label:"Operation sequence",value:`${result?.steps?.length||0} steps`,icon:Activity},{label:"Files considered",value:result?.files_considered?.length||0,icon:FileCode2},{label:"Files selected",value:result?.included_files?.length||0,icon:Box},{label:"Candidate tokens",value:formatNumber(detail?.candidate_tokens||0),icon:Layers},{label:"Returned tokens",value:formatNumber(detail?.returned_tokens||0),icon:FileCode2},{label:"Latency",value:`${detail?.latency_ms||0} ms`,icon:Zap},{label:"Trace ID",value:detail?.id.slice(0,8)||"—",icon:CircleDot}];
 return <section className="panel trace-preview"><div className="panel-heading"><div><h2>{loading?"Loading context…":"Trace detail"}</h2></div><button className="outlined-button" disabled={!detail||loading} onClick={onOpen}>Open <ArrowRight size={13}/></button></div><p className="trace-preview-task">{detail?inputLabel(detail):"No traces recorded yet. Select a repository file or connect an MCP agent to begin."}</p><dl>{rows.map(({label,value,icon:Icon})=><div key={label}><dt><Icon size={13}/>{label}</dt><dd>{value}</dd></div>)}</dl></section>;
}
