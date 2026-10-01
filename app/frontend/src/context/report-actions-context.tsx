"use client"

import { useExtensionRegistry, type ReportActionsSlotProps } from "./extension-registry-context"

export type { ReportActionsSlotProps } from "./extension-registry-context"

export function ReportActionsSlot(props: ReportActionsSlotProps) {
  const { reportActions } = useExtensionRegistry()
  return (
    <>
      {reportActions.map((Slot, index) => (
        <Slot key={index} {...props} />
      ))}
    </>
  )
}
