import { createContext, useContext, useMemo, useState, type ReactNode } from "react"

interface ReportNavigation {
  /** The reports of the sidebar in their order, under its current search and filters. */
  reportIds: number[]
  /** More reports follow the loaded ones. */
  hasMore: boolean
  /** Loads the next page of the sidebar list. */
  loadMore: () => void
}

type ReportNavigationContextType = ReportNavigation & {
  setNavigation: (navigation: ReportNavigation) => void
}

const noop = () => {}

const ReportNavigationContext = createContext<ReportNavigationContextType | null>(null)

/** Shares the report list's order with the workbench, so it can page through the same reports. */
export function ReportNavigationProvider({ children }: { children: ReactNode }) {
  const [navigation, setNavigation] = useState<ReportNavigation>({ reportIds: [], hasMore: false, loadMore: noop })
  const value = useMemo(() => ({ ...navigation, setNavigation }), [navigation])

  return <ReportNavigationContext.Provider value={value}>{children}</ReportNavigationContext.Provider>
}

export function useReportNavigation() {
  const ctx = useContext(ReportNavigationContext)
  if (!ctx) throw new Error("Must be used inside ReportNavigationProvider")
  return ctx
}
