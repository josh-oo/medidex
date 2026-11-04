import type { ArmSuggestion } from "@/types/apiDTOs";
import type { ArmDraft, ComparisonGroup } from "@/types/comparisons";

const createComparisonId = () => `comparison-${Math.random().toString(36).slice(2, 9)}`;

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

export const armDraftFromSuggestion = (arm?: ArmSuggestion): ArmDraft =>
  createArmDraft({
    interventions: arm?.interventions,
    participants: arm?.participants ? String(arm.participants) : "",
    dosage: arm?.dosage,
    frequency: arm?.frequency,
    route: arm?.route,
    durationValue: arm?.duration ? String(arm.duration.value) : "",
    durationUnit: arm?.duration?.unit ?? "",
  });

export const createComparisonGroup = (overrides?: Partial<Pick<ComparisonGroup, "a" | "b">>): ComparisonGroup => ({
  id: createComparisonId(),
  a: overrides?.a ?? createArmDraft(),
  b: overrides?.b ?? createArmDraft(),
});

export const hasValidComparisonGroups = (groups: ComparisonGroup[]): boolean =>
  groups.some((group) => cleaned(group.a.interventions).length > 0 && cleaned(group.b.interventions).length > 0);

// The duration of an arm as the study keeps it ("12 weeks"); empty if the value or the unit is missing.
const armDuration = (arm: ArmDraft): string => {
  const value = arm.durationValue.trim();
  return value && arm.durationUnit ? `${value} ${arm.durationUnit}` : "";
};

// The comparisons as the graph of a study (JSON, see `graph` of the study schema): an entity for every distinct arm (the
// placebo arm of "A vs placebo" and "B vs placebo" is one, so a study with three arms is two or three comparisons) and a
// comparison edge per pair. What an arm says about itself is edges to value entities (its interventions, role, dosage,
// frequency, route and duration), one entity per distinct value however many arms have it, and the participants of an arm
// are a population entity that took part in it. Pairs with an arm without interventions are left out; null if no pair is left.
export function buildGraph(groups: ComparisonGroup[]): string | null {
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
  // relation without `has_`, except the interventions): the key of the arm is all of it, so the same arm in two comparisons
  // is one entity.
  const attributes = (arm: ArmDraft, role: "intervention" | "control"): [string, string, string][] => [
    ...cleaned(arm.interventions).map((value): [string, string, string] => ["receives", "intervention", value]),
    ["has_role", "role", role],
    ...(["dosage", "frequency", "route"] as const).flatMap((key): [string, string, string][] => (arm[key].trim() ? [[`has_${key}`, key, arm[key].trim()]] : [])),
    ...(armDuration(arm) ? ([["has_duration", "duration", armDuration(arm)]] as [string, string, string][]) : []),
  ];
  const arms = new Map<string, string>();
  const armOf = (arm: ArmDraft, role: "intervention" | "control"): string => {
    const key = attributes(arm, role).map((attribute) => attribute.join("\u0000").toLowerCase()).sort().join("\u0001");
    let id = arms.get(key);
    if (!id) {
      id = add("arm");
      arms.set(key, id);
      for (const [relation, kind, value] of attributes(arm, role)) link(relation, id, valueNode(kind, value));
    }
    return id;
  };
  let comparisons = 0;
  for (const group of groups) {
    if (cleaned(group.a.interventions).length === 0 || cleaned(group.b.interventions).length === 0) continue;
    const [source, target] = [armOf(group.a, "intervention"), armOf(group.b, "control")];
    link("compared_with", source, target);
    comparisons += 1;
    for (const [arm, id] of [[group.a, source], [group.b, target]] as const) {
      // An arm has one population, however many comparisons it is in.
      if (arm.participants.trim() && !edges.some((edge) => edge.relation === "participated" && edge.source === id)) {
        const population = add("population");
        link("participated", id, population);
        link("has_size", population, valueNode("size", arm.participants.trim()));
      }
    }
  }
  return comparisons === 0 ? null : JSON.stringify({ nodes, edges });
}
