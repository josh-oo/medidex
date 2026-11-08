import type { ArmSuggestion, ComparisonSuggestion, DurationUnit, NewStudySuggestion, StudyGraphDto } from "@/types/apiDTOs";
import type { ArmComparison, ArmDraft, ArmRole, OutcomeDraft, OutcomeRole, StudyArm, StudyDetails } from "@/types/comparisons";

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

export const armFromSuggestion = (arm: ArmSuggestion): StudyArm => ({
  ...createStudyArm(arm.role ?? "intervention", {
    interventions: arm.interventions,
    participants: arm.participants ? String(arm.participants) : "",
    features: (arm.features ?? []).join(", "),
    dosage: arm.dosage,
    frequency: arm.frequency,
    route: arm.route,
    durationValue: arm.duration ? String(arm.duration.value) : "",
    durationUnit: arm.duration?.unit ?? "",
  }),
  source: arm.source,
});

export const createOutcome = (role: OutcomeRole = "primary", measure = "", timePoint = ""): OutcomeDraft => ({
  id: createId("outcome"),
  role,
  measure,
  timePoint,
});

export const emptyStudyDetails = (): StudyDetails => ({
  conditions: [],
  sex: [],
  age: "",
  designs: [],
  trialIds: [],
  interventions: [],
  outcomes: [],
});

// The relation from the study to an outcome of each role.
const OUTCOME_RELATIONS: Record<OutcomeRole, string> = {
  primary: "has_primary_outcome",
  secondary: "has_secondary_outcome",
  other: "has_outcome",
};

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

// The relations from the study the form edits (its participants, outcomes and arms are entities of their own).
const STUDY_FORM_RELATIONS = new Set(["in_country", "has_design", "has_trial_id", "has_intervention"]);

// The graph without what the form edits: its arms (with what they say about themselves, their comparisons and the
// populations that took part in them), the population and the outcomes of the study, its countries, designs, trial ids and
// interventions of no arm go, and the values nothing points to any more. Whatever else a graph the form starts from has
// is kept as it is.
function withoutFormParts(graph: StudyGraphDto): { nodes: { id: string; kind: string; value?: string }[]; edges: { relation: string; source: string; target: string }[] } {
  const arms = new Set(graph.nodes.filter((node) => node.kind === "arm").map((node) => node.id));
  const populations = new Set(graph.edges.filter((edge) => edge.relation === "participated" && (arms.has(edge.source) || edge.source === "study")).map((edge) => edge.target));
  const outcomes = graph.nodes.filter((node) => node.kind === "outcome").map((node) => node.id);
  const gone = new Set([...arms, ...populations, ...outcomes]);
  const edges = graph.edges
    .filter((edge) => !gone.has(edge.source) && !gone.has(edge.target) && !(edge.source === "study" && STUDY_FORM_RELATIONS.has(edge.relation)))
    .map(({ relation, source, target }) => ({ relation, source, target }));
  const used = new Set(edges.flatMap((edge) => [edge.source, edge.target]));
  const nodes = graph.nodes
    .filter((node) => !gone.has(node.id) && used.has(node.id))
    .map((node) => ({ id: node.id, kind: node.kind, ...(node.value === null ? {} : { value: node.value }) }));
  return { nodes, edges };
}

// The time points of an outcome as the form has them, in one field: "at 4 weeks; at 8 weeks".
const TIME_POINT_SEPARATOR = "; ";

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

// What the form shows of the study besides its arms, countries, participants and duration, read from a graph.
export function detailsFromGraph(graph?: StudyGraphDto): StudyDetails {
  if (!graph) return emptyStudyDetails();
  const population = graph.edges.find((edge) => edge.relation === "participated" && edge.source === "study")?.target;
  const seen = new Set<string>();
  const outcomes = (Object.entries(OUTCOME_RELATIONS) as [OutcomeRole, string][]).flatMap(([role, relation]) =>
    graph.edges
      .filter((edge) => edge.relation === relation && edge.source === "study" && !seen.has(edge.target))
      .map((edge) => {
        seen.add(edge.target);
        return createOutcome(role, first(graph, "measures", edge.target) ?? "", all(graph, "has_time_point", edge.target).join(TIME_POINT_SEPARATOR));
      })
      .filter((outcome) => outcome.measure)
  );
  return {
    conditions: population ? all(graph, "has_condition", population) : [],
    sex: population ? all(graph, "has_sex", population) : [],
    age: (population && first(graph, "has_age", population)) || "",
    designs: all(graph, "has_design", "study"),
    trialIds: all(graph, "has_trial_id", "study"),
    interventions: all(graph, "has_intervention", "study"),
    outcomes,
  };
}

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
      source: arm.id,
    })),
    comparisons: graph.edges
      .filter((edge) => edge.relation === "compared_with" && index.has(edge.source) && index.has(edge.target))
      .map((edge) => ({ evaluated: index.get(edge.source)!, comparator: index.get(edge.target)! })),
    graph,
  };
}

