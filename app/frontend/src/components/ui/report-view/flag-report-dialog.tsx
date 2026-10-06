import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { getReportFlagByReportId, upsertReportFlagByReportId } from "@/lib/api/reportApi";

export interface FlagTarget {
  id: number;
  title: string;
}

interface FlagReportDialogProps {
  /** The report being flagged; the dialog is open exactly while this is set. */
  target: FlagTarget | null;
  onClose: () => void;
  onSaved: (reportId: number, message: string) => void;
}

export function FlagReportDialog({ target, onClose, onSaved }: FlagReportDialogProps) {
  const [details, setDetails] = useState("");
  const [visibility, setVisibility] = useState<"private" | "public">("private");
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Start blank, then prefill with the user's existing flag on this report (if any).
  useEffect(() => {
    setDetails("");
    setVisibility("private");
    if (!target) return;

    let cancelled = false;
    getReportFlagByReportId(target.id)
      .then((payload) => {
        if (cancelled || !payload || typeof payload.message !== "string") return;
        setDetails(payload.message);
        setVisibility(payload.public ? "public" : "private");
      })
      .catch((error) => console.error("Error fetching report flag:", error));

    return () => {
      cancelled = true;
    };
  }, [target]);

  const handleSubmit = async () => {
    if (!target) return;

    const message = details.trim();
    if (!message) {
      toast.error("Please add a short description before submitting.");
      return;
    }

    setIsSubmitting(true);
    try {
      await upsertReportFlagByReportId(target.id, { message, public: visibility === "public" });
      onSaved(target.id, message);
      toast.success("Flag saved.");
      onClose();
    } catch (error) {
      console.error("Error submitting report flag:", error);
      toast.error("Could not submit your report. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={target !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-[560px]" onClick={(e) => e.stopPropagation()}>
        <DialogHeader>
          <DialogTitle>Flag report</DialogTitle>
          <DialogDescription>
            Report issues with this item so your team can review it.
          </DialogDescription>
        </DialogHeader>

        {target && (
          <div className="space-y-4">
            <div className="rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
              <span className="font-medium text-foreground">Report:</span> {target.title}
            </div>

            <div className="space-y-2">
              <label htmlFor="flag-details" className="text-sm font-medium">
                Details
              </label>
              <Textarea
                id="flag-details"
                value={details}
                onChange={(e) => setDetails(e.target.value)}
                placeholder="Tell us what is wrong with this report..."
                className="h-28 min-h-28 resize-none"
              />
            </div>

            <div className="space-y-2">
              <p className="text-sm font-medium">Visibility</p>
              <RadioGroup
                value={visibility}
                onValueChange={(value) => setVisibility(value as "private" | "public")}
                className="gap-2"
              >
                <VisibilityOption value="private" title="Private" description="Visible to you only." />
                <VisibilityOption
                  value="public"
                  title="Public"
                  description="Visible to you and the project owner."
                />
              </RadioGroup>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button type="button" onClick={handleSubmit} disabled={isSubmitting}>
            {isSubmitting ? "Submitting..." : "Submit"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function VisibilityOption({
  value,
  title,
  description,
}: {
  value: "private" | "public";
  title: string;
  description: string;
}) {
  const id = `flag-visibility-${value}`;
  return (
    <label htmlFor={id} className="flex items-start gap-2 rounded-md border p-3 cursor-pointer">
      <RadioGroupItem id={id} value={value} />
      <span className="text-sm leading-tight">
        <span className="font-medium">{title}</span>
        <span className="block text-xs text-muted-foreground">{description}</span>
      </span>
    </label>
  );
}
