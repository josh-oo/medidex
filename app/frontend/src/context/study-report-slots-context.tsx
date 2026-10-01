"use client"

import { createContext, useContext, type ComponentType } from "react"
import type { StudyCandidateDto } from "@/types/apiDTOs"

// Extension points for a downstream build to attach extra, per-study or
// per-report information to the shared OSS study/report views without this
// app knowing what that information is - currently used by the private
// repo's enterprise-only AI study-matching feature (a badge per study, a
// banner on the report's study panel, a status icon in the report list),
// but deliberately generic so a future, unrelated feature can reuse the same
// three slots instead of adding new ones. Mirrors ReportActionsSlot
// (report-actions-context.tsx) - this app never calls any of the
// *SlotProvider components itself, so by default each slot renders nothing.

export interface StudyBadgeSlotProps {
  reportId?: number
  study: StudyCandidateDto
}

const StudyBadgeSlotContext = createContext<ComponentType<StudyBadgeSlotProps> | null>(null)
export const StudyBadgeSlotProvider = StudyBadgeSlotContext.Provider

export function StudyBadgeSlot(props: StudyBadgeSlotProps) {
  const Slot = useContext(StudyBadgeSlotContext)
  if (!Slot) return null
  return <Slot {...props} />
}

export interface ReportBannerSlotProps {
  reportId?: number
}

const ReportBannerSlotContext = createContext<ComponentType<ReportBannerSlotProps> | null>(null)
export const ReportBannerSlotProvider = ReportBannerSlotContext.Provider

export function ReportBannerSlot(props: ReportBannerSlotProps) {
  const Slot = useContext(ReportBannerSlotContext)
  if (!Slot) return null
  return <Slot {...props} />
}

export interface ReportStatusSlotProps {
  reportId: number
}

const ReportStatusSlotContext = createContext<ComponentType<ReportStatusSlotProps> | null>(null)
export const ReportStatusSlotProvider = ReportStatusSlotContext.Provider

export function ReportStatusSlot(props: ReportStatusSlotProps) {
  const Slot = useContext(ReportStatusSlotContext)
  if (!Slot) return null
  return <Slot {...props} />
}
