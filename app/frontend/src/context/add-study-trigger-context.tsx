"use client"

import { AddStudyDialog } from "@/components/ui/study-view/add-study-dialog"
import { useExtensionRegistry, type AddStudyTriggerSlotProps } from "./extension-registry-context"

export type { AddStudyTriggerSlotProps } from "./extension-registry-context"

export function AddStudyTriggerSlot(props: AddStudyTriggerSlotProps) {
  const { addStudyTrigger } = useExtensionRegistry()
  const Component = addStudyTrigger ?? AddStudyDialog
  return <Component {...props} />
}
