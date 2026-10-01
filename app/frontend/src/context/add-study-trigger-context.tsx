"use client"

import { createContext, useContext, type ComponentType } from "react"
import { AddStudyDialog, type AddStudyDialogProps } from "@/components/ui/study-view/add-study-dialog"

export type AddStudyTriggerSlotProps = Pick<
  AddStudyDialogProps,
  "currentReportId" | "onSaveStudy"
>

// Extension point: lets a downstream build replace CandidateStudyTable's
// "Add New Study" trigger for a given report with its own version (e.g. one
// that's prefilled and highlighted from a suggestion it computed elsewhere)
// instead of this app always rendering the same plain AddStudyDialog.
// Unlike the other Slot* contexts (study-report-slots-context.tsx,
// report-actions-context.tsx), the default here isn't "render nothing" - a
// new-study trigger is core functionality this app needs on its own, so with
// no provider set, AddStudyTriggerSlot falls back to rendering the plain
// AddStudyDialog itself.
const AddStudyTriggerSlotContext =
  createContext<ComponentType<AddStudyTriggerSlotProps> | null>(null)

export const AddStudyTriggerSlotProvider = AddStudyTriggerSlotContext.Provider

export function AddStudyTriggerSlot(props: AddStudyTriggerSlotProps) {
  const Override = useContext(AddStudyTriggerSlotContext)
  const Component = Override ?? AddStudyDialog
  return <Component {...props} />
}
