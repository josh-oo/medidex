import { createContext, useContext, type ReactNode } from "react"
import { createPortal } from "react-dom"

// The foot of the report workbench, over both columns; null outside the workbench (see ReportSplitView).
const WorkbenchFooterContext = createContext<HTMLElement | null>(null)

export const WorkbenchFooterProvider = WorkbenchFooterContext.Provider

/**
 * What belongs under the whole workbench rather than in one of its columns (e.g. a bar to ask about the report): over
 * the foot of the workbench, in view while the columns scroll under it; nothing outside the workbench. The footer lets
 * clicks through to the columns, so what it shows takes them with `pointer-events-auto`.
 */
export function WorkbenchFooter({ children }: { children: ReactNode }) {
  const footer = useContext(WorkbenchFooterContext)
  return footer ? createPortal(children, footer) : null
}
