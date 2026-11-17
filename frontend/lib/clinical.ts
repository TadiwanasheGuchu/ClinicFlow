export const OBSERVATIONS: { type: string; label: string; unit: string; step: string; min: number; max: number }[] = [
  { type: "systolic_bp", label: "BP systolic", unit: "mmHg", step: "1", min: 50, max: 260 },
  { type: "diastolic_bp", label: "BP diastolic", unit: "mmHg", step: "1", min: 30, max: 160 },
  { type: "heart_rate", label: "Heart rate", unit: "bpm", step: "1", min: 20, max: 250 },
  { type: "temperature", label: "Temperature", unit: "°C", step: "0.1", min: 30, max: 44 },
  { type: "respiratory_rate", label: "Respiratory rate", unit: "/min", step: "1", min: 4, max: 80 },
  { type: "oxygen_saturation", label: "SpO₂", unit: "%", step: "1", min: 50, max: 100 },
  { type: "weight", label: "Weight", unit: "kg", step: "0.1", min: 0.3, max: 400 },
  { type: "height", label: "Height", unit: "cm", step: "0.1", min: 20, max: 250 },
  { type: "blood_glucose", label: "Blood glucose", unit: "mmol/L", step: "0.1", min: 0.5, max: 50 },
];
export const OBS_LABEL = Object.fromEntries(OBSERVATIONS.map((o) => [o.type, o.label]));

export const NOTE_SECTIONS: Record<string, { key: string; label: string }[]> = {
  consultation: [
    { key: "subjective", label: "Subjective (history, symptoms)" },
    { key: "objective", label: "Objective (examination, findings)" },
    { key: "assessment", label: "Assessment" },
    { key: "plan", label: "Plan" },
  ],
  progress: [
    { key: "subjective", label: "Subjective" },
    { key: "objective", label: "Objective" },
    { key: "assessment", label: "Assessment" },
    { key: "plan", label: "Plan" },
  ],
  procedure: [
    { key: "indication", label: "Indication" },
    { key: "procedure", label: "Procedure" },
    { key: "findings", label: "Findings" },
    { key: "plan", label: "Plan" },
  ],
  general: [{ key: "text", label: "Note" }],
};

export const NOTE_TYPE_LABEL: Record<string, string> = { consultation: "Consultation note", progress: "Progress note", procedure: "Procedure note", general: "General note" };
export const ENCOUNTER_TYPE_LABEL: Record<string, string> = { consultation: "Consultation", follow_up: "Follow-up", telephone: "Telephone consultation", procedure: "Procedure", other: "Other" };
export const SEVERITY_LABEL: Record<string, string> = { mild: "mild", moderate: "moderate", severe: "severe", unknown: "severity unknown" };
