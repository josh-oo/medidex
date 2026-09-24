"use client";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import type { StreamEvent } from "@/types/apiDTOs";
import { formatDistanceToNow } from "date-fns";

interface AiEvaluationHistoryDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  streamMessages: StreamEvent[];
}

export function AiEvaluationHistoryDialog({
  open,
  onOpenChange,
  streamMessages,
}: AiEvaluationHistoryDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[700px]">
        <DialogHeader>
          <DialogTitle>AI Evaluation History</DialogTitle>
          <DialogDescription>
            Complete step-by-step evaluation process ({streamMessages.length} events)
          </DialogDescription>
        </DialogHeader>
        <ScrollArea className="h-[500px] pr-4">
          <div className="space-y-3">
            {streamMessages.map((event, index) => (
              <div
                key={index}
                className="border rounded-lg p-3 space-y-2 text-sm"
              >
                <div className="flex items-center justify-between gap-2">
                  <Badge variant="outline" className="font-mono text-xs">
                    {event.node}
                  </Badge>
                  {event.timestamp && (
                    <span className="text-xs text-muted-foreground">
                      {formatDistanceToNow(new Date(event.timestamp), {
                        addSuffix: true,
                      })}
                    </span>
                  )}
                </div>
                {event.message && (
                  <p className="text-muted-foreground leading-relaxed">
                    {event.message}
                  </p>
                )}
                {event.details && Object.keys(event.details).length > 0 && (
                  <details className="text-xs">
                    <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                      Details
                    </summary>
                    <pre className="mt-2 p-2 bg-muted rounded overflow-x-auto whitespace-pre-wrap break-words max-w-full">
                      {JSON.stringify(event.details, null, 2)}
                    </pre>

                  </details>
                )}
              </div>
            ))}
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
