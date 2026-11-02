import type { ArmSuggestion, ComparisonSuggestion } from "@/types/apiDTOs";
import type { ArmComparison, ArmDraft, ArmRole, StudyArm } from "@/types/comparisons";

const createId = (prefix: string) => `${prefix}-${Math.random().toString(36).slice(2, 9)}`;

const cleaned = (items?: string[]) => (items ?? []).map((value) => value.trim()).filter(Boolean);

export const createArmDraft = (overrides?: Partial<ArmDraft>): ArmDraft => ({
  interventions: cleaned(overrides?.interventions),
  participants: overrides?.participants ?? "",
  dosage: overrides?.dosage ?? "",
  frequency: overrides?.frequency ?? "",
  route: overrides?.route ?? "",
  durationValue: overrides?.durationValue ?? "",
  durationUnit: overrides?.durationUnit ?? "",
});

export const createStudyArm = (role: ArmRole, overrides?: Partial<ArmDraft>): StudyArm => ({
  id: createId("arm"),
  role,
  ...createArmDraft(overrides),
});

export const armFromSuggestion = (arm: ArmSuggestion): StudyArm =>
  createStudyArm(arm.role ?? "intervention", {
    interventions: arm.interventions,
    participants: arm.participants ? String(arm.participants) : "",
    dosage: arm.dosage,
    frequency: arm.frequency,
    route: arm.route,
    durationValue: arm.duration ? String(arm.duration.value) : "",
    durationUnit: arm.duration?.unit ?? "",
  });

// The arms in the order the form lists them: the intervention arms first, then the controls, each in the order they came.
export const orderArms = (arms: StudyArm[]): StudyArm[] => [
  ...arms.filter((arm) => arm.role !== "control"),
  ...arms.filter((arm) => arm.role === "control"),
];

export const createComparison =(source: string, target: string): ArmComparison => ({ id: createId("comparison"), source, target });

// The comparisons of a suggestion between the arms made from it (in the same order); those naming no arm are left out.
export const comparisonsFromSuggestion = (arms: StudyArm[], comparisons: ComparisonSuggestion[]): ArmComparison[] =>
  comparisons.flatMap(({ evaluated, comparator }) =>
    arms[evaluated] && arms[comparator] && evaluated !== comparator ? [createComparison(arms[evaluated].id, arms[comparator].id)] : []
  );

// The name of an arm in the form: A, B, C, ... by its position.
export const armLetter = (index: number): string => String.fromCharCode(65 + (index % 26)) + (index >= 26 ? String(Math.floor(index / 26)) : "");

// A new comparison of two arms, from the evaluated arm to its comparator: an intervention arm is evaluated against a control,
// otherwise the arm it was started from is the evaluated one.
export const comparisonBetween = (from: StudyArm, to: StudyArm): ArmComparison =>
  from.role === "control" && to.role === "intervention" ? createComparison(to.id, from.id) : createComparison(from.id, to.id);

export const areCompared = (comparisons: ArmComparison[], a: string, b: string): boolean =>
  comparisons.some((comparison) => (comparison.source === a && comparison.target === b) || (comparison.source === b && comparison.target === a));

const hasInterventions = (arm?: StudyArm): arm is StudyArm => Boolean(arm && cleaned(arm.interventions).length > 0);

export const hasValidComparisons = (arms: StudyArm[], comparisons: ArmComparison[]): boolean => {
  const byId = new Map(arms.map((arm) => [arm.id, arm]));
  return comparisons.some((comparison) => hasInterventions(byId.get(comparison.source)) && hasInterventions(byId.get(comparison.target)));
};

// The duration of an arm as the study keeps it ("12 weeks"); empty if the value or the unit is missing.
const armDuration = (arm: ArmDraft): string => {
  const value = arm.durationValue.trim();
  return value && arm.durationUnit ? `${value} ${arm.durationUnit}` : "";
};

// The arms and their comparisons as the graph of a study (JSON, see `graph` of the study schema): an entity for every arm
// in a comparison and a comparison edge per pair. What an arm says about itself is edges to value entities (its
// interventions, role, dosage, frequency, route and duration), one entity per distinct value however many arms have it,
// and the participants of an arm are a population entity that took part in it. Comparisons with an arm without
// interventions are left out; null if none is left.
export function buildGraph(arms: StudyArm[], comparisons: ArmComparison[]): string | null {
  type Node = { id: string; kind: string; value?: string };
  type Edge = { relation: string; source: string; target: string };
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  const find = (kind: string, value?: string) =>
    nodes.find((node) => node.kind === kind && (value === undefined || (node.value ?? "").toLowerCase() === value.toLowerCase()));
  const add = (kind: string, value?: string): string => {
    const node = { id: `${kind}${nodes.filter((entry) => entry.kind === kind).length + 1}`, kind, ...(value === undefined ? {} : { value }) };
    nodes.push(node);
    return node.id;
  };
  const valueNode = (kind: string, value: string) => find(kind, value)?.id ?? add(kind, value);
  const link = (relation: string, source: string, target: string) => {
    if (!edges.some((edge) => edge.relation === relation && edge.source === source && edge.target === target)) {
      edges.push({ relation, source, target });
    }
  };
  // What an arm says about itself, by relation of the study ontology (the entity kind of each value is the name of the
  // relation without `has_`, except the interventions).
  const attributes = (arm: StudyArm): [string, string, string][] => [
    ...cleaned(arm.interventions).map((value): [string, string, string] => ["receives", "intervention", value]),
    ["has_role", "role", arm.role],
    ...(["dosage", "frequency", "route"] as const).flatMap((key): [string, string, string][] => (arm[key].trim() ? [[`has_${key}`, key, arm[key].trim()]] : [])),
    ...(armDuration(arm) ? ([["has_duration", "duration", armDuration(arm)]] as [string, string, string][]) : []),
  ];
  const entities = new Map<string, string>();
  const entityOf = (arm: StudyArm): string => {
    let id = entities.get(arm.id);
    if (!id) {
      id = add("arm");
      entities.set(arm.id, id);
      for (const [relation, kind, value] of attributes(arm)) link(relation, id, valueNode(kind, value));
      if (arm.participants.trim()) {
        const population = add("population");
        link("participated", id, population);
        link("has_size", population, valueNode("size", arm.participants.trim()));
      }
    }
    return id;
  };
  const byId = new Map(arms.map((arm) => [arm.id, arm]));
  const valid = comparisons.filter((comparison) => hasInterventions(byId.get(comparison.source)) && hasInterventions(byId.get(comparison.target)));
  if (valid.length === 0) return null;
  // The entities in the order of the arms of the form (arm1 is A), then the comparisons between them.
  for (const arm of arms) {
    if (valid.some((comparison) => comparison.source === arm.id || comparison.target === arm.id)) entityOf(arm);
  }
  for (const comparison of valid) link("compared_with", entityOf(byId.get(comparison.source)!), entityOf(byId.get(comparison.target)!));
  return JSON.stringify({ nodes, edges });
}
