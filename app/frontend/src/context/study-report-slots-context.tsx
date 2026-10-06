import type { ComponentType } from "react"
import { useExtensionRegistry } from "./extension-registry-context"

import type {
  ReportActionsSlotProps,
  StudyCardStyleProps,
  ReportBannerSlotProps,
  ReportStatusSlotProps,
  ReportCardSlotProps,
  ReportAbstractSlotProps,
  ProjectUploadOptionsSlotProps,
  ProjectCardSlotProps,
  StudyBadgeSlotProps,
  StudyContextMenuItemProps,
} from "./extension-registry-context"
import { Abstract } from "@/components/ui/report-view/report-abstract"

export type {
  ReportActionsSlotProps,
  ReportBannerSlotProps,
  ReportStatusSlotProps,
  ReportCardSlotProps,
  ReportAbstractSlotProps,
  ProjectUploadOptionsSlotProps,
  ProjectCardSlotProps,
  StudyBadgeSlotProps,
  StudyContextMenuItemProps,
} from "./extension-registry-context"

const renderSlots = <P extends object>(slots: ComponentType<P>[], props: P) => (
  <>{slots.map((Slot, index) => <Slot key={index} {...props} />)}</>
)

export function useStudyCardClassName(props: StudyCardStyleProps) {
  const { studyCardClassNames } = useExtensionRegistry()
  return studyCardClassNames
    .map((resolve) => resolve(props))
    .filter(Boolean)
    .join(" ")
}

export function StudyBadgeSlot(props: StudyBadgeSlotProps) {
  const { studyBadges } = useExtensionRegistry()
  return renderSlots(studyBadges, props)
}

export function StudyContextMenuSlot(props: StudyContextMenuItemProps) {
  const { studyContextMenuItems } = useExtensionRegistry()
  return renderSlots(studyContextMenuItems, props)
}

export function ReportBannerSlot(props: ReportBannerSlotProps) {
  const { reportBanners } = useExtensionRegistry()
  return renderSlots(reportBanners, props)
}

export function ReportStatusSlot(props: ReportStatusSlotProps) {
  const { reportStatuses } = useExtensionRegistry()
  return renderSlots(reportStatuses, props)
}

export function ReportActionsSlot(props: ReportActionsSlotProps) {
  const { reportActions } = useExtensionRegistry()
  return renderSlots(reportActions, props)
}


export function ReportCardExtrasSlot(props: ReportCardSlotProps) {
  const { reportCardExtras } = useExtensionRegistry()
  return renderSlots(reportCardExtras, props)
}

export function ProjectUploadOptionsSlot(props: ProjectUploadOptionsSlotProps) {
  const { projectUploadOptions } = useExtensionRegistry()
  return renderSlots(projectUploadOptions, props)
}

export function ReportAbstractSlot(props: ReportAbstractSlotProps) {
  const { reportAbstract: Renderer } = useExtensionRegistry()
  return Renderer ? <Renderer {...props} /> : <Abstract text={props.text} />
}

export function ProjectCardProgressSlot(props: ProjectCardSlotProps) {
  const { projectCardProgress } = useExtensionRegistry()
  return renderSlots(projectCardProgress, props)
}
