import type { DurationUnit } from "@/types/apiDTOs";

export type ComparisonSideKey = "a" | "b";

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

// Two arms that are compared. The first is the intervention arm, the second its control.
export type ComparisonGroup = {
  id: string;
  a: ArmDraft;
  b: ArmDraft;
};
