// Deterministic fixtures for the mock worker (item M, spec 08). Placeholder numbers only.
// Three hero timepoints plus two non-hero rows for the worklist.

const HERO = "134503"
const uid = (i) => `1.2.826.0.1.3680043.10.1234.${i}`

export const studies = [
  {
    study_uid: uid("134503.00"),
    patient_id: HERO,
    timepoint: "T0",
    rank: 0,
    day_offset: 0,
    study_date: "2019-03-04",
    stack_count: 151,
    nodules: [
      { nodule_id: "134503-T0-N1", track_id: "T1", lobe: "LUL (lingula)", center_mm: [-42.3, 18.7, -31.2], long: 6.2, short: 5.4, box_mean: 6.6, mean_hu: 41, type: "solid", det_score: 0.999 },
      { nodule_id: "134503-T0-N2", track_id: "T2", lobe: "RUL", center_mm: [38.1, 44.2, 12.4], long: 4.1, short: 3.9, box_mean: 4.4, mean_hu: 8, type: "ggo", det_score: 0.94 },
    ],
  },
  {
    study_uid: uid("134503.01"),
    patient_id: HERO,
    timepoint: "T1",
    rank: 1,
    day_offset: 380,
    study_date: "2020-03-18",
    stack_count: 158,
    nodules: [
      { nodule_id: "134503-T1-N1", track_id: "T1", lobe: "LUL (lingula)", center_mm: [-42.1, 18.9, -31.0], long: 7.4, short: 6.8, box_mean: 7.6, mean_hu: 45, type: "solid", det_score: 0.999 },
      { nodule_id: "134503-T1-N2", track_id: "T2", lobe: "RUL", center_mm: [38.4, 44.0, 12.1], long: 4.2, short: 3.8, box_mean: 4.5, mean_hu: 6, type: "ggo", det_score: 0.91 },
    ],
  },
  {
    study_uid: uid("134503.02"),
    patient_id: HERO,
    timepoint: "T2",
    rank: 2,
    day_offset: 744,
    study_date: "2021-03-27",
    stack_count: 152,
    nodules: [
      { nodule_id: "134503-T2-N1", track_id: "T1", lobe: "LUL (lingula)", center_mm: [-42.0, 19.1, -30.6], long: 9.8, short: 9.0, box_mean: 10.1, mean_hu: 38, type: "solid", det_score: 0.998 },
      { nodule_id: "134503-T2-N2", track_id: "T2", lobe: "RUL", center_mm: [38.0, 43.8, 12.6], long: null, short: null, box_mean: 4.3, mean_hu: 3, type: "part_solid", det_score: 0.83 },
    ],
  },
  {
    study_uid: uid("900101.00"),
    patient_id: "900101",
    timepoint: "T0",
    rank: 0,
    day_offset: null,
    study_date: "2018-06-02",
    stack_count: 0,
    nodules: [{ nodule_id: "900101-T0-N1", track_id: "A", lobe: "LLL", center_mm: [22.0, 12.0, 44.0], long: 3.4, short: 3.1, box_mean: 3.6, mean_hu: 120, type: "solid", det_score: 0.88 }],
  },
  {
    study_uid: uid("900102.00"),
    patient_id: "900102",
    timepoint: "T0",
    rank: 0,
    day_offset: null,
    study_date: "2020-11-15",
    stack_count: 0,
    nodules: [],
  },
]
