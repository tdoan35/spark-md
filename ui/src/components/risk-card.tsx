import riskFixture from "../../../fixtures/sybil_risk.json"
import { Card, CardContent, CardHeader } from "@/components/ui/card"

type RiskCardProps = {
  studyUid: string
  patientId: string
  timepoint: string
}

type RiskScreen = {
  timepoint: string
  study_uid: string
  risk_1_to_6yr: number[]
}

type RiskPatient = { screens: RiskScreen[] }

const patients: Record<string, RiskPatient> = riskFixture.patients
const percent = (probability: number) => `${(probability * 100).toFixed(1)}%`

export function RiskCard({ studyUid, patientId, timepoint }: RiskCardProps) {
  const exactPatient = Object.values(patients).find((patient) =>
    patient.screens.some((screen) => screen.study_uid === studyUid),
  )
  const fallbackId = patientId.replace(/^fixture-/, "")
  const patient = exactPatient ?? (Object.hasOwn(patients, fallbackId) ? patients[fallbackId] : undefined)
  const currentIndex = patient?.screens.findIndex((screen) =>
    exactPatient ? screen.study_uid === studyUid : screen.timepoint === timepoint,
  ) ?? -1
  if (!patient || currentIndex < 0) return null

  const current = patient.screens[currentIndex]
  // The fixture is ordered T0..T2; never include screens after the matched study.
  const trend = patient.screens.slice(0, currentIndex + 1)

  return (
    <Card size="sm" aria-label="Sybil research risk" className="gap-2 rounded-lg bg-muted/30 text-muted-foreground shadow-none">
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <h3 className="text-xs font-medium">Sybil risk estimate</h3>
      </CardHeader>
      <CardContent className="space-y-2">
        <dl className="grid grid-cols-2 gap-3">
          <div>
            <dt className="text-[10px]">1-yr</dt>
            <dd className="font-mono text-base tabular-nums">{percent(current.risk_1_to_6yr[0])}</dd>
          </div>
          <div>
            <dt className="text-[10px]">6-yr</dt>
            <dd className="font-mono text-base tabular-nums">{percent(current.risk_1_to_6yr[5])}</dd>
          </div>
        </dl>
        <div>
          <div className="mb-1 text-[10px]">1-yr trend · through {current.timepoint}</div>
          <ol aria-label="1-year risk by screen" className="flex flex-wrap gap-x-2 gap-y-1 text-[10px]">
            {trend.map((screen, index) => (
              <li key={screen.timepoint} className="flex items-center gap-2">
                {index > 0 && <span aria-hidden="true">→</span>}
                <span>{screen.timepoint} <span className="font-mono tabular-nums">{percent(screen.risk_1_to_6yr[0])}</span></span>
              </li>
            ))}
          </ol>
        </div>
        <p className="text-[10px] leading-relaxed">Research model · not a diagnosis · not part of Lung-RADS · precomputed offline on this box</p>
        <p className="text-[10px] leading-relaxed">NLST-trained; demo patients may overlap training data. These scores are not validation.</p>
      </CardContent>
    </Card>
  )
}
