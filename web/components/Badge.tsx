import { STATUS_TR } from "@/lib/types";
export default function Badge({ s }: { s?: string }) {
  if (!s) return null;
  return <span className={`badge ${s}`}>{STATUS_TR[s] || s}</span>;
}
