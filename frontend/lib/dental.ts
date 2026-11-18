export const CONDITION_LABEL: Record<string, string> = {
  sound: "Sound", caries: "Caries", filled: "Filled", crown: "Crown", root_canal: "Root canal treated",
  missing: "Missing", extracted: "Extracted", implant: "Implant", bridge: "Bridge", fracture: "Fracture",
  watch: "Watch", other: "Other",
};

/** Short code shown inside a tooth cell, so the chart never relies on colour. */
export const CONDITION_CODE: Record<string, string> = {
  sound: "S", caries: "C", filled: "F", crown: "Cr", root_canal: "RCT", missing: "M", extracted: "X",
  implant: "Imp", bridge: "Br", fracture: "Fx", watch: "W", other: "O",
};

export const PLAN_STATUS: Record<string, string> = {
  draft: "Draft", proposed: "Quoted — awaiting patient", accepted: "Accepted", declined: "Declined",
  completed: "Completed", cancelled: "Cancelled",
};

// FDI layout as seen facing the patient: upper right, upper left / lower right, lower left.
export const PERMANENT_ROWS = [
  [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28],
  [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38],
];
export const PRIMARY_ROWS = [
  [55, 54, 53, 52, 51, 61, 62, 63, 64, 65],
  [85, 84, 83, 82, 81, 71, 72, 73, 74, 75],
];

export const MEASURE_LABEL: Record<string, string> = {
  pain_nrs: "Pain (0–10)", psfs: "Function, PSFS (0–10)", rom: "Range of movement (°)", strength_mrc: "Strength, MRC (0–5)", custom: "Other",
};
export const OUTCOME_LABEL: Record<string, string> = {
  goals_met: "Goals met", partly_met: "Goals partly met", not_met: "Goals not met", self_discharged: "Self-discharged", referred_on: "Referred on",
};
