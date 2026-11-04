import { createContext, useContext, type ReactNode } from "react"
import { createPortal } from "react-dom"

// The side column of the report workbench, while it is laid out in two columns; null otherwise.
const WorkbenchAsideContext = createContext<HTMLElement | null>(null)

export const WorkbenchAsideProvider = WorkbenchAsideContext.Provider

/**
 * Widgets that belong next to the report (e.g. searching or adding a study): in the side column
 * under the report while the workbench has two columns, in place otherwise.
 */
export function WorkbenchAside({ children }: { children: ReactNode }) {
  const aside = useContext(WorkbenchAsideContext)
  return aside ? createPortal(children, aside) : <>{children}</>
}
