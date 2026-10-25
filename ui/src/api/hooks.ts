import { useEffect, useRef, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { api } from "./client"
import { qk } from "./keys"
import type { Findings, StudyDetail, WorklistRow } from "./types"

const q = { staleTime: 5_000, refetchOnWindowFocus: false }

export function useWorklist() {
  return useQuery({ queryKey: qk.worklist, queryFn: api.worklist, ...q })
}

export function useStudy(uid: string | null) {
  return useQuery({
    queryKey: qk.study(uid ?? ""),
    queryFn: () => api.study(uid!),
    enabled: !!uid,
    placeholderData: undefined,
    ...q,
  })
}

export function useFindings(uid: string | null) {
  const fq = useQuery({
    queryKey: qk.findings(uid ?? ""),
    queryFn: () => api.findings(uid!),
    enabled: !!uid,
    retry: false,
    ...q,
  })
  // TanStack keeps stale data when a refetch fails: never render another study's payload.
  const data: Findings | undefined =
    fq.isError || (fq.data && fq.data.study_uid !== uid) ? undefined : fq.data
  return { ...fq, data }
}

export function useReports(uid: string | null) {
  return useQuery({
    queryKey: qk.reports(uid ?? ""),
    queryFn: () => api.reports(uid!),
    enabled: !!uid,
    ...q,
  })
}

export function useAgentLog(studyUid?: string | null, limit = 300) {
  return useQuery({
    queryKey: qk.agentLog(studyUid),
    queryFn: () => api.agentLog(studyUid, limit),
    refetchInterval: false,
    ...q,
  })
}

export function useOutbox() {
  return useQuery({ queryKey: qk.outbox, queryFn: api.outbox, ...q })
}

export function useNetstats() {
  return useQuery({ queryKey: qk.netstats, queryFn: api.netstats, ...q })
}

/** Patient id for a study, from the worklist cache (global log uses it). */
export function usePatientOf(uid: string | null): string | undefined {
  const { data } = useWorklist()
  return uid ? data?.find((r: WorklistRow) => r.study_uid === uid)?.patient_id : undefined
}

export function useInterval<T>(read: () => T | undefined, ms: number) {
  const [v, setV] = useState<T | undefined>(undefined)
  const ref = useRef(read)
  ref.current = read
  useEffect(() => {
    const t = setInterval(() => setV(ref.current()), ms)
    return () => clearInterval(t)
  }, [ms])
  return v
}

export type StudyOrRow = StudyDetail | WorklistRow
