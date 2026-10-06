import {
  createContext,
  useContext,
  type ComponentType,
  type ReactNode,
} from "react"
import type { ProjectDto, StudyCandidateDto, StudyDto } from "@/types/apiDTOs"
import type { AddStudyDialogProps } from "@/components/ui/study-view/add-study-dialog"

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
  "currentReportId" | "onSaveStudy"
> & {
  /** The current report's `extensions` payload (see ReportCardSlotProps). */
  extensions?: Record<string, unknown>
}

export interface ReportCardSlotProps {
  reportId: number
  /** The report's `extensions` payload, for the keys listed in the registry's `reportIncludes`. */
  extensions?: Record<string, unknown>
}

export interface ReportAbstractSlotProps {
  reportId: number
  extensions?: Record<string, unknown>
  title: string | null
  text: string | null
}

export interface ProjectCardSlotProps {
  project: ProjectDto
}

/**
 * Rendered in the "Create Project" dialog. `options` is the free-form object sent
 * with the upload as `options` (JSON); each slot owns its own keys.
 */
export interface ProjectUploadOptionsSlotProps {
  options: Record<string, unknown>
  onChange: (options: Record<string, unknown>) => void
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
  /** Rendered below the processing progress bars of every project card (as progress sections). */
  projectCardProgress: ComponentType<ProjectCardSlotProps>[]
  /** Replaces the rendering of a report's abstract in the expanded report card. */
  reportAbstract?: ComponentType<ReportAbstractSlotProps>
  addStudyTrigger?: ComponentType<AddStudyTriggerSlotProps>
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
  projectCardProgress: [],
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