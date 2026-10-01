import { cn } from "@/lib/utils"

function Spinner({ className, style, ...props }: React.ComponentProps<"span">) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={cn(
        "inline-block h-4 w-4 animate-spin rounded-full align-middle text-current",
        className,
      )}
      style={{
        background: "conic-gradient(from 0deg, transparent, currentColor)",
        WebkitMask: "radial-gradient(farthest-side, transparent calc(100% - 2px), #000 calc(100% - 2px))",
        mask: "radial-gradient(farthest-side, transparent calc(100% - 2px), #000 calc(100% - 2px))",
        ...style,
      }}
      {...props}
    />
  )
}

export { Spinner }
