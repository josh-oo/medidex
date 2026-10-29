import { useLayoutEffect, useRef, type ReactNode } from "react"

const TRANSITION = "height 280ms cubic-bezier(0.2, 0, 0, 1)"

/**
 * Its content, with a change of its height eased rather than jumped (rows that arrive, a section that opens).
 * While the height moves, what sticks out is clipped; otherwise the height is the content's own. A change that comes
 * with a new width (the window resized, the sidebar folded) follows at once, as does every change with reduced motion.
 */
export function AnimatedHeight({ className, children }: { className?: string; children: ReactNode }) {
  const outerRef = useRef<HTMLDivElement>(null)
  const innerRef = useRef<HTMLDivElement>(null)

  useLayoutEffect(() => {
    const outer = outerRef.current
    const inner = innerRef.current
    if (!outer || !inner) return

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)")
    let { width, height } = inner.getBoundingClientRect()

    const settle = () => {
      outer.style.transition = ""
      outer.style.height = ""
      outer.style.overflow = ""
    }
    const onTransitionEnd = (event: TransitionEvent) => {
      if (event.target === outer && event.propertyName === "height") settle()
    }

    // Runs after layout and before paint, so the jump to the new height is never shown.
    const observer = new ResizeObserver(() => {
      const next = inner.getBoundingClientRect()
      const widthChanged = Math.abs(next.width - width) > 0.5
      const from = height
      width = next.width
      height = next.height
      if (widthChanged || reduceMotion.matches) {
        settle()
      } else if (outer.style.height) {
        // Already moving: on from where it is now to the new height.
        outer.style.height = `${next.height}px`
      } else if (Math.abs(next.height - from) >= 1) {
        outer.style.transition = TRANSITION
        outer.style.overflow = "hidden"
        outer.style.height = `${from}px`
        void outer.offsetHeight
        outer.style.height = `${next.height}px`
      }
    })

    observer.observe(inner)
    outer.addEventListener("transitionend", onTransitionEnd)
    return () => {
      observer.disconnect()
      outer.removeEventListener("transitionend", onTransitionEnd)
    }
  }, [])

  return (
    <div ref={outerRef} className={className}>
      {/* A flow root, so the margins of its first and last child count to its height. */}
      <div ref={innerRef} className="flow-root">
        {children}
      </div>
    </div>
  )
}
