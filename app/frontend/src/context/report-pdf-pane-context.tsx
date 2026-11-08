import { createContext, useContext } from "react"

/**
 * Where to open a PDF: a page (1-based), and optionally the passage on it to highlight and center - rectangles as
 * fractions of the page's width and height (left, top, width, height).
 */
export interface PdfFocus {
  page: number
  boxes?: [number, number, number, number][]
}

/** A study whose reports' PDFs are shown under the open report's, to compare them. */
export interface ComparedStudy {
  studyId: number
  shortName: string
}

/** The PDF pane of the report workbench: the open report's PDF next to the workbench, in a resizable split. */
export interface ReportPdfPaneState {
  open: boolean
  /** The passage the pane was last opened at, if any; a new object for every opening, even of the same passage. */
  focus: PdfFocus | null
  setOpen: (open: boolean) => void
  /** Opens the pane, at the passage if one is given. */
  show: (focus?: PdfFocus) => void
  /** The study compared with the open report (it belongs to the report and ends when another one opens). */
  compared: ComparedStudy | null
  /** Compares the open report with a study, opening the pane if it is closed; null ends the comparison. */
  compare: (study: ComparedStudy | null) => void
}

/**
 * The width of the docked PDF pane (in px, 0 without one) as a CSS variable of the document, so that a dialog can keep
 * to the workbench next to it (see isInReportPdfPane).
 */
export const REPORT_PDF_PANE_WIDTH = "--report-pdf-pane-width"

/** Whether an event's target is in the PDF pane, e.g. to keep a dialog open while the PDF next to it is read. */
export const isInReportPdfPane = (target: EventTarget | null) =>
  target instanceof Element && target.closest("[data-report-pdf-pane]") !== null

// Null outside the report workbench (see ReportSplitView).
const ReportPdfPaneContext = createContext<ReportPdfPaneState | null>(null)

export const ReportPdfPaneProvider = ReportPdfPaneContext.Provider

export function useReportPdfPane() {
  return useContext(ReportPdfPaneContext)
}
