"use client"

import { createContext, useContext, type ComponentType } from "react"

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

export type AssigneeOptionsResolver = (projectId: string) => AssigneeOptionsGroup[]

// Extension point: lets a downstream build (e.g. an enterprise edition) add
// extra, non-human entries to a project card's assignee list - their own
// dropdown group and their own assign/unassign behavior - without
// ProjectCard knowing what they are. A resolver (not a plain array) because
// the group's onToggle needs the project id it's acting on, which is only
// known inside ProjectCard. Mirrors ReportActionsSlot
// (report-actions-context.tsx) but merges data into an existing list rather
// than injecting a whole component - this app never calls
// AssigneeOptionsSlotProvider itself, so by default the slot resolves to
// nothing.
const AssigneeOptionsSlotContext = createContext<AssigneeOptionsResolver>(() => [])

export const AssigneeOptionsSlotProvider = AssigneeOptionsSlotContext.Provider

export function useAssigneeOptionsSlot(projectId: string): AssigneeOptionsGroup[] {
  const resolve = useContext(AssigneeOptionsSlotContext)
  return resolve(projectId)
}
