import { useExtensionRegistry } from "./extension-registry-context"

import type {
  ReportActionsSlotProps,
  StudyCardStyleProps,
  ReportBannerSlotProps,
  ReportStatusSlotProps,
  StudyBadgeSlotProps,
} from "./extension-registry-context"

export type {
  ReportActionsSlotProps,
  ReportBannerSlotProps,
  ReportStatusSlotProps,
  StudyBadgeSlotProps,
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
