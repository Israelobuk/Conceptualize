export type Overview = {
  project: { id: string; name: string; revision: number };
  total_operations: number; tokens_delivered: number; average_context_size: number;
  average_latency_ms: number; indexed_files: number; indexed_symbols: number;
  cache_hit_rate: number; indexed_at: string | null;
};
export type Trace = {
  id: string; operation: string; inputs: Record<string, unknown>; client: string;
  session_id: string | null; timestamp: string; token_budget: number;
  candidate_tokens: number; returned_tokens: number; latency_ms: number;
  cache_hit: boolean; status: string; revision: number; otel_trace_id: string;
};
export type Relationship = { source: string; target: string; kind: string; heuristic?: boolean };
export type TraceDetail = Trace & { result: {
  context: string; included_files: string[]; omitted_files: string[]; truncated_files?: string[];
  files_considered?: string[]; relationships?: Relationship[];
  selection?: {path:string;priority:number;reason:string;relationship:Relationship|null;
    token_cost:number;status:"selected"|"omitted"|"truncated"|"referenced";score?:number;graph_distance?:number|null;already_known?:boolean;score_reasons?:{signal:string;weight:number;evidence?:unknown}[];omission_reason?:string|null}[];
  sources?: { path: string; tokens: number; reason: string; parse_errors?: boolean }[];
  structural_selection?: unknown[];
  steps?: {name: string; files?: number; relationships?: number; returned_tokens?: number}[];
  index?: { revision: number; indexed_at: string | null; freshness: string };
  pattern_evidence?: unknown[]; manifest?: Record<string,unknown>; invalidations?:unknown[]; overhead?: Record<string,unknown>; context_id?:string; metrics?: Record<string, number>; previous_context?: {path:string; supplied_in_operation?:string; unchanged:boolean}[]; timings_ms?:Record<string,number>; error?: string; budget_scope?: string;
} };
export type ProjectGraph = {
  nodes: {id: string; kind: string; language?: string; name?: string}[];
  edges: Relationship[]; truncated: boolean; total_nodes: number;
};
export type GitInfo = {available?: boolean; branch?: string; head?: string|null;
  changed_files?:string[]; commits?:{sha:string;timestamp:string;subject:string;files:string[]}[];
  base?:string; base_diff_stat?:string; cochanges?:{files:string[];count:number}[]};
