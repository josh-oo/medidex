"use client"

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Spinner } from "@/components/ui/spinner";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { CircleHelp } from "lucide-react";
import { useGenAIEvaluationStore } from "@/hooks/use-genai-evaluation-store";
import { useReportStore } from "@/hooks/use-report-store";
import { toast } from "sonner";
import type { AIModel, PromptOverrides, DefaultPrompts } from "@/hooks/use-genai-evaluation-store";
import { RelevanceStudy } from "@/types/reports";

const MODEL_OPTIONS: AIModel[] = ["gpt-5.2", "gpt-5", "gpt-5-mini", "gpt-4.1"];
const EMPTY_PROMPT_OVERRIDES: PromptOverrides = {
  background_prompt: "",
  initial_eval_prompt: "",
  likely_group_prompt: "",
  likely_compare_prompt: "",
  likely_review_prompt: "",
  unsure_review_prompt: "",
  summary_prompt: "",
  pdf_prompt: "",
};

interface AIMatchSettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  reportId?: number;
  studies: RelevanceStudy[];
}

export function AIMatchSettingsDialog({
  open,
  onOpenChange,
  reportId,
  studies,
}: AIMatchSettingsDialogProps) {
    const getReport = useReportStore((state) => state.getReport);
    const evaluateStream = useGenAIEvaluationStore((state) => state.evaluateStream);
    const canStartEvaluation = useGenAIEvaluationStore((state) => state.canStartEvaluation);
    const getRunningEvaluationsCount = useGenAIEvaluationStore((state) => state.getRunningEvaluationsCount);
    const runningEvaluations = useGenAIEvaluationStore((state) => state.runningEvaluations);
    const isRunning = reportId ? runningEvaluations.includes(reportId) : false;

    const handleAIEvaluation = async (options: {
        model?: AIModel;
        includePdf?: boolean;
        promptOverrides?: PromptOverrides;
    }) => {
        if (reportId === undefined) {
            toast.error("Missing report id");
            return false;
        }

        const currentReport = getReport(reportId);
        if (!currentReport) {
            toast.error("Report not found");
            return false;
        }

        try {
            const runningCount = getRunningEvaluationsCount();
            toast.info(`Evaluating ${studies.length} studies with AI (${runningCount + 1}/4 running)...`);
            evaluateStream(
                currentReport.report,
                studies.map((study: any) => study.study),
                options,
                () => {
                    toast.success("AI evaluation complete!");
                }
            );
            return true;
        } catch (error) {
            toast.error(
                `AI evaluation failed: ${error instanceof Error ? error.message : "Unknown error"}`
            );
            return false;
        }
    };

    const runningCount = getRunningEvaluationsCount();
    const disableRun= studies.length === 0 || !canStartEvaluation();

    const [model, setModel] = useState<AIModel>("gpt-5-mini");
    const [includePdf, setIncludePdf] = useState(false);
    const [promptOverrides, setPromptOverrides] = useState<PromptOverrides>(
      EMPTY_PROMPT_OVERRIDES
    );
    const [defaultPrompts, setDefaultPrompts] = useState<DefaultPrompts | null>(null);
    const [promptsError, setPromptsError] = useState<string | null>(null);
  
    const updatePromptOverride = (
        key: keyof PromptOverrides,
        value: string
    ) => {
        setPromptOverrides((prev) => ({ ...prev, [key]: value }));
    };
  
    useEffect(() => {
      void (async () => {
        try {
          const response = await fetch("/api/genai/prompts");
          if (!response.ok) {
            throw new Error(`Failed to fetch default prompts: ${response.statusText}`);
          }
          const data = await response.json();
          setDefaultPrompts(data);
          setPromptsError(null);
        } catch (error) {
          setPromptsError(
            error instanceof Error ? error.message : "Failed to load default prompts."
          );
        }
      })();
    }, []);
  
    const buildPromptOverridesPayload = () => {
      const cleaned: PromptOverrides = {
        background_prompt: promptOverrides.background_prompt?.trim() || undefined,
        initial_eval_prompt:
          promptOverrides.initial_eval_prompt?.trim() || undefined,
        likely_group_prompt:
          promptOverrides.likely_group_prompt?.trim() || undefined,
        likely_compare_prompt:
          promptOverrides.likely_compare_prompt?.trim() || undefined,
        likely_review_prompt:
          promptOverrides.likely_review_prompt?.trim() || undefined,
        unsure_review_prompt:
          promptOverrides.unsure_review_prompt?.trim() || undefined,
        summary_prompt: promptOverrides.summary_prompt?.trim() || undefined,
        pdf_prompt: promptOverrides.pdf_prompt?.trim() || undefined,
      };
      const hasOverrides = Object.values(cleaned).some((value) => value);
      return hasOverrides ? cleaned : undefined;
    };
  
    const handleRun = async () => {
        onOpenChange(false);
        await handleAIEvaluation({
        model,
        includePdf,
        promptOverrides: buildPromptOverridesPayload(),
        });
    };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[720px] max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>AI Match Settings</DialogTitle>
          <DialogDescription>
            Configure the model, report PDF inclusion, and optional prompt overrides
            before running evaluation.
          </DialogDescription>
          {runningCount !== undefined && runningCount > 0 && (
            <p className="text-sm text-muted-foreground">
              {runningCount} evaluation{runningCount > 1 ? 's' : ''} currently running
            </p>
          )}
        </DialogHeader>
        {promptsError ? (
          <p className="text-sm text-destructive">{promptsError}</p>
        ) : null}
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="ai-model">Model</Label>
              <Select value={model} onValueChange={(value) => setModel(value as AIModel)}>
                <SelectTrigger id="ai-model">
                  <SelectValue placeholder="Select model" />
                </SelectTrigger>
                <SelectContent>
                  {MODEL_OPTIONS.map((option) => (
                    <SelectItem key={option} value={option}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="ai-include-pdf">Include report PDF</Label>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="ai-include-pdf"
                  checked={includePdf}
                  onCheckedChange={(checked) => setIncludePdf(Boolean(checked))}
                />
                <span className="text-sm text-muted-foreground">
                  Attach the PDF for the report being matched.
                </span>
              </div>
            </div>
          </div>

          <Accordion type="single" collapsible>
            <AccordionItem value="prompt-overrides" className="border-b-0">
              <AccordionTrigger className="text-sm">
                <span className="flex items-center gap-2">
                  <span>Custom prompt overrides (advanced)</span>
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span
                          className="inline-flex cursor-help items-center text-muted-foreground transition-colors hover:text-foreground"
                        >
                          <CircleHelp className="h-4 w-4" />
                        </span>
                      </TooltipTrigger>
                      <TooltipContent className="max-w-[34rem] text-left text-wrap text-xs leading-relaxed">
                        <ol className="list-decimal space-y-1 pl-4">
                          <li>
                            Initial pass: each study is labeled <strong>Not Match</strong>,{" "}
                            <strong>Likely</strong>, or <strong>Unsure</strong>.
                          </li>
                          <li>
                            Likely selection pass: AI selects up to 2 <strong>Very Likely</strong>{" "}
                            candidates and compares them.
                          </li>
                          <li>
                            Likely review pass: if no <strong>Match</strong> is found, remaining{" "}
                            <strong>Likely</strong> studies are re-reviewed.
                          </li>
                          <li>
                            Unsure pass: if still no <strong>Match</strong> is found, only{" "}
                            <strong>Unsure</strong> studies are re-reviewed.
                          </li>
                          <li>
                            Summary pass: AI returns a final explanation and may suggest a new
                            study.
                          </li>
                        </ol>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </span>
              </AccordionTrigger>
              <AccordionContent className="space-y-4 pt-3">
                <div className="space-y-2">
                  <Label htmlFor="override-background-prompt">
                    Background prompt
                  </Label>
                  <Textarea
                    id="override-background-prompt"
                    value={promptOverrides.background_prompt || ""}
                    onChange={(event) =>
                      updatePromptOverride(
                        "background_prompt",
                        event.target.value
                      )
                    }
                    placeholder={
                      defaultPrompts?.background_prompt ||
                      "Leave blank to use BACKGROUND_PROMPT."
                    }
                    rows={4}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="override-eval-prompt">
                    Initial evaluation prompt
                  </Label>
                  <Textarea
                    id="override-eval-prompt"
                    value={promptOverrides.initial_eval_prompt || ""}
                    onChange={(event) =>
                      updatePromptOverride(
                        "initial_eval_prompt",
                        event.target.value
                      )
                    }
                    placeholder={
                      defaultPrompts?.initial_eval_prompt ||
                      "Leave blank to use DEFAULT_EVAL_PROMPT."
                    }
                    rows={4}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="override-likely-group-prompt">
                    Likely group prompt
                  </Label>
                  <Textarea
                    id="override-likely-group-prompt"
                    value={promptOverrides.likely_group_prompt || ""}
                    onChange={(event) =>
                      updatePromptOverride(
                        "likely_group_prompt",
                        event.target.value
                      )
                    }
                    placeholder={
                      defaultPrompts?.likely_group_prompt ||
                      "Leave blank to use DEFAULT_LIKELY_GROUP_PROMPT."
                    }
                    rows={4}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="override-likely-compare-prompt">
                    Likely compare prompt
                  </Label>
                  <Textarea
                    id="override-likely-compare-prompt"
                    value={promptOverrides.likely_compare_prompt || ""}
                    onChange={(event) =>
                      updatePromptOverride(
                        "likely_compare_prompt",
                        event.target.value
                      )
                    }
                    placeholder={
                      defaultPrompts?.likely_compare_prompt ||
                      "Leave blank to use DEFAULT_LIKELY_COMPARE_PROMPT."
                    }
                    rows={4}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="override-likely-review-prompt">
                    Likely review prompt
                  </Label>
                  <Textarea
                    id="override-likely-review-prompt"
                    value={promptOverrides.likely_review_prompt || ""}
                    onChange={(event) =>
                      updatePromptOverride(
                        "likely_review_prompt",
                        event.target.value
                      )
                    }
                    placeholder={
                      defaultPrompts?.likely_review_prompt ||
                      "Leave blank to use DEFAULT_LIKELY_REVIEW_PROMPT."
                    }
                    rows={4}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="override-unsure-review-prompt">
                    Unsure review prompt
                  </Label>
                  <Textarea
                    id="override-unsure-review-prompt"
                    value={promptOverrides.unsure_review_prompt || ""}
                    onChange={(event) =>
                      updatePromptOverride(
                        "unsure_review_prompt",
                        event.target.value
                      )
                    }
                    placeholder={
                      defaultPrompts?.unsure_review_prompt ||
                      "Leave blank to use DEFAULT_UNSURE_REVIEW_PROMPT."
                    }
                    rows={4}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="override-summary-prompt">
                    Summary prompt
                  </Label>
                  <Textarea
                    id="override-summary-prompt"
                    value={promptOverrides.summary_prompt || ""}
                    onChange={(event) =>
                      updatePromptOverride("summary_prompt", event.target.value)
                    }
                    placeholder={
                      defaultPrompts?.summary_prompt ||
                      "Leave blank to use DEFAULT_SUMMARY_PROMPT."
                    }
                    rows={4}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="override-pdf-prompt">
                    PDF attachment note
                  </Label>
                  <Textarea
                    id="override-pdf-prompt"
                    value={promptOverrides.pdf_prompt || ""}
                    onChange={(event) =>
                      updatePromptOverride("pdf_prompt", event.target.value)
                    }
                    placeholder={
                      defaultPrompts?.pdf_prompt ||
                      "Leave blank to use the default note (appended when Include report PDF is on)."
                    }
                    rows={3}
                  />
                </div>
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => void handleRun()}
            disabled={isRunning || disableRun}
          >
            {isRunning ? <Spinner className="h-4 w-4" /> : "Run"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
