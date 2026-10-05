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

export function useStudyCardClassName(props: StudyCardStyleProps) {
  const { studyCardClassNames } = useExtensionRegistry()
  return studyCardClassNames
    .map((resolve) => resolve(props))
    .filter(Boolean)
    .join(" ")
}

export function StudyBadgeSlot(props: StudyBadgeSlotProps) {
  const { studyBadges } = useExtensionRegistry()
  return <>{studyBadges.map((Slot, index) => <Slot key={index} {...props} />)}</>
}

export function StudyContextMenuSlot(props: StudyContextMenuItemProps) {
  const { studyContextMenuItems } = useExtensionRegistry()
  return <>{studyContextMenuItems.map((Slot, index) => <Slot key={index} {...props} />)}</>
}

export function ReportBannerSlot(props: ReportBannerSlotProps) {
  const { reportBanners } = useExtensionRegistry()
  return <>{reportBanners.map((Slot, index) => <Slot key={index} {...props} />)}</>
}

export function ReportStatusSlot(props: ReportStatusSlotProps) {
  const { reportStatuses } = useExtensionRegistry()
  return <>{reportStatuses.map((Slot, index) => <Slot key={index} {...props} />)}</>
}

export function ReportActionsSlot(props: ReportActionsSlotProps) {
  const { reportActions } = useExtensionRegistry()
  return <>{reportActions.map((Slot, index) => <Slot key={index} {...props} />)}</>
}


export function ReportCardExtrasSlot(props: ReportCardSlotProps) {
  const { reportCardExtras } = useExtensionRegistry()
  return <>{reportCardExtras.map((Slot, index) => <Slot key={index} {...props} />)}</>
}

export function ProjectUploadOptionsSlot(props: ProjectUploadOptionsSlotProps) {
  const { projectUploadOptions } = useExtensionRegistry()
  return <>{projectUploadOptions.map((Slot, index) => <Slot key={index} {...props} />)}</>
}

export function ReportAbstractSlot(props: ReportAbstractSlotProps) {
  const { reportAbstract: Renderer } = useExtensionRegistry()
  return Renderer ? <Renderer {...props} /> : <Abstract text={props.text} />
}

export function ProjectCardProgressSlot(props: ProjectCardSlotProps) {
  const { projectCardProgress } = useExtensionRegistry()
  return <>{projectCardProgress.map((Slot, index) => <Slot key={index} {...props} />)}</>
}
