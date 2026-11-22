"use client";

import { useEffect } from "react";

export function PwaRegister() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    if (process.env.NODE_ENV !== "production") {
      navigator.serviceWorker.getRegistration("/").then((registration) => registration?.unregister()).catch(() => {
        // A stale local preview worker should not block development.
      });
      return;
    }
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {
      // Offline support is progressive; a registration failure must not block the app.
    });
  }, []);
  return null;
}
