"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LoaderCircle, RefreshCw, Send, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
// import { ReportChatButtons } from "./ai-actions";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type ChatMessage = {
  id?: string;
  type?: string;
  name?: string | null;
  content?: unknown;
  tool_call_id?: string;
  tool_calls?: ToolCall[];
};

type ToolCall = {
  id?: string;
  name?: string;
  args?: Record<string, unknown>;
};

type ToolCallLookup = Record<
  string,
  {
    name?: string;
    args?: Record<string, unknown>;
  }
>;

const FINAL_RESPONSE_TOOL_NAMES = new Set(["NewStudy", "ExistingStudy"]);

function extractMessages(payload: unknown): ChatMessage[] {
  if (!payload) {
    return [];
  }

  const candidate = Array.isArray(payload) ? payload[0] : payload;
  if (!candidate || typeof candidate !== "object") {
    return [];
  }

  const maybeMessages = (candidate as { messages?: unknown }).messages;
  if (!Array.isArray(maybeMessages)) {
    return [];
  }

  return maybeMessages.filter((item): item is ChatMessage => {
    return !!item && typeof item === "object";
  });
}

function extractStructuredResponse(payload: unknown): unknown {
  if (!payload) {
    return null;
  }

  const candidate = Array.isArray(payload) ? payload[0] : payload;
  if (!candidate || typeof candidate !== "object") {
    return null;
  }

  const structuredResponse = (candidate as { structured_response?: unknown }).structured_response;
  return typeof structuredResponse === "undefined" ? null : structuredResponse;
}

function getEffectiveToolName(message: ChatMessage, toolCallLookup: ToolCallLookup): string | null {
  if (message.type !== "tool") {
    return null;
  }

  const linkedToolCall = message.tool_call_id ? toolCallLookup[message.tool_call_id] : undefined;
  return linkedToolCall?.name || message.name || null;
}

function extractFinalResponseReason(structuredResponse: unknown): string {
  if (!structuredResponse || typeof structuredResponse !== "object" || Array.isArray(structuredResponse)) {
    return "No reason provided.";
  }

  const reason = (structuredResponse as Record<string, unknown>).reason;
  if (typeof reason === "string" && reason.trim().length > 0) {
    return reason.trim();
  }

  return "No reason provided.";
}

function stripReasonFromStructuredResponse(structuredResponse: unknown): unknown {
  if (!structuredResponse || typeof structuredResponse !== "object" || Array.isArray(structuredResponse)) {
    return structuredResponse;
  }

  const { reason: _reason, ...rest } = structuredResponse as Record<string, unknown>;
  return rest;
}

function prettyJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function normalizeMessageContent(content: unknown): string {
  if (typeof content === "string") {
    return content;
  }

  if (content === null || typeof content === "undefined") {
    return "";
  }

  if (typeof content === "number" || typeof content === "boolean") {
    return String(content);
  }

  return prettyJson(content);
}

function formatToolMessageContent(content: string): string {
  try {
    return prettyJson(JSON.parse(content));
  } catch {
    return content;
  }
}

function tryParseObject(content: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(content) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
    return null;
  } catch {
    return null;
  }
}

function getNestedValue(
  payload: Record<string, unknown>,
  path: string[]
): string | number | null | undefined {
  let current: unknown = payload;

  for (const segment of path) {
    if (!current || typeof current !== "object" || Array.isArray(current)) {
      return undefined;
    }
    current = (current as Record<string, unknown>)[segment];
  }

  if (typeof current === "string" || typeof current === "number" || current === null) {
    return current;
  }

  return undefined;
}

