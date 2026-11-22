import "server-only";

import { notFound } from "next/navigation";

import { BackendError } from "@/lib/server-api";

export function resourceId(value: string): number {
  if (!/^[1-9]\d*$/.test(value)) notFound();
  const id = Number(value);
  if (!Number.isSafeInteger(id)) notFound();
  return id;
}

export async function detailOrNotFound<T>(request: Promise<T>): Promise<T> {
  try {
    return await request;
  } catch (error) {
    if (error instanceof BackendError && error.status === 404) notFound();
    throw error;
  }
}
