import type { DurationUnit } from "@/types/apiDTOs";

// An arm of the study being added: the interventions it gives, and its dosage and duration (all optional but
// the interventions).
export type ArmDraft = {
  interventions: string[];
  participants: string;
  dosage: string;
  frequency: string;
  route: string;
  durationValue: string;
  durationUnit: DurationUnit | "";
};

// Whether the arm gets the evaluated intervention or is the control it is compared against.
export type ArmRole = "intervention" | "control";

// An arm of the form: every arm is entered once, however many comparisons it is in.
export type StudyArm = ArmDraft & {
  id: string;
  role: ArmRole;
};

// Two arms that are compared, by their ids: the evaluated arm (source) and its comparator (target).
export type ArmComparison = {
  id: string;
  source: string;
  target: string;
};
