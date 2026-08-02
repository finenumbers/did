import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function backendBase(): string {
  const base =
    process.env.BACKEND_INTERNAL_URL ||
    (process.env.NEXT_PUBLIC_API_URL?.startsWith("http")
      ? process.env.NEXT_PUBLIC_API_URL
      : "http://localhost:8000");
  return base.replace(/\/$/, "");
}

async function proxy(req: NextRequest, pathParts: string[]): Promise<NextResponse> {
  const targetPath = "/" + pathParts.map(encodeURIComponent).join("/");
  const url = new URL(backendBase() + targetPath);
  url.search = req.nextUrl.search;

  const headers = new Headers();
  const contentType = req.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const accept = req.headers.get("accept");
  if (accept) headers.set("accept", accept);

  // Prefer browser session token; fallback to machine token for server-side calls
  const incoming = req.headers.get("Authorization");
  if (incoming) {
    headers.set("Authorization", incoming);
  } else {
    const token = (process.env.ADMIN_API_TOKEN || "").trim();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  // Allow iframe export via ?access_token=
  const qToken = url.searchParams.get("access_token");
  if (qToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${qToken}`);
    url.searchParams.delete("access_token");
  }

  const init: RequestInit = {
    method: req.method,
    headers,
    cache: "no-store",
  };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.arrayBuffer();
  }

  const upstream = await fetch(url, init);
  const outHeaders = new Headers();
  for (const key of ["content-type", "content-disposition", "content-length"]) {
    const v = upstream.headers.get(key);
    if (v) outHeaders.set(key, v);
  }
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: outHeaders,
  });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function POST(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function PUT(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function PATCH(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path);
}
