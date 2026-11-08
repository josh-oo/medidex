import type { DurationUnit } from "@/types/apiDTOs";

// An arm of the study being added: the interventions it gives, and its features, dosage and duration (all optional but
// the interventions). The features are one text, comma-separated ("group, nurse-led").
export type ArmDraft = {
  interventions: string[];
  participants: string;
  features: string;
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
  // The arm of the graph it was prefilled from, whose participants keep what the form does not show (their sex, age, ...).
  source?: string;
};

// Two arms that are compared, by their ids: the evaluated arm (source) and its comparator (target).
export type ArmComparison = {
  id: string;
  source: string;
  target: string;
};

// Whether an outcome is a primary or secondary one of the study, or one it gives no role.
export type OutcomeRole = "primary" | "secondary" | "other";

// An outcome of the study being added: what it measures and when (its time points separated by "; ").
export type OutcomeDraft = {
  id: string;
  role: OutcomeRole;
  measure: string;
  timePoint: string;
};

// What the study being added says besides its arms, countries, participants and duration: who its participants are,
// its design, registration ids, the interventions of no arm, and its outcomes.
export type StudyDetails = {
  conditions: string[];
  sex: string[];
  age: string;
  designs: string[];
  trialIds: string[];
  interventions: string[];
  outcomes: OutcomeDraft[];
};
