import { createContext, useContext, useEffect } from "react"

// Tells the report workbench that its report could not be loaded; null outside the workbench (see ReportSplitView).
const WorkbenchUnavailableContext = createContext<((unavailable: boolean) => void) | null>(null)

export const WorkbenchUnavailableProvider = WorkbenchUnavailableContext.Provider

/**
 * For the panel next to the report: while `unavailable`, the workbench shows neither the report nor anything around it,
 * only the panel (which says why).
 */
export function useWorkbenchUnavailable(unavailable: boolean) {
  const setUnavailable = useContext(WorkbenchUnavailableContext)
  useEffect(() => {
    if (!setUnavailable) return
    setUnavailable(unavailable)
    return () => setUnavailable(false)
  }, [setUnavailable, unavailable])
}
