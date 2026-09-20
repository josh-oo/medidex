"use client";

import { useEffect, useRef } from "react";
import { Spinner } from "@/components/ui/spinner";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  Info
} from "lucide-react";

interface AiEvaluationProgressProps {
  message: string | null;
  isStreaming: boolean;
  hasSummary: boolean;
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
  onShowStepHistory: () => void;
}

const isMarkdown = (value: string) =>
  /(^|\n)\s*#{1,6}\s+/.test(value) ||
  /(^|\n)\s*[-*+]\s+/.test(value) ||
  /(^|\n)\s*\d+\.\s+/.test(value) ||
  /`{1,3}[\s\S]*`{1,3}/.test(value) ||
  /\*\*[^*]+\*\*/.test(value);

export function AiEvaluationProgress({
  message,
  isStreaming,
  hasSummary,
  collapsed,
  onCollapsedChange,
  onShowStepHistory,
}: AiEvaluationProgressProps) {
  if (!isStreaming && !message) {
    return null;
  }

  const wasStreaming = useRef(isStreaming);
  const canCollapse = hasSummary;

  useEffect(() => {
    if (!canCollapse) {
      if (collapsed) onCollapsedChange(false);
      wasStreaming.current = isStreaming;
      return;
    }
    if (isStreaming) {
      if (collapsed) onCollapsedChange(false);
    }
    wasStreaming.current = isStreaming;
  }, [canCollapse, isStreaming, collapsed, onCollapsedChange]);

  const shouldRenderMarkdown = message ? isMarkdown(message) : false;
  const previewText = message
    ? message.replace(/\s+/g, " ").trim().slice(0, 160) +
      (message.length > 160 ? "…" : "")
    : "";
  const collapsedText = isStreaming
    ? previewText || "AI evaluation in progress..."
    : "Summary available. Click Show to view details.";

  return (
    <div className="m-4 mb-0 rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-900 dark:bg-blue-950">
      <div className="flex items-center gap-3">
        {isStreaming ? (
          <Spinner className="h-4 w-4 flex-shrink-0 text-blue-600 dark:text-blue-400" />
        ) : null}
        {collapsed || isStreaming ? (
          <div className="flex-1 text-sm font-medium text-blue-900 dark:text-blue-100">
            {collapsed ? collapsedText : "AI evaluation in progress"}
          </div>
        ) : (
          <div className="flex-1 text-sm font-medium text-blue-900 dark:text-blue-100">
            AI Evaluation Completed!
          </div>
        )}
        {canCollapse ? (
          <button
            type="button"
            onClick={() => onCollapsedChange(!collapsed)}
            className="ml-auto text-xs font-medium text-blue-700 hover:text-blue-900 dark:text-blue-200 dark:hover:text-blue-100"
            aria-expanded={!collapsed}
          >
            {collapsed ? "Show" : "Hide"}
          </button>
        ) : null}
        {/* Info icon */}
      <button
        type="button"
        onClick={onShowStepHistory} // define this handler
        className="text-blue-700 hover:text-blue-900 dark:text-blue-200 dark:hover:text-blue-100"
        aria-label="More info"
      >
        <Info className="h-4 w-4" />
      </button>
      </div>
      {!collapsed && message ? (
        <div className="mt-3 max-h-[260px] overflow-y-auto pr-2">
          {shouldRenderMarkdown ? (
            <div className="text-sm text-blue-900 dark:text-blue-100 space-y-2">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  p: (props) => <p className="text-sm font-medium" {...props} />,
                  ul: (props) => <ul className="list-disc pl-5 space-y-1" {...props} />,
                  ol: (props) => <ol className="list-decimal pl-5 space-y-1" {...props} />,
                  li: (props) => <li className="text-sm font-medium" {...props} />,
                  strong: (props) => <strong className="font-semibold" {...props} />,
                  em: (props) => <em className="italic" {...props} />,
                }}
              >
                {message}
              </ReactMarkdown>
            </div>
          ) : (
            <p className="text-sm font-medium text-blue-900 dark:text-blue-100 whitespace-pre-wrap">
              {message}
            </p>
          )}
        </div>
      ) : null}
    </div>
  );
}
