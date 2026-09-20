import { LoaderCircle } from "lucide-react"

import { cn } from "@/lib/utils"

function Spinner({ className, ...props }: React.ComponentProps<typeof LoaderCircle>) {
  return (
    <LoaderCircle
      role="status"
      aria-label="Loading"
      className={cn("inline-block h-4 w-4 animate-spin align-middle text-current", className)}
      {...props}
    />
  )
}

export { Spinner }