function resolveToolDisplayName(message: ChatMessage, toolCallLookup: ToolCallLookup): string | null {
  if (message.type !== "tool" || !message.name) {
    return null;
  }

  const linkedToolCall = message.tool_call_id ? toolCallLookup[message.tool_call_id] : undefined;
  const linkedArgs = linkedToolCall?.args;
  const effectiveToolName = linkedToolCall?.name || message.name;
  const parsedContent = tryParseObject(normalizeMessageContent(message.content).trim());

  if (effectiveToolName === "fetch_next_candidate_study") {
    const reason =
      (linkedArgs && getNestedValue(linkedArgs, ["reason"])) ??
      (parsedContent &&
        (getNestedValue(parsedContent, ["reason"]) ??
          getNestedValue(parsedContent, ["args", "reason"]) ??
          getNestedValue(parsedContent, ["input", "reason"]))) ??
      "unknown reason";

    return `Loading next similar study (${String(reason)})`;
  }

  if (effectiveToolName === "fetch_report_fulltext") {
    const reportId =
      (linkedArgs && getNestedValue(linkedArgs, ["report_id"])) ??
      (parsedContent &&
        (getNestedValue(parsedContent, ["report_id"]) ??
          getNestedValue(parsedContent, ["args", "report_id"]) ??
          getNestedValue(parsedContent, ["input", "report_id"])));

    if (reportId === null || typeof reportId === "undefined" || reportId === "") {
      return "Loading reports fulltext";
    }

    return `Loading fulltext for report ${String(reportId)}`;
  }

  if (effectiveToolName === "fetch_report_abstract") {
    const reportId =
      (linkedArgs && getNestedValue(linkedArgs, ["report_id"])) ??
      (parsedContent &&
        (getNestedValue(parsedContent, ["report_id"]) ??
          getNestedValue(parsedContent, ["args", "report_id"]) ??
          getNestedValue(parsedContent, ["input", "report_id"])));

    return `Reading abstract for report ${String(reportId)}`;
  }

  if (effectiveToolName === "fetch_reports_linked_to_study") {
    const studyId =
      (linkedArgs && getNestedValue(linkedArgs, ["study_id"])) ??
      (parsedContent &&
        (getNestedValue(parsedContent, ["study_id"]) ??
          getNestedValue(parsedContent, ["args", "study_id"]) ??
          getNestedValue(parsedContent, ["input", "study_id"])));

    return `Reading report titles already linked to study ${String(studyId)}`;
  }

  if (effectiveToolName === "fetch_tags_associated_with_study") {
    const studyId =
      (linkedArgs && getNestedValue(linkedArgs, ["study_id"])) ??
      (parsedContent &&
        (getNestedValue(parsedContent, ["study_id"]) ??
          getNestedValue(parsedContent, ["args", "study_id"]) ??
          getNestedValue(parsedContent, ["input", "study_id"])));

    const tagCategory =
      (linkedArgs && getNestedValue(linkedArgs, ["tag_category"])) ??
      (parsedContent &&
        (getNestedValue(parsedContent, ["tag_category"]) ??
          getNestedValue(parsedContent, ["args", "tag_category"]) ??
          getNestedValue(parsedContent, ["input", "tag_category"])));

    return `Reading ${String(tagCategory)} associated with study ${String(studyId)}`;
  }

  if (effectiveToolName === "fetch_persons_associated_with_study") {
    const studyId =
      (linkedArgs && getNestedValue(linkedArgs, ["study_id"])) ??
      (parsedContent &&
        (getNestedValue(parsedContent, ["study_id"]) ??
          getNestedValue(parsedContent, ["args", "study_id"]) ??
          getNestedValue(parsedContent, ["input", "study_id"])));

    if (studyId === null || typeof studyId === "undefined" || studyId === "") {
      return "Checking persons associated with study";
    }

    return `Checking persons associated with study ${String(studyId)}`;
  }

  if (effectiveToolName === "fetch_study_by_shortname") {
    const shortName =
      (linkedArgs && getNestedValue(linkedArgs, ["short_name"])) ??
      (parsedContent &&
        (getNestedValue(parsedContent, ["short_name"]) ??
          getNestedValue(parsedContent, ["args", "short_name"]) ??
          getNestedValue(parsedContent, ["input", "short_name"])));

    if (shortName === null || typeof shortName === "undefined" || shortName === "") {
      return "Searched for studies with shortname";
    }

    return `Searched for studies with shortname ${String(shortName)}`;
  }

  return effectiveToolName;
}

