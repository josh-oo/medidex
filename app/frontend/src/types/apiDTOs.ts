export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

// ---------------------------------------------------------------------------
// Report DTOs
// ---------------------------------------------------------------------------
// Named the same way as the backend (src/utils/dto.py): each type's name says what
// it adds over ReportDto, not how "detailed" or "list-like" it is. ReportDto is the
// shared bibliographic base. The backend also has a standalone ReportSources
// (Report + DOI/fulltext links, returned by GET /reports/{id}) that ProjectReport and
// IntakeReport both build on - but nothing here calls that endpoint directly anymore
// (the pdf-upload view reads DOI/links off IntakeReportDto instead, straight from the
// list it already loaded), so there's no ReportSourcesDto on this side: its two fields
// are just declared directly on IntakeReportDto below instead of via an intermediate
// type with no other consumer.

export interface ReportDto {
  reportId: number;
  year: number;
  title: string;
  authors: string[];
  abstract: string | null;
  trialId: string | null;
  createdAt: string | undefined;
  updatedAt: string | undefined;
}

// A report plus its state within a project's curation workflow (ProjectReportPageDto.
// items below): whether it has a PDF, this user's flag on it, and its linked studies.
// flag/assignedStudies are optional (rather than required-but-possibly-empty)
// because IntakeReportDto below deliberately doesn't carry them - an intake report
// hasn't been curated yet, so there's nothing to fetch there - and still needs to
// satisfy this shape wherever it's passed into the shared list UI (ReportList,
// useReportStore).
export interface ProjectReportDto extends ReportDto {
  hasPdf: boolean | undefined;
  flag?: string;
  assignedStudies?: StudyDto[];
}

export interface ProjectReportPageDto {
  items: ProjectReportDto[];
  nextCursor: string | null;
}

// The admin intake list's row shape (IntakeReportPageDto.items below) - a report plus
// its DOI/cached OpenAlex fulltext links (so the pdf-upload view can read them
// straight from this list instead of a separate per-report fetch) and hasPdf.
// Deliberately NOT a ProjectReportDto: an intake report hasn't been curated yet, so
// flag/assignedStudies don't apply here (see ProjectReportDto's comment above for why
// it's still accepted anywhere a ProjectReportDto is expected).
export interface IntakeReportDto extends ReportDto {
  doi: string | null;
  fulltextLinks: string[];
  hasPdf: boolean | undefined;
}

export interface IntakeReportPageDto {
  items: IntakeReportDto[];
  nextCursor: string | null;
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
}

// ---------------------------------------------------------------------------
// Study DTOs
// ---------------------------------------------------------------------------

export interface StudyDto {
  studyId: number;
  status: string;
  shortName: string;
  countries: string[];
  numberParticipants: string | null;
  duration: string | null;
  comparison: string | null
  trialId: string | null;
  createdAt: string | undefined;
  updatedAt: string | undefined;
}

export type StudyCreateDto = Omit<StudyDto, "studyId" | "createdAt" | "updatedAt">;

// A page of the free-text study search (searchStudies).
export interface StudyPageDto {
  items: StudyDto[];
  nextCursor: string | null;
}

export interface GetStudySearchParams {
  q: string;
  limit?: number;
  cursor?: string;
}

// A study suggested as a possible match for a report by the similarity search
// (getSimilarStudiesByReportId) - a StudyDto plus how relevant this particular
// suggestion is, for the researcher to accept or reject.
export interface CandidateStudyDto extends StudyDto {
  relevance: number;
}

export interface CandidateStudyPageDto {
  items: CandidateStudyDto[];
  nextCursor: string | null;
}

export interface GetSimilarStudiesParams {
  aspect?: string;
  cutoff?: string;
  limit?: number;
  cursor?: string;
  return_details?: boolean;
}

export interface SimilarTagDto {
  id: string;
  name: string;
  score: number;
}

export interface GetSimilarTagsParams {
  sources?: string[];
  aspect?: string;
  k?: number;
}

// ---------------------------------------------------------------------------
// Project DTOs
// ---------------------------------------------------------------------------

