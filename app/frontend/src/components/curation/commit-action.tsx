import { useState } from "react";
import { Check, Send } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { commitProjectWork } from "@/lib/api/projectApi";

interface CommitActionProps {
  projectId: string;
  projectName: string;
  /** Reports the user is done with (linked or flagged publicly), committed ones included. */
  completed: number;
  /** Reports the user has committed their links of. */
  committed: number;
  total: number;
  /** The user has committed every report. */
  done: boolean;
  /** The names of the assignees who have not committed yet, the user aside; an empty name for one whose is unknown. */
  waitingFor: string[];
  onCommitted?: () => void;
}

// Whom the update waits for, by first name: "Jana", "Jana and Ben", "Jana, Ben and 2 more"; the ones without a name
// are counted ("2 annotators", "Jana and 1 more").
const MAX_NAMES = 2;
export function waitingForText(names: string[]): string {
  const firstNames = names.map((name) => name.trim().split(/\s+/)[0]).filter(Boolean);
  const shown = firstNames.slice(0, MAX_NAMES);
  const more = names.length - shown.length;
  if (shown.length === 0) return `${more} ${more === 1 ? "annotator" : "annotators"}`;
  if (more === 0) return shown.join(" and ");
  return `${shown.join(", ")} and ${more} more`;
}

/**
 * The assignee hands in their links of the reports they are done with and have not committed yet, after a confirmation
 * (they cannot change those links afterwards, and the reports leave their list). Once all assignees have committed
 * every report, the update is locked and its owner merges the links.
 */
export function CommitAction({
  projectId,
  projectName,
  completed,
  committed,
  total,
  done,
  waitingFor,
  onCommitted,
}: CommitActionProps) {
  const [open, setOpen] = useState(false);
  const [committing, setCommitting] = useState(false);

  if (done) {
    return (
      <span
        className="inline-flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground"
        title={waitingFor.some(Boolean) ? `Waiting for ${waitingFor.filter(Boolean).join(", ")}` : undefined}
      >
        <Check className="h-3.5 w-3.5 shrink-0 text-primary" aria-hidden />
        <span className="truncate">
          <span className="font-medium text-foreground">Committed</span>
          {waitingFor.length > 0 && ` · waiting for ${waitingForText(waitingFor)}`}
        </span>
      </span>
    );
  }
  // What is left of the update: the reports not committed yet, of which those the user is done with go now.
  const remaining = total - committed;
  const ready = completed - committed;
  if (ready <= 0) return null;
  const label = `${ready}/${remaining} ${remaining === 1 ? "report" : "reports"}`;

  const commit = async () => {
    setCommitting(true);
    try {
      await commitProjectWork(projectId);
      setOpen(false);
      onCommitted?.();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Your links could not be committed.");
    } finally {
      setCommitting(false);
    }
  };

  return (
    <>
      <Button size="sm" className="gap-1.5" onClick={() => setOpen(true)}>
        <Send className="h-4 w-4" />
        Commit {label}
      </Button>
      <AlertDialog open={open} onOpenChange={setOpen}>
        <AlertDialogContent className="sm:max-w-md">
          <AlertDialogHeader>
            <AlertDialogTitle>Commit your links?</AlertDialogTitle>
            <AlertDialogDescription>
              You commit your links of {label} of {projectName}. Once committed, you cannot change them any more and
              the reports leave your list; when all assignees have committed every report, the update is locked and
              merged.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="gap-2 sm:gap-2">
            <AlertDialogCancel disabled={committing}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={committing}
              onClick={(event) => {
                event.preventDefault();
                void commit();
              }}
            >
              {committing ? "Committing..." : "Commit"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
