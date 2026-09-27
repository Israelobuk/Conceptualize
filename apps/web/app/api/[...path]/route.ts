import { NextRequest, NextResponse } from "next/server";
// Local control plane only. Credentials remain on the server; never NEXT_PUBLIC_*.
export async function GET(request: NextRequest, context: {params: Promise<{path: string[]}>}) {
  const { path } = await context.params;
  const allowed = path.length === 1 && ["overview", "traces", "graph", "git"].includes(path[0])
    || path.length === 2 && path[0] === "traces" && /^[a-f0-9-]{36}$/.test(path[1]);
  if (!allowed) return NextResponse.json({detail: "Not found"}, {status: 404});
  const key = process.env.CONCEPTUALIZE_API_KEY;
  if (!key) return NextResponse.json({detail: "Set CONCEPTUALIZE_API_KEY in the dashboard server environment, then restart it."}, {status: 503});
  try {
    const url = (process.env.CONCEPTUALIZE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "")
      + "/v1/" + path.join("/") + request.nextUrl.search;
    const response = await fetch(url, {headers: {Authorization: `Bearer ${key}`}, cache: "no-store", signal: AbortSignal.timeout(15000)});
    return NextResponse.json(await response.json(), {status: response.status});
  } catch {
    return NextResponse.json({detail: "Cannot reach Conceptualize API. Start the API and check its URL."}, {status: 503});
  }
}

// Context inspections use the same API/runtime as MCP. No retrieval logic lives here.
export async function POST(request: NextRequest, context: {params: Promise<{path: string[]}>}) {
  const {path} = await context.params;
  if(path.length !== 1 || !["runtime", "index"].includes(path[0])) return NextResponse.json({detail:"Not found"},{status:404});
  const origin = request.headers.get("origin");
  const publicOrigin = `${request.nextUrl.protocol}//${request.headers.get("host") || request.nextUrl.host}`;
  if(origin && origin !== publicOrigin) return NextResponse.json({detail:"Invalid origin"},{status:403});
  const key=process.env.CONCEPTUALIZE_API_KEY;
  if(!key)return NextResponse.json({detail:"Set CONCEPTUALIZE_API_KEY in the dashboard server environment, then restart it."},{status:503});
  try {
    const body=await request.json();
    const endpoint=path[0] === "index" ? "/v1/index" : "/v1/runtime";
    const response=await fetch((process.env.CONCEPTUALIZE_API_URL||"http://127.0.0.1:8000").replace(/\/$/,"")+endpoint,{
      method:"POST",headers:{Authorization:`Bearer ${key}`,"Content-Type":"application/json","X-MCP-Client":"dashboard"},
      body:JSON.stringify(body),signal:AbortSignal.timeout(30000),cache:"no-store"});
    return NextResponse.json(await response.json(),{status:response.status});
  }catch{return NextResponse.json({detail:"Unable to inspect context. Check the API connection."},{status:503});}
}
