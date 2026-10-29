export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

// A page of items from any cursor-paginated list endpoint - see the backend's
// src/utils/pagination.py for what the cursor itself encodes.
export interface Page<T> {
  items: T[];
  nextCursor: string | null;
}

// ---------------------------------------------------------------------------
// Report DTOs
// ---------------------------------------------------------------------------
// Named the same way as the backend (src/utils/dto.py): each type's name says what
// it adds over its parent, not how "detailed" or "list-like" it is. ReportBaseDto is
// the bare identity every report type shares, ReportDto is the full bibliographic
// record built on it. The backend also has a standalone ReportSources (Report +
// DOI/fulltext links, returned by GET /reports/{id}) that ReportCurationDto and
// ReportIntakeDto both build on - but nothing here calls that endpoint directly
// anymore (the pdf-upload view reads DOI/links off ReportIntakeDto instead, straight
// from the list it already loaded), so there's no ReportSourcesDto on this side: its
// two fields are just declared directly on ReportIntakeDto below instead of via an
// intermediate type with no other consumer.

// Bare-bones report identity (id + title) for list views that don't need the full
// bibliographic record - GET /studies/{study_id}/reports's Page<ReportBaseDto> below,
// which pages through a study's reports instead of returning them all at once.
export interface ReportPreviewDto {
  reportId: number;
  title: string;
}

export interface ReportDto {
  reportId: number;
  title: string;
  year: number;
  authors: string[];
  abstract: string | null;
  trialId: string | null;
  createdAt: string | undefined;
  updatedAt: string | undefined;
}

// A report plus its state within a project's curation workflow (Page<ReportCurationDto>.
// items below): whether it has a PDF, this user's flag on it, and its linked studies.
// flag/assignedStudies are optional (rather than required-but-possibly-empty)
// because ReportIntakeDto below deliberately doesn't carry them - an intake report
// hasn't been curated yet, so there's nothing to fetch there - and still needs to
// satisfy this shape wherever it's passed into the shared list UI (ReportList,
// useReportStore).
export interface ReportCurationDto extends ReportDto {
  hasPdf: boolean | undefined;
  flag?: string;
  assignedStudies?: StudyPreviewDto[];
  // The unconfirmed .ris-upload/fulltext guess (report_added.trial_registration_id) -
  // distinct from trialId above, which only ever holds a reviewer-confirmed value.
  // Optional for the same reason flag/assignedStudies are: ReportIntakeDto doesn't carry
  // it either, but still needs to satisfy this shape (see this interface's comment).
  preliminaryTrialId?: string | null;
  // Optional data a downstream deployable attached on request (see `include` in
  // GetProjectReportsParams), keyed by extension. Empty unless requested.
  extensions?: Record<string, unknown>;
}

// The admin intake list's row shape (Page<ReportIntakeDto>.items below) - a report plus
// its DOI/cached OpenAlex fulltext links (so the pdf-upload view can read them
// straight from this list instead of a separate per-report fetch) and hasPdf.
// Deliberately NOT a ReportCurationDto: an intake report hasn't been curated yet, so
// flag/assignedStudies don't apply here (see ReportCurationDto's comment above for why
// it's still accepted anywhere a ReportCurationDto is expected).
export interface ReportIntakeDto extends ReportDto {
  doi: string | null;
  fulltextLinks: string[];
  hasPdf: boolean | undefined;
}

export type ReportChatDto = JsonValue;

// `any` (the default/absent) means "don't filter on this dimension". `only` keeps just the
// reports matching this dimension (e.g. processed: "only" -> only processed reports); `exclude`
// keeps everything else (processed: "exclude" -> only unprocessed reports). Different fields
// combine as an AND, so e.g. { newStudy: "only", flagged: "exclude" } can be requested together.
// Readiness (still-processing reports) isn't one of these - it's decided by which endpoint you
// call (getProjectReports vs getProjectReportsIntake), not a filter field, since normal users
// must never be able to request unready reports at all.
export type FilterMode = "any" | "only" | "exclude";

export interface ReportFiltersState {
  processed?: FilterMode;
  withPdf?: FilterMode;
  flagged?: FilterMode;
  newStudy?: FilterMode;
  consensus?: FilterMode;
  reviewed?: FilterMode;
}

// One filter dimension in the report list's filter bar, rendered as a single dropdown button
// (labelled `label` while its mode is "any", or the matching option label once set) offering
// all 3 FilterMode states - Any / onlyLabel / excludeLabel - independently of every other
// dimension's own dropdown.
export interface ReportFilterDimension {
  field: keyof ReportFiltersState;
  label: string;
  onlyLabel: string;
  excludeLabel: string;
}

export interface GetProjectReportsParams extends ReportFiltersState {
  search?: string;
  cursor?: string;
  limit?: number;
  // Keys of optional extension data to attach to each report (ReportCurationDto.extensions).
  include?: string[];
}

// ---------------------------------------------------------------------------
// Study DTOs
// ---------------------------------------------------------------------------

