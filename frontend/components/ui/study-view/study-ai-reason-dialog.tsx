"use client";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { AIClassification } from "@/hooks/use-genai-evaluation-store";
import { StudyAIBadge } from "./study-ai-badge";

interface StudyAIReasonDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  studyName: string;
  classification: AIClassification;
  reason: string;
}

export function StudyAIReasonDialog({
  open,
  onOpenChange,
  studyName,
  classification,
  reason,
}: StudyAIReasonDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[525px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            AI Evaluation: {studyName}
          </DialogTitle>
          <DialogDescription className="flex items-center gap-2 pt-2">
            Classification: <StudyAIBadge classification={classification} />
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <h4 className="mb-2 text-sm font-medium">Reasoning:</h4>
            <p className="text-sm text-muted-foreground leading-relaxed">
              {reason}
            </p>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
