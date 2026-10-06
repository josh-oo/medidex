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
  duration: string | null;
  comparison: string | null;
  trialId: string | null;
}

export interface StudyDto extends StudyBaseDto {
  studyId: number;
  createdAt: string | undefined;
  updatedAt: string | undefined;
}

// A StudyDto plus everything the study details view needs, returned in one call by
// GET /studies/{study_id}: linked reports and the tag-like aspects (interventions/
// conditions/outcomes/participants/design). Each nested list is only its first page
// (the endpoint's `limit` param, default 10) - page further through any one of them
// via its own /studies/{study_id}/* endpoint and the returned nextCursor.
export interface StudyFullDto extends StudyDto {
  reports: Page<ReportPreviewDto>;
  interventions: Page<TagDto>;
  conditions: Page<TagDto>;
  outcomes: Page<TagDto>;
  participants: Page<TagDto>;
  design: Page<TagDto>;
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
  numberReportsReadyForProcessing: number;
  numberReportsProcessed: number;
}

// ---------------------------------------------------------------------------
// Aspect DTOs (interventions / conditions / outcomes / persons)
// ---------------------------------------------------------------------------

export interface TagDto {
  id: string;
  keyword: string;
}

// Raw shape of GET /participants and GET /design - unlike interventions/conditions/
// outcomes, these two aren't wrapped into TagDto by the backend (see resources.py).
export interface ParticipantDto {
  id: number;
  description: string;
}

export interface DesignDto {
  id: number;
  description?: string | null;
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

export type StudyStatus = "Closed" | "Stopped early" | "Open/Ongoing" | "Planned";

export type DurationUnit = "hours" | "days" | "weeks" | "months" | "years";

export interface ComparisonGroup {
  intervention: string[];
  control: string[];
}

export interface NewStudySuggestion {
  short_name: string;
  status_of_study: StudyStatus;
  countries: string[];
  duration_value: number;
  duration_unit: DurationUnit;
  number_of_participants: number;
  comparison: ComparisonGroup[];
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
