import type { Trace } from "./types";
export type Range = "7" | "30" | "all";
export type TreeItem = {name: string; path: string; folder: boolean; count: number; children: TreeItem[]};
export const formatNumber = (n: number) => new Intl.NumberFormat("en-US").format(n);
export const compactNumber = (n: number) => n >= 1000000 ? `${(n/1000000).toFixed(1)}M` : n >= 10000 ? `${(n/1000).toFixed(1)}k` : formatNumber(n);
export const inputLabel = (trace: Trace) => String(trace.inputs.query || trace.inputs.target || trace.inputs.path || (trace.inputs.paths as string[] | undefined)?.join(", ") || "Project structure");
const DAY = 86400000;
export function filterActivity(traces: Trace[], range: Range, operation = "", query = "", now = Date.now()) {
  const cutoff = range === "all" ? 0 : now - Number(range) * DAY;
  return traces.filter(t => Date.parse(t.timestamp) >= cutoff && (!operation || t.operation === operation)
    && (!query || `${inputLabel(t)} ${t.operation} ${t.client} ${t.id}`.toLowerCase().includes(query.toLowerCase())));
}
function totals(traces: Trace[]) {
  const tokens = traces.reduce((n,t)=>n+t.returned_tokens,0);
  return {operations: traces.length, tokens, averageSize: traces.length ? Math.round(tokens/traces.length) : 0,
    averageLatency: traces.length ? Math.round(traces.reduce((n,t)=>n+t.latency_ms,0)/traces.length) : 0};
}
export function periodMetrics(traces: Trace[], range: Range, now = Date.now()) {
  const current = totals(filterActivity(traces, range, "", "", now));
  const previous = range === "all" ? [] : traces.filter(t => Date.parse(t.timestamp) < now-Number(range)*DAY && Date.parse(t.timestamp) >= now-Number(range)*2*DAY);
  const prior = totals(previous);
  const change = Object.fromEntries(Object.keys(current).map(key => {
    const k = key as keyof typeof current;
    return [k, prior[k] ? Math.round((current[k]-prior[k])/prior[k]*100) : null];
  })) as Record<keyof typeof current, number | null>;
  return {...current, change};
}
export function activityBars(traces: Trace[], range: Range, metric: "operations" | "tokens" | "averageSize" | "averageLatency", now = Date.now()) {
  const length = range === "all" ? Math.max(7, Math.ceil((now - Math.min(now, ...traces.map(t=>Date.parse(t.timestamp))))/DAY)) : Number(range);
  const buckets: Trace[][] = Array.from({length:30},()=>[]);
  for (const trace of filterActivity(traces,range,"","",now)) {
    const i = Math.min(29,Math.max(0,Math.floor((Date.parse(trace.timestamp)-(now-length*DAY))/(length*DAY)*30)));
    buckets[i].push(trace);
  }
  return buckets.map(b=>totals(b)[metric]);
}
export function buildRepositoryTree(paths: string[]): TreeItem {
  const root: TreeItem = {name: "repository", path:"", folder:true, count:0, children:[]};
  for (const path of [...new Set(paths)].sort()) {
    let node = root; node.count++;
    const parts = path.split("/");
    parts.forEach((name,i)=>{
      let child = node.children.find(c=>c.name===name);
      if (!child) { child = {name,path:parts.slice(0,i+1).join("/"),folder:i<parts.length-1,count:0,children:[]}; node.children.push(child); }
      child.count++; node=child;
    });
  }
  const sort = (node: TreeItem) => { node.children.sort((a,b)=>Number(b.folder)-Number(a.folder)||a.name.localeCompare(b.name)); node.children.forEach(sort); };
  sort(root); return root;
}
export function relativeTime(timestamp: string, now = Date.now()) {
  const minutes = Math.max(0, Math.floor((now-Date.parse(timestamp))/60000));
  return minutes < 1 ? "Just now" : minutes < 60 ? `${minutes} min ago` : minutes < 1440 ? `${Math.floor(minutes/60)} hr ago` : `${Math.floor(minutes/1440)}d ago`;
}
