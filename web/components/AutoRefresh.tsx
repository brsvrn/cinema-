"use client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

// Polls the server while a render is in progress. Rendering itself happens on the
// worker, so closing the app or losing connection never stops production.
export default function AutoRefresh({ active, ms = 5000 }: { active: boolean; ms?: number }) {
  const router = useRouter();
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => router.refresh(), ms);
    return () => clearInterval(t);
  }, [active, ms, router]);
  return null;
}
