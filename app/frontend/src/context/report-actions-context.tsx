"use client"

import { createContext, useContext, type ComponentType } from "react"
import type { StudyCandidateDto } from "@/types/apiDTOs"

export interface ReportActionsSlotProps {
  reportId: number
  studies: StudyCandidateDto[]
}

// Extension point: lets a downstream build (e.g. an enterprise edition)
// render extra report-level actions (a floating action button, etc.) on the
// report detail page without this app knowing what they are. Mirrors
// App's extraRoutes prop (router.tsx) but for a slot deep inside an
// existing page rather than a whole new route - this app never calls
// ReportActionsSlotProvider itself, so by default ReportActionsSlot
// renders nothing.
const ReportActionsSlotContext = createContext<ComponentType<ReportActionsSlotProps> | null>(null)

export const ReportActionsSlotProvider = ReportActionsSlotContext.Provider

export function ReportActionsSlot(props: ReportActionsSlotProps) {
  const Slot = useContext(ReportActionsSlotContext)
  if (!Slot) return null
  return <Slot {...props} />
}
