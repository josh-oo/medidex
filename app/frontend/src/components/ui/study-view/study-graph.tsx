// The graph of a study (the study ontology, config/medidex-study.yaml): entities such as the arms and populations of the study, connected
// by relations such as the comparison of two arms ("Drug A (10 mg) vs Placebo"). An entity has no properties, only
// relations: an arm is described by the interventions, dosage and duration it points to. Which entities and relations
// exist and how they look comes from the study schema.
import type { ReactNode } from "react";
import { useStudySchema } from "@/hooks/use-study-schema";
import { useStudyGraph } from "@/hooks/use-study-graph";
import { iconByName } from "@/lib/icons";
import type {
  GraphEntitySchemaDto,
  GraphRelationSchemaDto,
  GraphSchemaDto,
  StudyGraphDto,
  StudyGraphNodeDto,
} from "@/types/apiDTOs";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { DetailRow } from "@/components/ui/study-view/detail-row";

// The id edges use for the study itself (the root entity of the graph schema).
const STUDY_ID = "study";

// An end of an edge: the entity kind and, unless it is the study itself, the node.
interface End {
  entity: GraphEntitySchemaDto;
  node: StudyGraphNodeDto | null;
}

const entityOf = (schema: GraphSchemaDto, kind: string): GraphEntitySchemaDto | undefined =>
  schema.entities.find((entity) => entity.key === kind);

const endOf = (schema: GraphSchemaDto, graph: StudyGraphDto, id: string): End | undefined => {
  if (id === STUDY_ID) {
    const root = schema.entities.find((entity) => entity.root);
    return root ? { entity: root, node: null } : undefined;
  }
  const node = graph.nodes.find((candidate) => candidate.id === id);
  const entity = node && entityOf(schema, node.kind);
  return node && entity ? { entity, node } : undefined;
};

// What a node says about itself: the values at the end of its attribute relations (the interventions, dosage, ... of an
// arm), as [relation, values] in the order of the schema.
const attributesOf = (schema: GraphSchemaDto, graph: StudyGraphDto, node: StudyGraphNodeDto) =>
  schema.relations
    .filter((relation) => relation.attribute && relation.source.includes(node.kind))
    .map((relation) => {
      const values = graph.edges
        .filter((edge) => edge.relation === relation.key && edge.source === node.id)
        .flatMap((edge) => graph.nodes.filter((candidate) => candidate.id === edge.target && candidate.value));
      return { relation, tags: Boolean(entityOf(schema, relation.target[0])?.value?.category), values: values.map((value) => value.value as string) };
    })
    .filter(({ values }) => values.length > 0);

// A node as a line: the tags it points to joined by " + ", then its other values in parentheses ("A + B (10 mg, 5 weeks)").
// `all` also includes what the schema leaves out of a line (e.g. the role of an arm).
const nodeText = (schema: GraphSchemaDto, graph: StudyGraphDto, node: StudyGraphNodeDto, all = false): string => {
  const attributes = attributesOf(schema, graph, node).filter(({ relation }) => all || relation.line);
  const title = attributes.filter(({ tags }) => tags).flatMap(({ values }) => values).join(" + ");
  const details = attributes.filter(({ tags }) => !tags).flatMap(({ values }) => values).join(", ");
  return title && details ? `${title} (${details})` : title || details;
};

const endText = (schema: GraphSchemaDto, graph: StudyGraphDto, end: End): string =>
  end.node ? nodeText(schema, graph, end.node) : end.entity.label;

// The edges of a relation, each as the two ends it connects (an edge whose nodes are missing is left out).
const edgesOf = (schema: GraphSchemaDto, graph: StudyGraphDto, relation: GraphRelationSchemaDto) =>
  graph.edges
    .filter((edge) => edge.relation === relation.key)
    .flatMap((edge) => {
      const from = endOf(schema, graph, edge.source);
      const to = endOf(schema, graph, edge.target);
      return from && to ? [{ from, to }] : [];
    });

// The edges of a relation as lines ("A + B vs C"), or an older study's plain text as it is.
export function relationText(schema: GraphSchemaDto, graph: StudyGraphDto | null | undefined, relation: GraphRelationSchemaDto): string {
  if (!graph) return "";
  const lines = edgesOf(schema, graph, relation).map(({ from, to }) =>
    [endText(schema, graph, from), endText(schema, graph, to)].filter(Boolean).join(relation.separator),
  );
  return lines.length > 0 ? lines.join("; ") : (graph.text ?? "");
}

