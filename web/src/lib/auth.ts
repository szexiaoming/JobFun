export const SESSION_COOKIE = "jobfun_session";

export function sessionCookieOptions() {
  const configured = process.env.JOBFUN_COOKIE_SECURE?.trim().toLowerCase();
  const secure =
    configured === "true" ||
    (configured !== "false" && process.env.NODE_ENV === "production");

  return {
    httpOnly: true,
    secure,
    sameSite: "strict" as const,
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  };
}

export function isSameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  const host = request.headers.get("host");
  if (!origin || !host) {
    return false;
  }
  try {
    return new URL(origin).host === host.trim().toLowerCase();
  } catch {
    return false;
  }
}
