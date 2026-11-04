import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { armLetter, areCompared } from "@/lib/comparisonUtils";
import type { ArmComparison, StudyArm } from "@/types/comparisons";

// The comparisons of the add-study form drawn as brackets beside its arm rows: every comparison is a bracket from one
// row to another with a chip ("B vs C") in its middle, on the innermost lane where it overlaps no other bracket (two that
// only meet at an arm share a lane). Each row has a port (+) to start a comparison from, and the port of another arm to
// end it at.

const LANE_GAP = 60; // between the lanes, wider than a chip so the chips of two lanes never overlap
const INNER_LANE = 46; // the innermost lane, in from the ports: far enough that a chip never covers a port
const CHIP_HALF = 30; // half the width of a chip and a little room, so the outermost chip stays inside the gutter
const PORT_GAP = 12; // between the ports and the rows
const MIN_PORT = 80; // the ports never closer to the edge, so the label of a port ("Link to A") fits beside it

type Lane = { comparison: ArmComparison; lane: number; top: number; bottom: number };

// Each comparison on the innermost lane where it overlaps no comparison already placed, the shortest placed first.
function assignLanes(comparisons: ArmComparison[], rowOf: Map<string, number>): Lane[] {
  const spans = comparisons
    .filter((comparison) => rowOf.has(comparison.source) && rowOf.has(comparison.target))
    .map((comparison) => {
      const [a, b] = [rowOf.get(comparison.source)!, rowOf.get(comparison.target)!];
      return { comparison, top: Math.min(a, b), bottom: Math.max(a, b) };
    })
    .sort((x, y) => x.bottom - x.top - (y.bottom - y.top) || x.top - y.top);
  const placed: Lane[] = [];
  for (const span of spans) {
    let lane = 0;
    while (placed.some((other) => other.lane === lane && span.top < other.bottom && other.top < span.bottom)) lane += 1;
    placed.push({ ...span, lane });
  }
  return placed;
}

// The width of the gutter the brackets of the comparisons need, the ports included.
export function lanesWidth(arms: StudyArm[], comparisons: ArmComparison[]): number {
  const lanes = assignLanes(comparisons, new Map(arms.map((arm, index) => [arm.id, index])));
  const count = lanes.length ? Math.max(...lanes.map((lane) => lane.lane)) + 1 : 0;
  return portX(count) + 9 + PORT_GAP;
}

const portX = (lanes: number) => Math.max(MIN_PORT, lanes === 0 ? 0 : CHIP_HALF + INNER_LANE + LANE_GAP * (lanes - 1));

// The vertical centers of the rows (marked `data-arm-row`) of the element, kept up to date as they change size.
export function useRowCenters(container: HTMLElement | null): number[] {
  const [centers, setCenters] = useState<number[]>([]);

  useEffect(() => {
    if (!container) return;
    const measure = () => {
      const rows = Array.from(container.querySelectorAll<HTMLElement>("[data-arm-row]"));
      const next = rows.map((row) => row.offsetTop + row.offsetHeight / 2);
      setCenters((previous) => (previous.length === next.length && previous.every((value, index) => value === next[index]) ? previous : next));
    };
    const observer = new ResizeObserver(measure);
    observer.observe(container);
    measure();
    return () => observer.disconnect();
  }, [container]);

  return centers;
}

interface ArmComparisonLanesProps {
  arms: StudyArm[];
  comparisons: ArmComparison[];
  rowCenters: number[];
  // The arm a new comparison is being drawn from, if any.
  linkingFrom: string | null;
  onPort: (armId: string) => void;
  onRemove: (comparisonId: string) => void;
}