// The fields needed to create a study - everything else (studyId, timestamps) is
// server-generated, so this also doubles as the addStudy request payload.
export interface StudyBaseDto {
  status: string;
  shortName: string;
  countries: string[];
  numberParticipants: string | null;
  // Overall duration, e.g. "12 weeks". Null: the study schema calculates it from the arms (`derive` of the field).
  duration: string | null;
  trialId: string | null;
  // The arms of the study and their comparisons as JSON (the graph of the study schema; tags by name or id).
  graph?: string | null;
}

export interface StudyDto extends Omit<StudyBaseDto, "graph"> {
  studyId: number;
  createdAt: string | undefined;
  updatedAt: string | undefined;
}

// A StudyDto plus everything the study details view needs, returned in one call by
// GET /studies/{study_id}: linked reports and the tags of each category of the study
// schema (interventions, conditions, countries, ...), keyed by category. Each nested
// list is only its first page (the endpoint's `limit` param, default 10) - page further
// through any one of them via its own /studies/{study_id}/* endpoint and the returned
// nextCursor.
export interface StudyFullDto extends StudyDto {
  reports: Page<ReportPreviewDto>;
  tags: Record<string, Page<TagDto>>;
  // The graph of the study schema, with its tags named.
  graph: StudyGraphDto;
}

// GET /study-schema: what a study consists of and how it is presented (config/medidex-study.yaml
// of the backend). Colors and icons are names; see lib/colors.ts and lib/icons.ts.
export type StudyColor =
  | "blue"
  | "emerald"
  | "rose"
  | "amber"
  | "slate"
  | "sky"
  | "violet"
  | "teal";

// A primitive value of a study; `key` is the name of the field of StudyDto.
export interface StudyFieldSchemaDto {
  key: keyof StudyDto & string;
  label: string;
  type: "integer" | "duration" | "enum" | "text";
  icon: string;
  color: StudyColor;
  display: "metric" | "text" | "none";
  // The allowed values of an enum field (empty for the other types).
  values: string[];
}

// A metadata field of the database record of a study (when it was entered/edited).
export interface StudyMetaSchemaDto {
  key: keyof StudyDto & string;
  label: string;
  type: "date";
}

export interface TagCategorySchemaDto {
  key: string;
  label: string;
  icon: string;
  color: StudyColor;
  searchField: string;
  /** Whether the plain free-text search also looks in the tags of the category. */
  freeTextSearch: boolean;
  description: string;
}

// What an entity that is a value holds: a tag of a category, or a primitive.
export interface GraphValueSchemaDto {
  category: string | null;
  type: "integer" | "duration" | "enum" | "text" | null;
  // The allowed values of an enum (empty for the other types).
  values: string[];
}

// A kind of entity of the graph of a study (the classes of the study ontology, config/medidex-study.yaml): an arm (an intervention as it is
// delivered), a population, or a value such as a dosage. An entity has no properties, only relations.
export interface GraphEntitySchemaDto {
  key: string;
  label: string;
  icon: string;
  color: StudyColor;
  // The study itself ("study" is its id in the graph).
  root: boolean;
  // Set for an entity that is a value (a dosage, an intervention).
  value: GraphValueSchemaDto | null;
}

// A kind of relation between two entities (`graph.relations`), e.g. the comparison of two arms, or the dosage of an arm.
export interface GraphRelationSchemaDto {
  key: string;
  label: string;
  icon: string;
  color: StudyColor;
  // The kinds of entity an edge can start and end at.
  source: string[];
  target: string[];
  symmetric: boolean;
  many: boolean;
  required: boolean;
  // An attribute is part of its source when that is shown as a line.
  line: boolean;
  // Between source and target when shown as a line ("Drug A vs Placebo").
  separator: string;
  // Also a line on the study cards.
  card: boolean;
  // Leads to values: it describes its source (the dosage of an arm) instead of connecting two entities.
  attribute: boolean;
  // The relation it specialises (a primary outcome is an outcome), if any.
  parent: string | null;
}

export interface GraphSchemaDto {
  entities: GraphEntitySchemaDto[];
  relations: GraphRelationSchemaDto[];
}

export interface StudySchemaDto {
  fields: StudyFieldSchemaDto[];
  meta: StudyMetaSchemaDto[];
  tags: TagCategorySchemaDto[];
  graph: GraphSchemaDto;
}

// A node of the graph of one study: an entity of a kind. A node that is a value holds it (the name of a tag, or text).
export interface StudyGraphNodeDto {
  id: string;
  kind: string;
  value: string | null;
  tagId: string | null;
}

export interface StudyGraphEdgeDto {
  relation: string;
  source: string;
  target: string;
}

// The graph of one study. An older study holds a plain text instead.
export interface StudyGraphDto {
  nodes: StudyGraphNodeDto[];
  edges: StudyGraphEdgeDto[];
  text: string | null;
}

// Bare-bones Study identity for ReportCurationDto.assignedStudies - the UI only ever
// reads studyId/shortName/createdAt off an assigned study (the badge label,
// click-to-open, and the "linked after this report was entered" highlight), never the
// full bibliographic record.
export interface StudyPreviewDto {
  studyId: number;
  shortName: string;
  createdAt: string | undefined;
}