interface ReportChatProps {
  reportId: number;
  open: boolean;
  setOpen: (open: boolean) => void;
}

export default function ReportChat({ reportId, open, setOpen}: ReportChatProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [messageInput, setMessageInput] = useState("");
  const [payload, setPayload] = useState<unknown>(null);
  const [pendingUserMessage, setPendingUserMessage] = useState<string | null>(null);
  const [expandedToolMessages, setExpandedToolMessages] = useState<Record<string, boolean>>({});
  const messageListRef = useRef<HTMLDivElement | null>(null);
  const messageListEndRef = useRef<HTMLDivElement | null>(null);

  const messages = useMemo(() => extractMessages(payload), [payload]);
  const structuredResponse = useMemo(() => extractStructuredResponse(payload), [payload]);
  const toolCallLookup = useMemo<ToolCallLookup>(() => {
    const lookup: ToolCallLookup = {};

    for (const message of messages) {
      if (!Array.isArray(message.tool_calls)) {
        continue;
      }

      for (const toolCall of message.tool_calls) {
        if (!toolCall?.id) {
          continue;
        }

        lookup[toolCall.id] = {
          name: toolCall.name,
          args:
            toolCall.args && typeof toolCall.args === "object" && !Array.isArray(toolCall.args)
              ? toolCall.args
              : undefined,
        };
      }
    }

    return lookup;
  }, [messages]);

  const structuredResponseText = useMemo(() => {
    if (structuredResponse === null) {
      return "";
    }

    return prettyJson(structuredResponse);
  }, [structuredResponse]);

  const finalResponseReason = useMemo(
    () => extractFinalResponseReason(structuredResponse),
    [structuredResponse]
  );

  const structuredResponseWithoutReasonText = useMemo(() => {
    if (structuredResponse === null) {
      return "";
    }

    return prettyJson(stripReasonFromStructuredResponse(structuredResponse));
  }, [structuredResponse]);

  const visibleMessages = useMemo(
    () =>
      messages.filter((message) => {
        if (message.type === "system") {
          return false;
        }

        const content = normalizeMessageContent(message.content).trim();
        if (content.length > 0) {
          return true;
        }

        if (structuredResponse === null) {
          return false;
        }

        const effectiveToolName = getEffectiveToolName(message, toolCallLookup);
        return !!effectiveToolName && FINAL_RESPONSE_TOOL_NAMES.has(effectiveToolName);
      }),
    [messages, structuredResponse, toolCallLookup]
  );

  const fetchChat = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);

    try {
      const response = await fetch(`/api/meerkat/reports/${reportId}/chat`, {
        method: "GET",
        cache: "no-store",
      });

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }

      const data = (await response.json()) as unknown;
      setPayload(data);
    } catch (fetchError) {
      console.error("Failed to fetch report chat:", fetchError);
      setLoadError("Unable to load the report chat. Please try again.");
    } finally {
      setIsLoading(false);
    }
  }, [reportId]);

  const sendMessage = useCallback(async () => {
    const message = messageInput.trim();
    if (!message || isSending) {
      return;
    }

    setIsSending(true);
    setSendError(null);
    setPendingUserMessage(message);

    try {
      const response = await fetch(`/api/meerkat/reports/${reportId}/chat`, {
        method: "POST",
        cache: "no-store",
        headers: {
          "Content-Type": "text/plain",
        },
        body: message,
      });

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }

      const data = (await response.json()) as unknown;
      setPayload(data);
      setMessageInput("");
    } catch (postError) {
      console.error("Failed to post chat message:", postError);
      setSendError("Unable to send message. Please try again.");
    } finally {
      setIsSending(false);
      setPendingUserMessage(null);
    }
  }, [isSending, messageInput, reportId]);

  const deleteChat = useCallback(async () => {
    if (isDeleting) {
      return;
    }

    setIsDeleting(true);
    setDeleteError(null);

    try {
      const response = await fetch(`/api/meerkat/reports/${reportId}/chat`, {
        method: "DELETE",
        cache: "no-store",
      });

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }

      setPayload(null);
      setExpandedToolMessages({});
      setMessageInput("");
      await fetchChat();
    } catch (deleteChatError) {
      console.error("Failed to delete report chat:", deleteChatError);
      setDeleteError("Unable to refresh chat history. Please try again.");
    } finally {
      setIsDeleting(false);
    }
  }, [fetchChat, isDeleting, reportId]);


  // Fetch chat when dialog is opened for the first time
  const hasFetchedRef = useRef(false);

  useEffect(() => {
    if (open && !hasFetchedRef.current) {
      fetchChat();
      hasFetchedRef.current = true;
    }
    if (!open) {
      hasFetchedRef.current = false;
    }
  }, [open, fetchChat]);

  const toggleToolMessage = useCallback((messageKey: string) => {
    setExpandedToolMessages((current) => ({
      ...current,
      [messageKey]: !current[messageKey],
    }));
  }, []);

  useEffect(() => {
    if (!open) {
      return;
    }

    requestAnimationFrame(() => {
      messageListEndRef.current?.scrollIntoView({ behavior: "auto", block: "end" });
      messageListRef.current?.scrollTo({
        top: messageListRef.current.scrollHeight,
        behavior: "auto",
      });
    });
  }, [isLoading, isSending, open, pendingUserMessage, visibleMessages.length]);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="h-[85vh] max-h-[85vh] overflow-hidden sm:max-w-4xl p-0 flex flex-col">
            <DialogHeader className="border-b px-6 pt-6 pb-4 shrink-0">
              <div className="flex items-center justify-start gap-3">
                <DialogTitle>Ask MediBot about the current report</DialogTitle>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void deleteChat()}
                  disabled={isDeleting || isLoading}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  {isDeleting ? "Clearing..." : "Clear Chat"}
                </Button>
              </div>
              {deleteError && <p className="mt-2 text-sm text-destructive">{deleteError}</p>}
            </DialogHeader>

            <div ref={messageListRef} className="h-full w-full flex-1 min-h-0 overflow-y-auto">
              <div className="w-full px-6 py-4 space-y-4">
                {isLoading && (
                  <div className="rounded-md border bg-muted/30 p-4 text-sm text-muted-foreground">
                    Loading chat history...
                  </div>
                )}

                {!isLoading && loadError && (
                  <div className="rounded-md border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
                    <p>{loadError}</p>
                    <Button
                      className="mt-3"
                      onClick={() => void fetchChat()}
                      size="sm"
                      type="button"
                      variant="outline"
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                      Retry
                    </Button>
                  </div>
                )}

                {!isLoading && !loadError && visibleMessages.length > 0 && (
                  <div className="w-full space-y-3">
                    {visibleMessages.map((message, index) => {
                      const role = message.type || "unknown";
                      const content = normalizeMessageContent(message.content).trim();
                      const formattedToolContent = formatToolMessageContent(content);
                      const messageKey = message.id ?? `${role}-${index}`;
                      const isToolMessage = message.type === "tool";
                      const effectiveToolName = getEffectiveToolName(message, toolCallLookup);
                      const isStructuredFinalResponse =
                        !!effectiveToolName && FINAL_RESPONSE_TOOL_NAMES.has(effectiveToolName);
                      const isToolMessageExpanded = !!expandedToolMessages[messageKey];
                      const toolDisplayName = resolveToolDisplayName(message, toolCallLookup);
                      const isHumanMessage = message.type === "user" || message.type === "human";
                      const messageStripeClass = isHumanMessage
                        ? "border-l-4 border-l-emerald-500"
                        : "border-r-4 border-r-sky-500";
                      const finalResponseSummary =
                        effectiveToolName === "ExistingStudy"
                          ? `I think this report belongs to an existing study because: ${finalResponseReason}`
                          : `I think this report belongs to a new study because: ${finalResponseReason}`;

                      return (
                        <div key={messageKey} className={`w-full ${isHumanMessage ? "pl-6" : ""}`}>
                          <div className={`w-full rounded-lg border bg-card p-4 ${messageStripeClass}`}>
                          <div className="flex items-center gap-2">
                            {(isStructuredFinalResponse
                              ? finalResponseSummary
                              : isToolMessage
                                ? toolDisplayName
                                : message.name) && (
                              <span className="mb-3 text-xs text-muted-foreground">
                                {isStructuredFinalResponse
                                  ? finalResponseSummary
                                  : isToolMessage
                                    ? toolDisplayName
                                    : message.name}
                              </span>
                            )}
                          </div>
                          {isStructuredFinalResponse ? (
                            <pre className="overflow-x-auto whitespace-pre-wrap break-all text-sm leading-relaxed">
                              {structuredResponseWithoutReasonText || structuredResponseText || formattedToolContent}
                            </pre>
                          ) : isToolMessage ? (
                            <div >
                              <div
                                aria-expanded={isToolMessageExpanded}
                                className="cursor-pointer rounded-md border border-dashed bg-muted/20 px-3 py-2 text-xs text-muted-foreground transition-colors hover:bg-muted/30"
                                onClick={() => toggleToolMessage(messageKey)}
                                onKeyDown={(event) => {
                                  if (event.key === "Enter" || event.key === " ") {
                                    event.preventDefault();
                                    toggleToolMessage(messageKey);
                                  }
                                }}
                                role="button"
                                tabIndex={0}
                              >
                                {isToolMessageExpanded
                                  ? "Click to collapse."
                                  : "Click to view details."}
                              </div>
                              {isToolMessageExpanded && (
                                <pre className="overflow-x-auto whitespace-pre-wrap break-all text-sm leading-relaxed">
                                  {formattedToolContent}
                                </pre>
                              )}
                            </div>
                          ) : (
                            <pre className="overflow-x-auto whitespace-pre-wrap break-all text-sm leading-relaxed">
                              {content}
                            </pre>
                          )}
                        </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {!isLoading && !loadError && isSending && pendingUserMessage && (
                  <div className="w-full pl-6">
                    <div className="w-full rounded-lg border border-l-4 border-l-emerald-500 bg-card p-4">
                      <pre className="overflow-x-auto whitespace-pre-wrap break-all text-sm leading-relaxed">
                        {pendingUserMessage}
                      </pre>
                    </div>
                  </div>
                )}

                {!isLoading && !loadError && isSending && (
                  <div className="w-full">
                    <div className="w-full rounded-lg border border-r-4 border-r-sky-500 bg-card p-4">
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <LoaderCircle className="h-4 w-4 animate-spin" />
                        MediBot is thinking...
                      </div>
                    </div>
                  </div>
                )}

                <div ref={messageListEndRef} aria-hidden="true" />
              </div>
            </div>

            <div className="shrink-0 border-t bg-background px-6 py-4">
              <Textarea
                className="min-h-[88px] resize-none"
                id="report-chat-message"
                placeholder="Write a message..."
                value={messageInput}
                onChange={(event) => setMessageInput(event.target.value)}
              />
              {sendError && <p className="mt-2 text-sm text-destructive">{sendError}</p>}
              <div className="mt-3 flex justify-end">
                <Button
                  type="button"
                  onClick={() => void sendMessage()}
                  disabled={isSending || messageInput.trim().length === 0}
                >
                  <Send className="h-4 w-4" />
                  {isSending ? "Waiting..." : "Send"}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      );
    }
