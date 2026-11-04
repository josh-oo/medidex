import { ChevronLeft, ChevronRight } from "lucide-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface PagerProps {
  /** First and last position shown, 1-based. */
  range: readonly [number, number]
  canPrev: boolean
  canNext: boolean
  onPrev: () => void
  onNext: () => void
  /** A page is loading; the list shows that itself (see useClientPages' isTurning). */
  loading?: boolean
  className?: string
}

/** "11–20" with previous / next page, for the lists that are paged (see useClientPages). */
export function Pager({ range, canPrev, canNext, onPrev, onNext, loading, className }: PagerProps) {
  if (!canPrev && !canNext) return null

  return (
    <div className={cn("flex items-center gap-0.5 text-xs text-muted-foreground tabular-nums", className)}>
      <span className="px-1 whitespace-nowrap">
        {range[0]}–{range[1]}
      </span>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        className="h-7 w-7 text-muted-foreground"
        aria-label="Previous page"
        disabled={!canPrev || loading}
        onClick={onPrev}
      >
        <ChevronLeft className="h-4 w-4" />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        className="h-7 w-7 text-muted-foreground"
        aria-label="Next page"
        disabled={!canNext || loading}
        onClick={onNext}
      >
        <ChevronRight className="h-4 w-4" />
      </Button>
    </div>
  )
}
