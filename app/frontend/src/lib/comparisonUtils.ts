import type { ArmSuggestion, ComparisonSuggestion, DurationUnit, NewStudySuggestion, StudyGraphDto } from "@/types/apiDTOs";
import type { ArmComparison, ArmDraft, ArmRole, StudyArm } from "@/types/comparisons";

const createId = (prefix: string) => `${prefix}-${Math.random().toString(36).slice(2, 9)}`;

const cleaned = (items?: string[]) => (items ?? []).map((value) => value.trim()).filter(Boolean);

export const createArmDraft = (overrides?: Partial<ArmDraft>): ArmDraft => ({
  interventions: cleaned(overrides?.interventions),
  participants: overrides?.participants ?? "",
  features: overrides?.features ?? "",
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
    features: (arm.features ?? []).join(", "),
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

// The graph without what the form edits: its arms (with what they say about themselves, their comparisons and the
// populations that took part in them) and the countries of the study go, and the values nothing points to any more.
// Everything else of a graph the form starts from (the population of the study, its outcomes, designs, trial ids, the
// interventions of no arm) is kept as it is.
function withoutFormParts(graph: StudyGraphDto): { nodes: { id: string; kind: string; value?: string }[]; edges: { relation: string; source: string; target: string }[] } {
  const arms = new Set(graph.nodes.filter((node) => node.kind === "arm").map((node) => node.id));
  const armPopulations = new Set(graph.edges.filter((edge) => edge.relation === "participated" && arms.has(edge.source)).map((edge) => edge.target));
  const gone = new Set([...arms, ...armPopulations]);
  const edges = graph.edges
    .filter((edge) => !gone.has(edge.source) && !gone.has(edge.target) && !(edge.source === "study" && edge.relation === "in_country"))
    .map(({ relation, source, target }) => ({ relation, source, target }));
  const used = new Set(edges.flatMap((edge) => [edge.source, edge.target]));
  const nodes = graph.nodes
    .filter((node) => !gone.has(node.id) && used.has(node.id))
    .map((node) => ({ id: node.id, kind: node.kind, ...(node.value === null ? {} : { value: node.value }) }));
  return { nodes, edges };
}

const first = (graph: StudyGraphDto, relation: string, source: string): string | undefined => {
  const edge = graph.edges.find((candidate) => candidate.relation === relation && candidate.source === source);
  return graph.nodes.find((node) => node.id === edge?.target)?.value ?? undefined;
};
const all = (graph: StudyGraphDto, relation: string, source: string): string[] =>
  graph.edges
    .filter((edge) => edge.relation === relation && edge.source === source)
    .map((edge) => graph.nodes.find((node) => node.id === edge.target)?.value)
    .filter((value): value is string => Boolean(value));

// A duration as the form has it ("12 weeks" is 12 and "weeks"); one in no unit of the form is left out.
const formDuration = (text: string | undefined): { value: number; unit: DurationUnit } | undefined => {
  const match = text?.match(/^(\d+(?:\.\d+)?)\s+(\w+?)s?$/);
  const unit = match ? (`${match[2]}s` as DurationUnit) : undefined;
  return match && unit && ["hours", "days", "weeks", "months", "years"].includes(unit) ? { value: Number(match[1]), unit } : undefined;
};

// The form of a new study prefilled from a graph (that of a report): its arms, comparisons, countries and participants,
// with the graph itself as the base the form is written back onto (see buildGraph).
export function suggestionFromGraph(graph: StudyGraphDto, shortName: string): NewStudySuggestion {
  const arms = graph.nodes.filter((node) => node.kind === "arm");
  const index = new Map(arms.map((arm, position) => [arm.id, position]));
  const participantsOf = (owner: string): number | undefined => {
    const population = graph.edges.find((edge) => edge.relation === "participated" && edge.source === owner)?.target;
    return population ? Number(first(graph, "has_size", population)) || undefined : undefined;
  };
  return {
    short_name: shortName,
    status_of_study: "" as NewStudySuggestion["status_of_study"],
    countries: all(graph, "in_country", "study"),
    number_of_participants: participantsOf("study") ?? 0,
    arms: arms.map((arm) => ({
      interventions: all(graph, "receives", arm.id),
      role: first(graph, "has_role", arm.id) === "control" ? "control" : "intervention",
      participants: participantsOf(arm.id),
      features: all(graph, "has_feature", arm.id),
      dosage: first(graph, "has_dosage", arm.id),
      frequency: first(graph, "has_frequency", arm.id),
      route: first(graph, "has_route", arm.id),
      duration: formDuration(first(graph, "has_duration", arm.id)),
    })),
    comparisons: graph.edges
      .filter((edge) => edge.relation === "compared_with" && index.has(edge.source) && index.has(edge.target))
      .map((edge) => ({ evaluated: index.get(edge.source)!, comparator: index.get(edge.target)! })),
    graph,
  };
}

// The arms and their comparisons as the graph of a study (JSON, see `graph` of the study schema), written onto `base` (the
// graph the form was prefilled from, whose other parts it keeps): an entity for every arm in a comparison and a comparison
// edge per pair. What an arm says about itself is edges to value entities (its interventions, role, features, dosage,
// frequency, route and duration), one entity per distinct value however many arms have it, and the participants of an arm are a
// population entity that took part in it. Comparisons with an arm without interventions are left out; null if none is
// left. The countries of the study are edges from the study itself. A duration of the study holds for every arm that has
// none of its own (the study derives its duration from its arms), and its participants are the size of its population.
export function buildGraph(
  arms: StudyArm[],
  comparisons: ArmComparison[],
  countries: string[] = [],
  base?: StudyGraphDto,
  study: { duration?: string; participants?: string } = {},
): string | null {
  const studyDuration = study.duration;
  type Node = { id: string; kind: string; value?: string };
  type Edge = { relation: string; source: string; target: string };
  const kept = base ? withoutFormParts(base) : { nodes: [], edges: [] };
  const nodes: Node[] = kept.nodes;
  const edges: Edge[] = kept.edges;
  const find = (kind: string, value?: string) =>
    nodes.find((node) => node.kind === kind && (value === undefined || (node.value ?? "").toLowerCase() === value.toLowerCase()));
  const add = (kind: string, value?: string): string => {
    let number = nodes.filter((entry) => entry.kind === kind).length + 1;
    while (nodes.some((entry) => entry.id === `${kind}${number}`)) number += 1;
    const node = { id: `${kind}${number}`, kind, ...(value === undefined ? {} : { value }) };
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
    ...cleaned(arm.features.split(",")).map((value): [string, string, string] => ["has_feature", "feature", value]),
    ...(["dosage", "frequency", "route"] as const).flatMap((key): [string, string, string][] => (arm[key].trim() ? [[`has_${key}`, key, arm[key].trim()]] : [])),
    ...((armDuration(arm) || studyDuration) ? ([["has_duration", "duration", armDuration(arm) || studyDuration!]] as [string, string, string][]) : []),
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
  // The countries of the study, from the study itself (its id in the graph is `study`).
  for (const country of cleaned(countries)) link("in_country", "study", valueNode("country", country));
  // The participants of the study: the size of its population (made if it has none, gone with its last value).
  let population = edges.find((edge) => edge.relation === "participated" && edge.source === "study")?.target;
  if (population) edges.splice(0, edges.length, ...edges.filter((edge) => !(edge.relation === "has_size" && edge.source === population)));
  if (study.participants?.trim()) {
    if (!population) {
      population = add("population");
      link("participated", "study", population);
    }
    link("has_size", population, valueNode("size", study.participants.trim()));
  } else if (population && !edges.some((edge) => edge.source === population)) {
    const empty = population;
    edges.splice(0, edges.length, ...edges.filter((edge) => edge.target !== empty));
  }
  const used = new Set(edges.flatMap((edge) => [edge.source, edge.target]));
  return JSON.stringify({ nodes: nodes.filter((node) => used.has(node.id)), edges });
}
