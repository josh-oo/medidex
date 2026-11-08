import {
  createContext,
  useContext,
  type ComponentType,
  type ReactNode,
} from "react"
import type { ProjectDto, StudyCandidateDto, StudyDto } from "@/types/apiDTOs"
import type { AddStudyDialogProps } from "@/components/ui/study-view/add-study-dialog"
import type { CurationStep } from "@/lib/curation-steps"

export interface ReportActionsSlotProps {
  reportId: number
  studies: StudyCandidateDto[]
}

export interface UserMenuItemProps {
  user: {
    name: string
    email: string
    avatar: string
  }
}

export interface AssigneeOption {
  id: string
  name: string
  icon?: ComponentType<{ className?: string }>
}

export interface AssigneeOptionsGroup {
  heading: string
  options: AssigneeOption[]
  onToggle: (optionId: string, isSelected: boolean) => Promise<void> | void
}

export type AssigneeOptionsResolver = (
  projectId: string,
) => AssigneeOptionsGroup[]

export interface StudyBadgeSlotProps {
  reportId?: number
  study: StudyDto
}

export interface StudyContextMenuItemProps {
  reportId?: number
  study: StudyDto
}

export interface StudyCardStyleProps {
  reportId?: number
  studyId: number
}

/**
 * Called as a React hook while a study card renders; returns extra class names
 * for the card (or undefined). Resolvers must be stable across renders.
 */
export type StudyCardClassNameResolver = (
  props: StudyCardStyleProps,
) => string | undefined

export interface ReportBannerSlotProps {
  reportId?: number
}

export interface ReportStatusSlotProps {
  reportId: number
}

export type AddStudyTriggerSlotProps = Pick<
  AddStudyDialogProps,
  "currentReportId" | "onSaveStudy" | "inline"
> & {
  /** The current report's `extensions` payload (see ReportCardSlotProps). */
  extensions?: Record<string, unknown>
}

export interface ReportCardSlotProps {
  reportId: number
  /** The report's `extensions` payload, for the keys listed in the registry's `reportIncludes`. */
  extensions?: Record<string, unknown>
}

export interface PdfStatusSlotProps {
  projectId: string
  reportId: number
  hasPdf: boolean
  /** Marked as having no PDF ("Not available"); hasPdf is true for it too. */
  pdfUnavailable: boolean
}

export interface ReportAbstractSlotProps {
  reportId: number
  extensions?: Record<string, unknown>
  title: string | null
  text: string | null
}

export interface ReportPdfViewProps {
  reportId: number
  extensions?: Record<string, unknown>
  title: string | null
}

/** A way to view a report's PDF besides the PDF itself (e.g. its fulltext with the extracted tags marked). */
export interface ReportPdfView {
  label: string
  icon: ComponentType<{ className?: string }>
  open: () => void
}

export interface ReportPdfViews {
  views: ReportPdfView[]
  /** Rendered next to the PDF buttons (e.g. the dialog a view opens). */
  dialog: ReactNode
}

/**
 * An extra step of the curation of a project (e.g. a postprocessing of its reports), or null when
 * the project does not go through it. Extra steps come after the PDFs and before the linkage.
 */
export type ProjectStepResolver = (project: ProjectDto) => CurationStep | null

/**
 * Rendered in the "Create Project" dialog. `options` is the free-form object sent
 * with the upload as `options` (JSON); each slot owns its own keys.
 */
export interface ProjectUploadOptionsSlotProps {
  options: Record<string, unknown>
  onChange: (options: Record<string, unknown>) => void
}

/**
 * Rendered on the review page of a report, below the final selection. `studyIds` are the studies selected for the
 * report; `onMergeBlock` holds the merge back while it is given a reason (shown next to the button), null releases it.
 */
export interface ReviewPanelSlotProps {
  reportId: number
  studyIds: number[]
  onMergeBlock: (reason: string | null) => void
}

export interface StudyLinkReview {
  /** Called before a report is linked to an existing study; resolves false to cancel the link. */
  confirmLink: (reportId: number, study: StudyDto) => Promise<boolean>
  /** Rendered next to the study list (e.g. the dialog `confirmLink` opens). */
  dialog: ReactNode
}

export interface ExtensionRegistry {
  userMenuItems: ComponentType<UserMenuItemProps>[]
  reportActions: ComponentType<ReportActionsSlotProps>[]
  assigneeOptions: AssigneeOptionsResolver[]
  studyBadges: ComponentType<StudyBadgeSlotProps>[]
  studyCardClassNames: StudyCardClassNameResolver[]
  /** Rendered inside the right-click menu of a study card (as ContextMenuItem elements). */
  studyContextMenuItems: ComponentType<StudyContextMenuItemProps>[]
  reportBanners: ComponentType<ReportBannerSlotProps>[]
  reportStatuses: ComponentType<ReportStatusSlotProps>[]
  /**
   * Keys of extension data the project report lists should attach to each report
   * (the backend's `include`); delivered to the report slots as `extensions`.
   */
  reportIncludes?: string[]
  /** Rendered at the bottom of every report card in the report list. */
  reportCardExtras: ComponentType<ReportCardSlotProps>[]
  projectUploadOptions: ComponentType<ProjectUploadOptionsSlotProps>[]
  /** Extra steps shown in the progress of every project. */
  projectSteps: ProjectStepResolver[]
  /** Replaces the status dot of a report in the list of the PDF upload (grey: no PDF, green: has one). */
  pdfStatusDot?: ComponentType<PdfStatusSlotProps>
  /** Rendered next to the preview in the PDF card of the PDF upload (e.g. how far the PDF has been processed). */
  pdfStatusPanel?: ComponentType<PdfStatusSlotProps>
  /**
   * Called as a React hook by the report card; its views join the PDF in the card's "View" menu.
   * Must be stable across renders.
   */
  useReportPdfViews?: (props: ReportPdfViewProps) => ReportPdfViews
  /** Replaces the rendering of a report's abstract in the expanded report card. */
  reportAbstract?: ComponentType<ReportAbstractSlotProps>
  addStudyTrigger?: ComponentType<AddStudyTriggerSlotProps>
  /**
   * Called as a React hook by the study list; lets the extension review a link before it is made.
   * Must be stable across renders.
   */
  useStudyLinkReview?: () => StudyLinkReview
  /** Rendered on the review page of a report, below the final selection; each can hold the merge back. */
  reviewPanels: ComponentType<ReviewPanelSlotProps>[]
  routes?: ReactNode
}

const emptyExtensions: ExtensionRegistry = {
  userMenuItems: [],
  reportActions: [],
  assigneeOptions: [],
  studyBadges: [],
  studyCardClassNames: [],
  studyContextMenuItems: [],
  reportBanners: [],
  reportStatuses: [],
  reportCardExtras: [],
  projectUploadOptions: [],
  projectSteps: [],
  reviewPanels: [],
}

const ExtensionRegistryContext = createContext<ExtensionRegistry>(emptyExtensions)

export function ExtensionRegistryProvider({
  extensions,
  children,
}: {
  extensions?: Partial<ExtensionRegistry>
  children: ReactNode
}) {
  const value: ExtensionRegistry = {
    ...emptyExtensions,
    ...extensions,
  }

  return (
    <ExtensionRegistryContext.Provider value={value}>
      {children}
    </ExtensionRegistryContext.Provider>
  )
}

export function useExtensionRegistry() {
  return useContext(ExtensionRegistryContext)
}