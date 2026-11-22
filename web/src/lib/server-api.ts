import "server-only";

import { cookies } from "next/headers";
import { cache } from "react";

import { SESSION_COOKIE } from "@/lib/auth";

export type CurrentUser = {
  id: number;
  username: string;
  roles: string[];
};

type BackendErrorBody = {
  error?: {
    code?: string;
    message?: string;
    request_id?: string;
  };
};

export class BackendError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly requestId = "",
  ) {
    super(message);
    this.name = "BackendError";
  }
}

function apiBaseUrl(): string {
  const configured =
    process.env.JOBFUN_API_BASE_URL?.trim() ||
    "http://127.0.0.1:8000/api/v1";
  const parsed = new URL(configured);
  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error("JOBFUN_API_BASE_URL must use HTTP or HTTPS");
  }
  return parsed.toString().replace(/\/$/, "");
}

export async function sessionToken(): Promise<string | null> {
  return (await cookies()).get(SESSION_COOKIE)?.value ?? null;
}

export async function backendRequest<T>(
  path: string,
  init: RequestInit = {},
  explicitToken?: string,
): Promise<T> {
  const token = explicitToken ?? (await sessionToken());
  if (!token) {
    throw new BackendError(401, "authentication_required", "需要重新登录");
  }
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  headers.set("Accept", "application/json");
  headers.set("X-Request-ID", crypto.randomUUID());
  const response = await fetch(`${apiBaseUrl()}${normalizedPath(path)}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  if (!response.ok) {
    throw await toBackendError(response);
  }
  return (await response.json()) as T;
}

export const getCurrentUser = cache(() => backendRequest<CurrentUser>("/me"));

export async function proxyBackendRequest(
  request: Request,
  path: string,
  token: string,
): Promise<Response> {
  const incoming = new Headers(request.headers);
  const headers = new Headers();
  for (const name of ["content-type", "idempotency-key", "deletion-token"]) {
    const value = incoming.get(name);
    if (value) headers.set(name, value);
  }
  headers.set("Authorization", `Bearer ${token}`);
  headers.set("Accept", incoming.get("accept") || "application/json");
  headers.set("X-Request-ID", crypto.randomUUID());
  const method = request.method.toUpperCase();
  const response = await fetch(`${apiBaseUrl()}${normalizedPath(path)}`, {
    method,
    headers,
    body: ["GET", "HEAD"].includes(method) ? undefined : await request.arrayBuffer(),
    cache: "no-store",
    redirect: "manual",
  });
  const outgoingHeaders = new Headers();
  for (const name of [
    "content-type",
    "content-disposition",
    "content-length",
    "cache-control",
    "x-request-id",
    "retry-after",
  ]) {
    const value = response.headers.get(name);
    if (value) outgoingHeaders.set(name, value);
  }
  outgoingHeaders.set("X-Content-Type-Options", "nosniff");
  return new Response(response.body, {
    status: response.status,
    headers: outgoingHeaders,
  });
}

export async function toBackendError(response: Response): Promise<BackendError> {
  let body: BackendErrorBody = {};
  try {
    body = (await response.json()) as BackendErrorBody;
  } catch {
    // Keep upstream bodies and infrastructure details out of the UI.
  }
  return new BackendError(
    response.status,
    body.error?.code || "backend_error",
    body.error?.message || "服务暂时无法完成请求",
    body.error?.request_id || response.headers.get("x-request-id") || "",
  );
}

function normalizedPath(path: string): string {
  const value = path.startsWith("/") ? path : `/${path}`;
  if (value.includes("..") || value.includes("\\")) {
    throw new Error("Invalid backend path");
  }
  return value;
}
