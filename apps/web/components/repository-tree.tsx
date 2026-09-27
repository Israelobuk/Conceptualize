"use client";
import { useMemo, useState } from "react";
import { ChevronRight, FileCode2, Folder, FolderOpen } from "lucide-react";
import { buildRepositoryTree, type TreeItem } from "@/lib/dashboard-data";
export default function RepositoryTree({paths, selected, onSelect, expandedView=false}: {paths:string[]; selected:string; onSelect:(path:string)=>void; expandedView?:boolean;}) {
  const root = useMemo(()=>buildRepositoryTree(paths),[paths]);
  const [expanded,setExpanded] = useState<Set<string>>(new Set(["apps","src"]));
  function render(node:TreeItem, depth:number):React.ReactNode {
    const open=expanded.has(node.path);
    const Icon=node.folder ? open ? FolderOpen : Folder : FileCode2;
    return <div key={node.path}>
      <div className={selected===node.path ? "tree-row selected" : "tree-row"} style={{paddingLeft:14+depth*17}}>
        {node.folder ? <button className="tree-disclosure" aria-label={`${open?"Collapse":"Expand"} ${node.path}`} aria-expanded={open} onClick={()=>setExpanded(previous=>{const next=new Set(previous);if(next.has(node.path))next.delete(node.path);else next.add(node.path);return next;})}><ChevronRight size={13} className={open?"rotated":""}/></button> : <span className="tree-spacer"/>}
        <button className="tree-select" onClick={()=>onSelect(node.path)} title={node.path}><Icon size={15}/><span>{node.name}</span></button>
        {node.folder && <span className="tree-count">{node.count}{depth===0?" files":""}</span>}
      </div>
      {node.folder && open && node.children.map(child=>render(child,depth+1))}
    </div>;
  }
  return <div className={expandedView?"repository-tree expanded-tree":"repository-tree"} aria-label="Repository files">{root.children.map(node=>render(node,0))}{!paths.length && <div className="panel-empty">No repository files indexed.</div>}</div>;
}
