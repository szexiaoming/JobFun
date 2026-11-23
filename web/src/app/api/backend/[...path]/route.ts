import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import { isSameOrigin, SESSION_COOKIE } from "@/lib/auth";
import { proxyBackendRequest } from "@/lib/server-api";

const ALLOWED_PATHS = [
  /^me(?:\/export|\/deletion-challenge)?$/,
  /^workbench$/,
  /^resumes(?:\/\d+)?$/,
  /^jobs(?:\/\d+)?$/,
  /^matches(?:\/\d+)?$/,
  /^applications(?:\/\d+)?(?:\/(?:interview-(?:insights|questions)|requirements|gap-explanations))?$/,
  /^gap-explanations\/\d+$/,
  /^interview-attempts(?:\/\d+)?$/,
  /^interview-transcriptions(?:\/\d+)?$/,
  /^operations\/\d+$/,
  /^uploads\/(?:resume_source|job_source|interview_audio|\d+)$/,
  /^retained-audio$/,
];

type Context = { params: Promise<{ path: string[] }> };

async function handle(request: Request, context: Context) {
  const method = request.method.toUpperCase();
  if (!["GET", "HEAD"].includes(method) && !isSameOrigin(request)) {
    return NextResponse.json({ error: "请求来源无效" }, { status: 403 });
  }
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ error: "需要重新登录" }, { status: 401 });
  }
  const { path } = await context.params;
  const backendPath = path.join("/");
  if (!ALLOWED_PATHS.some((pattern) => pattern.test(backendPath))) {
    return NextResponse.json({ error: "接口不存在" }, { status: 404 });
  }
  try {
    return await proxyBackendRequest(
      request,
      `/${backendPath}${new URL(request.url).search}`,
      token,
    );
  } catch {
    return NextResponse.json({ error: "暂时无法连接 JobFun API" }, { status: 503 });
  }
}

export const GET = handle;
export const POST = handle;
export const PATCH = handle;
export const DELETE = handle;
