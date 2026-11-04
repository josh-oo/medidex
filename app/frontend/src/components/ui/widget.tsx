import type { ComponentType, ReactNode } from "react"

import { AnimatedHeight } from "@/components/ui/animated-height"
import { cn } from "@/lib/utils"

interface WidgetProps {
  title?: ReactNode
  icon?: ComponentType<{ className?: string }>
  /** Shown as a small counter next to the title. */
  count?: ReactNode
  /** Rendered at the right end of the header. */
  actions?: ReactNode
  className?: string
  children?: ReactNode
}

/** A raised block of the report workbench, with an optional header. Its height eases as its content changes. */
export function Widget({ title, icon: Icon, count, actions, className, children }: WidgetProps) {
  const hasHeader = title !== undefined || actions !== undefined

  return (
    <section
      data-slot="widget"
      className={cn("bg-card text-card-foreground rounded-2xl border shadow-xs p-4 sm:p-5 min-w-0", className)}
    >
      <AnimatedHeight>
        {hasHeader && (
          <header className="mb-3 flex min-h-7 items-center gap-2">
            {Icon && <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />}
            {title !== undefined && <h3 className="min-w-0 truncate text-sm font-semibold">{title}</h3>}
            {count !== undefined && (
              <span className="rounded-full bg-muted px-2 text-xs tabular-nums text-muted-foreground">{count}</span>
            )}
            {actions && <div className="ml-auto flex shrink-0 items-center gap-1.5">{actions}</div>}
          </header>
        )}
        {children}
      </AnimatedHeight>
    </section>
  )
}