export function ArmComparisonLanes({ arms, comparisons, rowCenters, linkingFrom, onPort, onRemove }: ArmComparisonLanesProps) {
  const [hovered, setHovered] = useState<string | null>(null);
  const rowOf = new Map(arms.map((arm, index) => [arm.id, index]));
  const lanes = assignLanes(comparisons, rowOf);
  const count = lanes.length ? Math.max(...lanes.map((lane) => lane.lane)) + 1 : 0;
  const port = portX(count);
  const letterOf = (armId: string) => armLetter(rowOf.get(armId) ?? 0);
  const active = lanes.find((lane) => lane.comparison.id === hovered);
  const highlighted = new Set(active ? [active.comparison.source, active.comparison.target] : []);

  if (rowCenters.length !== arms.length) return null;

  return (
    <div className="pointer-events-none absolute inset-y-0 left-0" style={{ width: port + 9 + PORT_GAP }} aria-label="Comparisons of the arms">
      {lanes.map(({ comparison, lane, top, bottom }) => {
        const x = port - INNER_LANE - LANE_GAP * lane;
        const state =
          linkingFrom !== null || (hovered !== null && hovered !== comparison.id)
            ? "border-border"
            : hovered === comparison.id
              ? "border-primary"
              : "border-muted-foreground/40";
        return (
          <div
            key={`lane-${comparison.id}`}
            className={`absolute rounded-l-[10px] border-2 border-r-0 transition-colors ${state}`}
            // The bracket of the hovered comparison is drawn over the others where they meet at an arm.
            style={{ left: x, top: rowCenters[top] - 1, width: port - x, height: rowCenters[bottom] - rowCenters[top] + 2, zIndex: hovered === comparison.id ? 2 : 1 }}
          />
        );
      })}
      {lanes.length === 0 && linkingFrom === null && arms.length > 1 && (
        // Without comparisons, a faint example of one between the first two arms shows how they are added.
        <>
          <div
            className="absolute rounded-l-[10px] border-2 border-r-0 border-dashed border-border"
            style={{ left: port - INNER_LANE, top: rowCenters[0] - 1, width: INNER_LANE, height: rowCenters[1] - rowCenters[0] + 2 }}
          />
          <p
            className="absolute -translate-x-1/2 -translate-y-1/2 bg-background py-1 text-center text-[11px] leading-4 whitespace-nowrap text-muted-foreground"
            style={{ left: port - INNER_LANE, top: (rowCenters[0] + rowCenters[1]) / 2 }}
          >
            Link arms
            <br />
            with +
          </p>
        </>
      )}
      {arms.map((arm, index) => {
        const isSource = linkingFrom === arm.id;
        const isTarget = linkingFrom !== null && !isSource && !areCompared(comparisons, linkingFrom, arm.id);
        const isBlocked = linkingFrom !== null && !isSource && !isTarget;
        const look = isSource
          ? "border-primary bg-primary text-primary-foreground"
          : isTarget
            ? "border-primary bg-primary/10 text-primary"
            : highlighted.has(arm.id)
              ? "border-primary bg-background text-primary"
              : "border-muted-foreground/50 bg-background text-muted-foreground hover:border-primary hover:text-primary";
        const letter = armLetter(index);
        const from = linkingFrom === null ? "" : armLetter(rowOf.get(linkingFrom) ?? 0);
        // While a link is drawn, the ports it can end at say so beside them (and take the click as well), the port it
        // started from cancels it.
        const label = isSource ? "Cancel" : isTarget ? `Link to ${from}` : null;
        return (
          <div key={`port-${arm.id}`}>
            {label && (
              <button
                type="button"
                tabIndex={-1}
                onClick={() => onPort(arm.id)}
                className={`pointer-events-auto absolute z-[5] -translate-x-full -translate-y-1/2 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium leading-4 ${
                  isSource ? "border-border bg-background text-muted-foreground" : "border-primary/40 bg-background text-primary"
                }`}
                style={{ left: port - 14, top: rowCenters[index] }}
              >
                {label}
              </button>
            )}
            <button
              type="button"
              disabled={isBlocked}
              onClick={() => onPort(arm.id)}
              title={linkingFrom === null ? "Link to another arm" : undefined}
              aria-label={
                linkingFrom === null
                  ? `Link arm ${letter} to another arm`
                  : isSource
                    ? `Cancel the link from arm ${letter}`
                    : `Link arm ${letter} to arm ${from}`
              }
              className={`pointer-events-auto absolute z-[3] flex h-[18px] w-[18px] -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 text-xs font-bold leading-none transition-colors disabled:opacity-40 ${look}`}
              style={{ left: port, top: rowCenters[index] }}
            >
              +
            </button>
          </div>
        );
      })}
      {linkingFrom === null && lanes.map(({ comparison, lane, top, bottom }) => {
        const x = port - INNER_LANE - LANE_GAP * lane;
        const label = `${letterOf(comparison.source)} vs ${letterOf(comparison.target)}`;
        const isHovered = hovered === comparison.id;
        const look = isHovered
          ? "border-primary bg-primary text-primary-foreground shadow-sm"
          : hovered === null
            ? "border-muted-foreground/50 bg-background text-foreground"
            : "border-border bg-background text-muted-foreground";
        return (
          <div
            key={`chip-${comparison.id}`}
            className={`group pointer-events-auto absolute flex h-6 -translate-x-1/2 -translate-y-1/2 items-center gap-0.5 rounded-full border-[1.5px] pl-2 pr-1 text-[11px] font-semibold whitespace-nowrap transition-colors ${look} ${isHovered ? "z-10" : "z-[4]"}`}
            style={{ left: x, top: (rowCenters[top] + rowCenters[bottom]) / 2 }}
            onMouseEnter={() => setHovered(comparison.id)}
            onMouseLeave={() => setHovered(null)}
            onFocus={() => setHovered(comparison.id)}
            onBlur={() => setHovered(null)}
          >
            <span className="pr-1">{label}</span>
            <button
              type="button"
              onClick={() => {
                setHovered(null);
                onRemove(comparison.id);
              }}
              aria-label={`Remove comparison ${label}`}
              className="flex h-4 w-0 items-center justify-center overflow-hidden rounded-full opacity-0 transition-all group-hover:w-4 group-hover:opacity-100 focus-visible:w-4 focus-visible:opacity-100"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
