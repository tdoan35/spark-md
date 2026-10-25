export const qk = {
  worklist: ["worklist"] as const,
  study: (uid: string) => ["study", uid] as const,
  findings: (uid: string) => ["findings", uid] as const,
  reports: (uid: string) => ["reports", uid] as const,
  agentLog: (uid?: string | null) => ["agent-log", uid ?? "global"] as const,
  outbox: ["outbox"] as const,
  netstats: ["netstats"] as const,
}
