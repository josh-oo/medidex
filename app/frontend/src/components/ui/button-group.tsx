import * as React from "react"

import { cn } from "@/lib/utils"

/**
 * Related actions joined into one control: the buttons inside (ghost ones, or one `default` for the main action)
 * share a frame and are divided by thin lines, e.g. "Open PDF | Download".
 */
function ButtonGroup({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      role="group"
      data-slot="button-group"
      className={cn(
        "inline-flex shrink-0 items-stretch overflow-hidden rounded-full border bg-card shadow-xs",
        "divide-x divide-border",
        // The buttons lose their own rounding and frame; the group has them.
        "[&>*]:rounded-none [&>*]:shadow-none [&>*]:border-0",
        "[&>*:focus-visible]:relative [&>*:focus-visible]:z-10",
        className
      )}
      {...props}
    />
  )
}

export { ButtonGroup }
