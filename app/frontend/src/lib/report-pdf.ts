// A report's PDF, fetched with the session's auth: opened in a tab of its own, or downloaded.
import { toast } from "sonner";
import { getReportPdf } from "@/lib/api/reportApi";

export const downloadReportPdf = async (reportId: number, reportTitle: string) => {
  try {
    // 1. Create a strictly Latin title to match the server request
    const safeTitle = reportTitle
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "") // Remove accents
      .replace(/[‐-―]/g, "-") // Normalize dashes (Fixes your index 88 crash)
      .replace(/[\\/:*?"<>|]+/g, "-")   // Remove illegal filename characters
      .replace(/[^ -~]/g, "")           // Strip any remaining non-Latin/Unicode characters
      .trim();

    // 2. Fetch the PDF with auth attached
    const buffer = await getReportPdf(reportId);
    const blob = new Blob([buffer], { type: "application/pdf" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;

    // 3. Trigger the safe download
    link.download = `${reportId} - ${safeTitle || "report"}.pdf`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  } catch (error) {
    console.error("Error downloading report PDF:", error);
    toast.error("Could not download PDF. Please try again.");
  }
};

export const openReportPdf = async (reportId: number) => {
  // Open the tab synchronously (still tied to the user gesture) so
  // browsers don't treat the later navigation as a blocked popup.
  // Note: "noopener" makes window.open() return null, which would
  // leave us with no reference to navigate once the PDF is fetched.
  const newTab = window.open("", "_blank");
  try {
    const buffer = await getReportPdf(reportId);
    const blob = new Blob([buffer], { type: "application/pdf" });
    const url = URL.createObjectURL(blob);
    if (newTab) {
      // Navigating a popup's top-level location to a blob: URL renders
      // blank in some browsers (Safari in particular); embedding it in
      // the popup's own document works reliably everywhere instead.
      newTab.document.title = `Report ${reportId}`;
      const style = newTab.document.createElement("style");
      style.textContent = "html,body,embed{margin:0;height:100%;width:100%}";
      newTab.document.head.appendChild(style);
      const embed = newTab.document.createElement("embed");
      embed.src = url;
      embed.type = "application/pdf";
      newTab.document.body.appendChild(embed);
      newTab.focus();
    }
  } catch (error) {
    console.error("Error opening report PDF:", error);
    toast.error("Could not open PDF. Please try again.");
    newTab?.close();
  }
};