// The arms and their comparisons as the graph of a study (see `graph` of the study schema), written onto `base` (the graph
// the form was prefilled from, whose other parts it keeps): an entity for every arm in a comparison and a comparison edge
// per pair. What an arm says about itself is edges to value entities (its interventions, role, features, dosage,
// frequency, route and duration), one entity per distinct value however many arms have it, and the participants of an arm
// are a population entity that took part in it (with what the population of the arm it was prefilled from says besides
// its size). Comparisons with an arm without interventions are left out. The countries, designs, trial ids and
// interventions of no arm are edges from the study itself, its participants are its population (their number, conditions,
// sex and age), and its outcomes are an entity each with what it measures and when. A duration of the study holds for
// every arm that has none of its own (the study derives its duration from its arms).
export function graphFromForm(
  arms: StudyArm[],
  comparisons: ArmComparison[],
  countries: string[] = [],
  base?: StudyGraphDto,
  study: { duration?: string; participants?: string; details?: StudyDetails } = {},
): StudyGraphDto {
  const studyDuration = study.duration;
  const details = study.details ?? emptyStudyDetails();
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
  // A population that took part in `owner`, with its values (made only if it has one).
  const populate = (owner: string, values: [string, string, string][]) => {
    if (values.length === 0) return;
    const population = add("population");
    link("participated", owner, population);
    for (const [relation, kind, value] of values) link(relation, population, valueNode(kind, value));
  };
  // What the population of an arm of `base` says besides its size.
  const baseArmPopulation = (arm: string): [string, string, string][] => {
    const population = base?.edges.find((edge) => edge.relation === "participated" && edge.source === arm)?.target;
    if (!base || !population) return [];
    return base.edges
      .filter((edge) => edge.source === population && edge.relation !== "has_size")
      .flatMap((edge): [string, string, string][] => {
        const node = base.nodes.find((candidate) => candidate.id === edge.target);
        return node?.value ? [[edge.relation, node.kind, node.value]] : [];
      });
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
      populate(id, [
        ...(arm.participants.trim() ? [["has_size", "size", arm.participants.trim()] as [string, string, string]] : []),
        ...(arm.source ? baseArmPopulation(arm.source) : []),
      ]);
    }
    return id;
  };
  const byId = new Map(arms.map((arm) => [arm.id, arm]));
  const valid = comparisons.filter((comparison) => hasInterventions(byId.get(comparison.source)) && hasInterventions(byId.get(comparison.target)));
  // The entities in the order of the arms of the form (arm1 is A), then the comparisons between them.
  for (const arm of arms) {
    if (valid.some((comparison) => comparison.source === arm.id || comparison.target === arm.id)) entityOf(arm);
  }
  for (const comparison of valid) link("compared_with", entityOf(byId.get(comparison.source)!), entityOf(byId.get(comparison.target)!));
  // What the study says of itself (its id in the graph is `study`).
  for (const country of cleaned(countries)) link("in_country", "study", valueNode("country", country));
  for (const design of cleaned(details.designs)) link("has_design", "study", valueNode("design", design));
  for (const trialId of cleaned(details.trialIds)) link("has_trial_id", "study", valueNode("trial_id", trialId));
  for (const intervention of cleaned(details.interventions)) link("has_intervention", "study", valueNode("intervention", intervention));
  // The participants of the study: its population, with their number, conditions, sex and age.
  populate("study", [
    ...(study.participants?.trim() ? [["has_size", "size", study.participants.trim()] as [string, string, string]] : []),
    ...cleaned(details.conditions).map((value): [string, string, string] => ["has_condition", "condition", value]),
    ...cleaned(details.sex).map((value): [string, string, string] => ["has_sex", "sex", value]),
    ...(details.age.trim() ? [["has_age", "age", details.age.trim()] as [string, string, string]] : []),
  ]);
  // The outcomes of the study: what each measures, and when.
  for (const outcome of details.outcomes) {
    if (!outcome.measure.trim()) continue;
    const id = add("outcome");
    link(OUTCOME_RELATIONS[outcome.role], "study", id);
    link("measures", id, valueNode("measure", outcome.measure.trim()));
    for (const timePoint of outcome.timePoint.split(TIME_POINT_SEPARATOR.trim())) {
      if (timePoint.trim()) link("has_time_point", id, valueNode("time_point", timePoint.trim()));
    }
  }
  const used = new Set(edges.flatMap((edge) => [edge.source, edge.target]));
  return {
    nodes: nodes.filter((node) => used.has(node.id)).map((node) => ({ id: node.id, kind: node.kind, value: node.value ?? null, tagId: null })),
    edges,
  };
}

// The graph of the form as the study keeps it (JSON); null if no comparison of two arms with interventions is left.
export function buildGraph(...args: Parameters<typeof graphFromForm>): string | null {
  const [arms, comparisons] = args;
  if (!hasValidComparisons(arms, comparisons)) return null;
  const { nodes, edges } = graphFromForm(...args);
  return JSON.stringify({ nodes: nodes.map(({ id, kind, value }) => ({ id, kind, ...(value === null ? {} : { value }) })), edges });
}
