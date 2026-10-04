import {
  createContext,
  useContext,
  type ComponentType,
  type ReactNode,
} from "react"
import type { StudyCandidateDto } from "@/types/apiDTOs"
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
  study: StudyCandidateDto
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
>

export interface ExtensionRegistry {
  userMenuItems: ComponentType<UserMenuItemProps>[]
  reportActions: ComponentType<ReportActionsSlotProps>[]
  assigneeOptions: AssigneeOptionsResolver[]
  studyBadges: ComponentType<StudyBadgeSlotProps>[]
  studyCardClassNames: StudyCardClassNameResolver[]
  reportBanners: ComponentType<ReportBannerSlotProps>[]
  reportStatuses: ComponentType<ReportStatusSlotProps>[]
  addStudyTrigger?: ComponentType<AddStudyTriggerSlotProps>
  routes?: ReactNode
}

const emptyExtensions: ExtensionRegistry = {
  userMenuItems: [],
  reportActions: [],
  assigneeOptions: [],
  studyBadges: [],
  studyCardClassNames: [],
  reportBanners: [],
  reportStatuses: [],
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