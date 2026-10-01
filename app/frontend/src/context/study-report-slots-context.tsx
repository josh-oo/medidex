"use client"

import { createContext, useContext, type ComponentType } from "react"
import type { StudyCandidateDto } from "@/types/apiDTOs"

// Extension points for a downstream build to attach extra, per-study or
// per-report information to the shared OSS study/report views without this
// app knowing what that information is.

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