function Chip({ schema, graph, end }: { schema: GraphSchemaDto; graph: StudyGraphDto; end: End }) {
  const { entity, node } = end;
  const title = node ? nodeText(schema, graph, node) : entity.label;
  // What the line leaves out (e.g. the role of an arm) is shown next to it.
  const rest = node ? attributesOf(schema, graph, node).filter(({ relation }) => !relation.line).flatMap(({ values }) => values) : [];
  return (
    <span className="rounded-md bg-muted px-1.5 py-0.5 text-xs leading-snug text-foreground">
      {title || entity.label}
      {rest.length > 0 && <span className="ml-1.5 text-muted-foreground">{rest.join(" · ")}</span>}
    </span>
  );
}

// The graph of a study in its details (rows of a `<dl>`): a row per relation between entities with its edges, one per line, and
// a row per kind of entity for those no relation connects (e.g. an arm that is compared with none). Rows without content are left out.
export function StudyGraphBlock({ studyId }: { studyId: number }): ReactNode {
  const { schema } = useStudySchema();
  const graph = useStudyGraph(studyId);
  if (!schema || !graph) return null;
  const relations = schema.graph.relations
    .filter((relation) => !relation.attribute)
    .map((relation) => ({ relation, edges: edgesOf(schema.graph, graph, relation) }))
    .filter(({ edges }) => edges.length > 0);
  const connected = new Set(relations.flatMap(({ edges }) => edges.flatMap(({ from, to }) => [from.node?.id, to.node?.id])));
  const loose = schema.graph.entities
    .filter((entity) => !entity.root && !entity.value)
    .map((entity) => ({ entity, nodes: graph.nodes.filter((node) => node.kind === entity.key && !connected.has(node.id)) }))
    .filter(({ nodes }) => nodes.length > 0);
  const fallback = relations.length === 0 && loose.length === 0 ? schema.graph.relations.find((relation) => !relation.attribute) : undefined;

  return (
    <>
      {relations.map(({ relation, edges }) => (
        <DetailRow key={relation.key} icon={relation.icon} label={relation.label}>
          <ul className="space-y-1">
            {edges.map(({ from, to }, index) => (
              <li key={index} className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
                <Chip schema={schema.graph} graph={graph} end={from} />
                <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                  {relation.separator.trim() || "·"}
                </span>
                <Chip schema={schema.graph} graph={graph} end={to} />
              </li>
            ))}
          </ul>
        </DetailRow>
      ))}
      {loose.map(({ entity, nodes }) => (
        <DetailRow key={entity.key} icon={entity.icon} label={entity.label}>
          <ul className="flex flex-wrap gap-1">
            {nodes.map((node) => (
              <li key={node.id}>
                <Chip schema={schema.graph} graph={graph} end={{ entity, node }} />
              </li>
            ))}
          </ul>
        </DetailRow>
      ))}
      {fallback && graph.text && (
        <DetailRow icon={fallback.icon} label={fallback.label}>
          <p className="leading-relaxed">{graph.text}</p>
        </DetailRow>
      )}
    </>
  );
}

// The relations of a study that are shown on its card, one line each (e.g. "Drug A vs Placebo").
export function StudyCardGraph({ studyId }: { studyId: number }): ReactNode {
  const { schema } = useStudySchema();
  const graph = useStudyGraph(studyId);
  if (!schema || !graph) return null;
  return schema.graph.relations
    .filter((relation) => relation.card)
    .map((relation) => ({ relation, text: relationText(schema.graph, graph, relation) }))
    .filter(({ text }) => text)
    .map(({ relation, text }) => {
      const Icon = iconByName(relation.icon);
      return (
        // Fades in when the graph arrives (it is loaded after the card).
        <div key={relation.key} className="flex items-center gap-1.5 text-muted-foreground flex-1 min-w-0 basis-0 max-w-full overflow-hidden motion-safe:animate-in motion-safe:fade-in motion-safe:duration-300">
          <Icon className="h-3 w-3 shrink-0" />
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="truncate block w-full max-w-full">{text}</span>
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">
                <p>{text}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      );
    });
}
