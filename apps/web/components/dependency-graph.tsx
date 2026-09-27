"use client";
import { useMemo, useEffect, useRef } from "react";
import { ReactFlow, Background, Controls, Handle, Position, type NodeProps, type Node, type Edge, type ReactFlowInstance } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { ProjectGraph } from "@/lib/types";
type GraphNode=Node<{label:string;path:string;major:boolean;root?:boolean},"context">;
function ContextNode({data,selected}:NodeProps<GraphNode>) {
  return <div className={`${data.major?"graph-hub":"graph-file"}${data.root?" root-hub":""}${selected?" selected":""}`} title={data.path || "Repository root"}>
    <Handle type="target" position={Position.Left} id="in-left" style={data.major?{left:data.root?17:10}:undefined}/>
    <Handle type="target" position={Position.Right} id="in-right" style={data.major?{left:data.root?17:10,right:"auto"}:undefined}/>
    {data.major ? <><span className="hub-circle"/><span className="hub-label">{data.label}</span></> : <span>{data.label}</span>}
    <Handle type="source" position={Position.Left} id="out-left" style={data.major?{left:data.root?17:10}:undefined}/>
    <Handle type="source" position={Position.Right} id="out-right" style={data.major?{left:data.root?17:10,right:"auto"}:undefined}/>
  </div>;
}
const nodeTypes={context:ContextNode};
export default function DependencyGraph({graph,selected,onSelect,mode="tree",filter=""}:{graph:ProjectGraph;selected:string;onSelect:(path:string)=>void;mode?:"tree"|"dependencies";filter?:string;}) {
 const canvasRef=useRef<HTMLDivElement>(null); const flowRef=useRef<ReactFlowInstance<GraphNode,Edge>|null>(null);
 useEffect(()=>{if(!canvasRef.current)return;let timer:ReturnType<typeof setTimeout>;const observer=new ResizeObserver(()=>{clearTimeout(timer);timer=setTimeout(()=>void flowRef.current?.fitView({padding:.12,minZoom:.1}),100);});observer.observe(canvasRef.current);return()=>{observer.disconnect();clearTimeout(timer);};},[]);
 const {nodes,edges}=useMemo(()=>{
  const paths=graph.nodes.filter(n=>n.kind==="file" && (!filter || n.id===filter || n.id.startsWith(filter+"/"))).map(n=>n.id).sort();
  const groups=new Map<string,string[]>();
  for(const path of paths){const pieces=path.split("/");const group=pieces.length>1?pieces[0]:"root files";groups.set(group,[...(groups.get(group)||[]),path]);}
  const graphNodes:GraphNode[]=[{id:"dir:",type:"context",position:{x:450,y:175},selected:selected==="",data:{label:"repo",path:"",major:true,root:true}}];
  const graphEdges:Edge[]=[];
  [...groups.entries()].forEach(([group,files],i)=>{
   const slots=[{hub:500,leaf:615,y:5,hubY:35},{hub:215,leaf:10,y:75,hubY:110},{hub:215,leaf:10,y:215,hubY:235},{hub:705,leaf:815,y:95,hubY:130},{hub:705,leaf:815,y:225,hubY:255}];
   const slot=slots[i]||{hub:i%2?705:215,leaf:i%2?815:10,y:350+Math.floor((i-5)/2)*130,hubY:385+Math.floor((i-5)/2)*130};
   const left=slot.hub<450;const y=slot.y;const hubX=slot.hub;
   const target=group==="root files"?"":group;
   graphNodes.push({id:"dir:"+group,type:"context",position:{x:hubX,y:slot.hubY},selected:!!selected&&selected===group,data:{label:group,path:target,major:true}});
   graphEdges.push({id:"tree:"+group,source:"dir:",target:"dir:"+group,sourceHandle:left?"out-left":"out-right",targetHandle:left?"in-right":"in-left",type:"default",style:{stroke:selected===group?"#3478e5":"#183d70",strokeWidth:1.1}});
   const ordered=files.includes(selected)?[selected,...files.filter(p=>p!==selected)]:files;
   const shown=ordered.slice(0,mode==="tree"?3:6);
   shown.forEach((path,j)=>{
    graphNodes.push({id:path,type:"context",position:{x:slot.leaf,y:y+j*30},selected:selected===path,data:{label:path.split("/").pop()||path,path,major:false}});
    if(mode==="tree")graphEdges.push({id:"file:"+path,source:"dir:"+group,target:path,sourceHandle:left?"out-left":"out-right",targetHandle:left?"in-right":"in-left",type:"default",style:{stroke:selected===path?"#3478e5":"#183d70",strokeWidth:1}});
   });
   if(files.length>shown.length)graphNodes.push({id:"more:"+group,type:"context",position:{x:slot.leaf,y:y+shown.length*30},data:{label:`+${files.length-shown.length} files`,path:target,major:false}});
  });
  if(mode==="dependencies"){
   const visible=new Set(graphNodes.map(n=>n.id));
   graph.edges.filter(e=>e.kind!=="defines"&&visible.has(e.source)&&visible.has(e.target)).forEach((e,i)=>graphEdges.push({id:`dependency:${i}`,source:e.source,target:e.target,type:"default",style:{stroke:e.source===selected||e.target===selected?"#3478e5":"#24466d",strokeWidth:1.15},label:e.kind.replaceAll("_"," "),labelStyle:{fill:"#9babc1",fontSize:9},labelBgStyle:{fill:"#050c14"}}));
  }
  return {nodes:graphNodes,edges:graphEdges};
 },[graph,selected,mode,filter]);
 if(!graph.nodes.length)return <div className="graph-canvas panel-empty">Index a repository to explore its structure.</div>;
 return <div ref={canvasRef} className="graph-canvas" aria-label="Project dependency graph"><ReactFlow key={mode+filter} nodes={nodes} edges={edges} nodeTypes={nodeTypes} onInit={instance=>{flowRef.current=instance;}} fitView fitViewOptions={{padding:.12,minZoom:.1}} minZoom={.1} maxZoom={2.5} colorMode="dark" nodesDraggable onNodeClick={(_,node)=>onSelect(node.data.path)} proOptions={{hideAttribution:true}}><Background color="#142237" gap={22} size={.8}/><Controls showInteractive={false}/></ReactFlow></div>;
}
