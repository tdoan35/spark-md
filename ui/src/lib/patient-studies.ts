import type { PriorRef, StudyDetail, WorklistRow } from "@/api/types"

/** Chronology only: no clinical measurements are derived in the UI. */
export function compareScreens(a: PriorRef, b: PriorRef) {
  return (a.day_offset != null && b.day_offset != null ? a.day_offset - b.day_offset : 0)
    || a.timepoint.localeCompare(b.timepoint, undefined, { numeric: true })
    || a.study_uid.localeCompare(b.study_uid)
}

export function patientScreens(study: StudyDetail, worklist: WorklistRow[] = []): PriorRef[] {
  const screens = new Map<string, PriorRef>()
  for (const screen of [...study.priors, study, ...worklist.filter((s) => s.patient_id === study.patient_id)]) {
    screens.set(screen.study_uid, screen)
  }
  return [...screens.values()].sort(compareScreens)
}
