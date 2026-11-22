import { NextResponse } from "next/server";

import { SESSION_COOKIE } from "@/lib/auth";
import { BackendError, getCurrentUser } from "@/lib/server-api";

export async function GET() {
  try {
    const user = await getCurrentUser();
    const response = NextResponse.json({ user });
    response.headers.set("Cache-Control", "no-store");
    return response;
  } catch (error) {
    const response = NextResponse.json(
      { error: "需要重新登录" },
      { status: error instanceof BackendError ? error.status : 503 },
    );
    if (error instanceof BackendError && error.status === 401) {
      response.cookies.delete(SESSION_COOKIE);
    }
    response.headers.set("Cache-Control", "no-store");
    return response;
  }
}
