import { useEffect, useState } from "react";
import { GitCompareArrows } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { ComparedStudy } from "@/context/report-pdf-pane-context";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useReportStore } from "@/hooks/use-report-store";
import { getSimilarStudiesByReportId } from "@/lib/api/reportApi";

const PAGE_SIZE = 10;

interface ReportPdfComparePickerProps {
  reportId: number;
  onPick: (study: ComparedStudy) => void;
}

/**
 * Picks the study to compare the open report with: the studies it is linked to and its most similar ones, or those the
 * search finds for it. Its reports are gone through in tabs under the open report's PDF.
 */
export function ReportPdfComparePicker({ reportId, onPick }: ReportPdfComparePickerProps) {
  const linked = useReportStore((state) => state.reports[reportId]?.assignedStudies);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebouncedValue(query.trim(), 300);
  const [studies, setStudies] = useState<{ linked: ComparedStudy[]; found: ComparedStudy[] } | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  // Without a query the linked studies come first; the search goes through the similar studies, as in the study list.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setStudies(null);
    setFailed(false);
    getSimilarStudiesByReportId(reportId, { q: debouncedQuery || undefined, limit: PAGE_SIZE })
      .then((page) => {
        if (cancelled) return;
        const linkedOptions = debouncedQuery ? [] : (linked ?? []);
        const linkedIds = new Set(linkedOptions.map((option) => option.studyId));
        setStudies({ linked: linkedOptions, found: page.items.filter((item) => !linkedIds.has(item.studyId)) });
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [open, reportId, debouncedQuery, linked]);

  const studyItem = (option: ComparedStudy) => (
    <CommandItem
      key={option.studyId}
      value={String(option.studyId)}
      onSelect={() => {
        onPick({ studyId: option.studyId, shortName: option.shortName });
        setOpen(false);
      }}
    >
      <span className="truncate">{option.shortName}</span>
    </CommandItem>
  );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <Tooltip>
        <TooltipTrigger asChild>
          <PopoverTrigger asChild>
            <Button type="button" variant="ghost" size="sm">
              <GitCompareArrows />
              Compare
            </Button>
          </PopoverTrigger>
        </TooltipTrigger>
        <TooltipContent>Compare with the PDFs of a study</TooltipContent>
      </Tooltip>
      <PopoverContent
        align="end"
        sideOffset={8}
        className="w-[min(340px,calc(100vw-2rem))] overflow-hidden rounded-2xl border bg-popover p-0 text-popover-foreground shadow-lg"
      >
        {/* The search runs on the server; the list shows what it found as it is. */}
        <Command shouldFilter={false}>
          <CommandInput placeholder="Search studies..." value={query} onValueChange={setQuery} />
          <CommandList className="max-h-72 overflow-y-auto">
            {failed ? (
              <p className="px-3 py-6 text-center text-sm text-muted-foreground">The studies could not be loaded.</p>
            ) : studies === null ? (
              <p className="px-3 py-6 text-center text-sm text-muted-foreground">Loading studies…</p>
            ) : (
              <>
                <CommandEmpty>No studies found.</CommandEmpty>
                {studies.linked.length > 0 && <CommandGroup heading="Linked">{studies.linked.map(studyItem)}</CommandGroup>}
                {studies.found.length > 0 && (
                  <CommandGroup heading={debouncedQuery ? "Found" : "Similar"}>{studies.found.map(studyItem)}</CommandGroup>
                )}
              </>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
