import { useEffect, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";

// A load quicker than this shows nothing in between (a placeholder shown for a moment flickers).
const SHOW_AFTER_MS = 300;

/** The one placeholder of a section of the settings while it loads the first time: a card of `rows` lines. */
export function SettingsSkeleton({ rows = 3 }: { rows?: number }) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setShown(true), SHOW_AFTER_MS);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <div aria-busy className={shown ? "space-y-3 rounded-2xl border bg-card p-5 shadow-xs" : "invisible"}>
      {shown &&
        Array.from({ length: rows }, (_, index) => (
          <Skeleton key={index} className={index === 0 ? "h-5 w-1/3" : "h-10 w-full"} />
        ))}
    </div>
  );
}