export interface GetStudySearchParams {
  q: string;
  limit?: number;
  cursor?: string;
  // The ids of the study databases to search in; all of them if left out.
  databases?: number[];
}

// A study suggested as a possible match for a report by the similarity search
// (getSimilarStudiesByReportId) - a StudyDto plus how relevant this particular
// suggestion is, for the researcher to accept or reject.
export interface StudyCandidateDto extends StudyDto {
  relevance: number;
}

export interface GetSimilarStudiesParams {
  aspect?: string;
  // Search studies (same syntax as GetStudySearchParams) instead of recommending them;
  // the matches then carry their relevance for the report.
  q?: string;
  cutoff?: string;
  limit?: number;
  cursor?: string;
}

export interface TagCandidateDto extends TagDto {
  relevance: number;
}

export interface GetSimilarTagsParams {
  sources?: string[];
  aspect?: string;
  k?: number;
}

// ---------------------------------------------------------------------------
// Project DTOs
// ---------------------------------------------------------------------------

export interface ProjectDto{
  projectId: string;
  name: string;
  createdAt: string;
  owner: string;
  // The study database its reports are matched against and added to.
  databaseId: number;
  numberReportsReadyForProcessing: number;
  numberReportsTotal: number;
  numberReportsPreProcessed: number;
  numberReportsWithPdf: number;
  numberReportsAutoSearchedPdf: number,
  numberReportsReadyForReview: number;
  numberReportsConfirmed: number;
  numberReportsPostprocessing: number;
  numberReportsPostprocessed: number;
  assignees : AssigneeDto[]
}

export interface AssigneeDto {
  userId : string;
  numberReportsLinked: number;
}

export interface TaskDto {
  projectId: string;
  name: string;
  createdAt: string;
  owner: string;
  databaseId: number;
  numberReportsTotal: number;
  numberReportsReadyForProcessing: number;
  numberReportsProcessed: number;
}

// ---------------------------------------------------------------------------
// Study databases
// ---------------------------------------------------------------------------

export interface DatabasePayload {
  name: string;
  description?: string | null;
  // Which studies belong in the database, e.g. the inclusion criteria of the register.
  eligibilityCriteria: string;
}

// The fields given are changed; an empty description removes it.
export type DatabaseUpdate = Partial<DatabasePayload>;

export interface DatabaseDto {
  databaseId: number;
  name: string;
  description?: string | null;
  eligibilityCriteria: string;
  createdAt: string;
  // Not all its reports are in the vectorstore yet (e.g. right after an import): its studies are found by the search
  // but not yet suggested for new reports, and no projects can be uploaded into it.
  indexing: boolean;
  numberReportsIndexed: number;
  numberStudies: number;
  numberReports: number;
}

// ---------------------------------------------------------------------------
// Aspect DTOs (tags / persons)
// ---------------------------------------------------------------------------

export interface TagDto {
  id: string;
  keyword: string;
}

export type GetPersonsResponseDto = Record<string, string[]>;

// ---------------------------------------------------------------------------
// Annotation DTOs
// ---------------------------------------------------------------------------

export interface AnnotationDto {
  user: string;
  studyId: number;
  studyShortName: string;
  confirmed: boolean,
}

export interface AnnotationFlagDto {
  user: string;
  flag: string;
  public: boolean;
}

export interface ReportAnnotationsDto {
  studies: AnnotationDto[];
  flags: AnnotationFlagDto[];
}

export type ProjectAnnotationsDto = Record<string, ReportAnnotationsDto>;

// One of the allowed values of the `status` field of the study schema.
export type StudyStatus = string;

export type DurationUnit = "hours" | "days" | "weeks" | "months" | "years";

// An arm as suggested for a new study: its interventions (names), and its dosage and duration if the report has them.
export interface ArmSuggestion {
  interventions: string[];
  participants?: number;
  dosage?: string;
  frequency?: string;
  route?: string;
  duration?: { value: number; unit: DurationUnit };
}

// Two arms that are compared.
export interface ComparisonSuggestion {
  a: ArmSuggestion;
  b: ArmSuggestion;
}

export interface NewStudySuggestion {
  short_name: string;
  status_of_study: StudyStatus;
  countries: string[];
  number_of_participants: number;
  duration?: { value: number; unit: DurationUnit };
  comparisons: ComparisonSuggestion[];
}

export type StreamEventType = "node" | "complete" | "error" | "unknown";

// Generic shape for any backend SSE stream (currently only
// GET /projects/{id}/stream's batch-progress feed). `node`/`details` are
// deliberately untyped beyond this - a downstream build consuming a
// different stream can narrow them
// to its own node/detail shapes without this type needing to know about it.
export interface StreamEvent {
  event: StreamEventType;
  node?: string;
  message?: string;
  details?: Record<string, unknown>;
  timestamp: number;
}

export interface StreamCallbacks {
  onEvent: (event: StreamEvent) => void;
  onComplete?: () => void;
  onError: (error: Error) => void;
}