export interface ProjectDto {
  projectId: string;
  name: string;
  createdAt: string;
  owner: string;
  numberReportsReadyForProcessing: number;
}

export interface ProjectDetailsDto extends ProjectDto{
  numberReportsTotal: number;
  numberReportsPreProcessed: number;
  numberReportsWithPdf: number;
  numberReportsAutoSearchedPdf: number,
  numberReportsReadyForReview: number;
  numberReportsConfirmed: number;
  assignees : ProjectAssigneeDto[]
}

export interface ProjectAssigneeDto {
  userId : string;
  numberReportsLinked: number;
}

export interface ProjectTaskDto {
  project : ProjectDto;
  numberReportsProcessed: number;
}

// ---------------------------------------------------------------------------
// Aspect DTOs (interventions / conditions / outcomes / persons)
// ---------------------------------------------------------------------------

export interface InterventionDto {
  ID: number;
  Description: string;
}

export interface ConditionDto {
  ID: number;
  Description: string;
}

export interface OutcomeDto {
  ID: number;
  Description: string;
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

// ---------------------------------------------------------------------------
// GenAI evaluation backend DTOs
// ---------------------------------------------------------------------------

export interface EvaluateRequest {
  report: ReportDto;
  studies: StudyDto[];
  model?: "gpt-5.2" | "gpt-5" | "gpt-5-mini" | "gpt-4.1" | null;
  include_pdf?: boolean | null;
  prompt_overrides?: PromptOverrides | null;
}

export interface PromptOverrides {
  background_prompt?: string | null;
  initial_eval_prompt?: string | null;
  likely_group_prompt?: string | null;
  likely_compare_prompt?: string | null;
  likely_review_prompt?: string | null;
  unsure_review_prompt?: string | null;
  summary_prompt?: string | null;
  pdf_prompt?: string | null;
}

export interface DefaultPrompts {
  background_prompt: string;
  initial_eval_prompt: string;
  likely_group_prompt: string;
  likely_compare_prompt: string;
  likely_review_prompt: string;
  unsure_review_prompt: string;
  summary_prompt: string;
  pdf_prompt: string;
}

export interface StudyDecision {
  study_id: string;
  decision: "match" | "not_match" | "unsure" | "likely_match";
  reason: string;
}

export interface VeryLikelyDecision {
  study_id: string;
  prior_reason: string | null;
  group_reason: string | null;
}

export interface EvaluateResponse {
  match: StudyDecision | null;
  not_matches: StudyDecision[];
  unsure: StudyDecision[];
  likely_matches: StudyDecision[];
  very_likely: VeryLikelyDecision[];
  evaluation_has_match?: boolean | null;
  evaluation_summary?: string | null;
  evaluation_new_study?: NewStudySuggestion | null;
}

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

export type StreamEventNode =
  | "prepare_report_pdf"
  | "load_next_initial"
  | "classify_initial"
  | "select_very_likely"
  | "compare_very_likely"
  | "prepare_likely_review"
  | "load_next_likely"
  | "classify_likely_review"
  | "prepare_unsure_review"
  | "load_next_unsure"
  | "classify_unsure"
  | "match_not_found_end"
  | "summarize_evaluation"
  | "suggest_new_study";

export type StreamEventType = "node" | "complete" | "error" | "unknown";

export interface StreamEventDetails {
  study_id?: string | number;
  short_name?: string;
  decision?: "match" | "likely_match" | "unsure" | "not_match";
  reason?: string;
  idx?: number;
  very_likely_study_ids?: Array<string | number>;
  very_likely_names?: string[];
  match_study_id?: string;
  count?: number;
  has_match?: boolean;
  summary?: string;
  new_study?: NewStudySuggestion | null;
}

export interface StreamEvent {
  event: StreamEventType;
  node?: StreamEventNode;
  message?: string;
  details?: StreamEventDetails;
  timestamp: number;
}

export interface StreamCallbacks {
  onEvent: (event: StreamEvent) => void;
  onComplete: () => void;
  onError: (error: Error) => void;
}
