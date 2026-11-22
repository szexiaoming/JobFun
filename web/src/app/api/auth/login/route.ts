import { NextResponse } from "next/server";

import { isSameOrigin, SESSION_COOKIE, sessionCookieOptions } from "@/lib/auth";
import { BackendError, backendRequest, type CurrentUser } from "@/lib/server-api";

export async function POST(request: Request) {
  if (!isSameOrigin(request)) {
    return NextResponse.json({ error: "请求来源无效" }, { status: 403 });
  }
  let token = "";
  try {
    const body = (await request.json()) as { token?: unknown };
    token = typeof body.token === "string" ? body.token.trim() : "";
  } catch {
    return NextResponse.json({ error: "登录信息格式无效" }, { status: 400 });
  }
  if (token.length < 32 || token.length > 512 || !/^[\x20-\x7E]+$/.test(token)) {
    return NextResponse.json({ error: "API Token 格式无效" }, { status: 422 });
  }
  try {
    const user = await backendRequest<CurrentUser>("/me", {}, token);
    const response = NextResponse.json({ user });
    response.cookies.set(SESSION_COOKIE, token, sessionCookieOptions());
    response.headers.set("Cache-Control", "no-store");
    return response;
  } catch (error) {
    if (error instanceof BackendError && error.status === 401) {
      return NextResponse.json({ error: "API Token 无效或已过期" }, { status: 401 });
    }
    return NextResponse.json({ error: "暂时无法连接 JobFun API" }, { status: 503 });
  }
}
