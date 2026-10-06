import type { StudyColor } from "@/types/apiDTOs";

// Tailwind class names of the colors of the study schema. Written out in full (not built
// from the color name) so that Tailwind finds them.
export interface ColorClasses {
  accent: string; // icon and emphasis
  bg: string; // soft background
  border: string; // left border of a tile
}

export const STUDY_COLORS: Record<StudyColor, ColorClasses> = {
  blue: {
    accent: "text-blue-600 dark:text-blue-400",
    bg: "bg-blue-50 dark:bg-blue-950/30",
    border: "border-l-blue-500",
  },
  emerald: {
    accent: "text-emerald-600 dark:text-emerald-400",
    bg: "bg-emerald-50 dark:bg-emerald-950/30",
    border: "border-l-emerald-500",
  },
  rose: {
    accent: "text-rose-600 dark:text-rose-400",
    bg: "bg-rose-50 dark:bg-rose-950/30",
    border: "border-l-rose-500",
  },
  amber: {
    accent: "text-amber-600 dark:text-amber-400",
    bg: "bg-amber-50 dark:bg-amber-950/30",
    border: "border-l-amber-500",
  },
  slate: {
    accent: "text-slate-600 dark:text-slate-400",
    bg: "bg-slate-100 dark:bg-slate-800/50",
    border: "border-l-slate-500",
  },
  sky: {
    accent: "text-sky-600 dark:text-sky-400",
    bg: "bg-sky-50 dark:bg-sky-950/30",
    border: "border-l-sky-500",
  },
  violet: {
    accent: "text-violet-600 dark:text-violet-400",
    bg: "bg-violet-50 dark:bg-violet-950/30",
    border: "border-l-violet-500",
  },
  teal: {
    accent: "text-teal-600 dark:text-teal-400",
    bg: "bg-teal-50 dark:bg-teal-950/30",
    border: "border-l-teal-500",
  },
};

export const colorClasses = (color: string): ColorClasses =>
  STUDY_COLORS[color as StudyColor] ?? STUDY_COLORS.slate;
