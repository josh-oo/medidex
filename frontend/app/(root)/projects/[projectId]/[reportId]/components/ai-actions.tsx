"use client"

import { Bot, MessageSquareText, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import { useState } from "react";
import ReportChat from "./report-chat";
import { AIMatchSettingsDialog } from "@/components/ui/study-view/ai-match-settings-dialog";
import { RelevanceStudy } from "@/types/reports";
import { useGenAIEvaluationStore } from "@/hooks/use-genai-evaluation-store";
import { Spinner } from "@/components/ui/spinner";

interface ReportChatButtonsProps {
  reportId: number;
  studies: RelevanceStudy[];
}

export function ReportChatButtons({ reportId, studies }: ReportChatButtonsProps) {
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [autoMatchOpen, setAutoMatchOpen] = useState(false);

  const runningEvaluations = useGenAIEvaluationStore((state) => state.runningEvaluations);
  const isRunning = reportId ? runningEvaluations.includes(reportId) : false;

  const handleChatClick = () => {
    setPopoverOpen(false);
    setChatOpen(true);
  };

  const handleAutoMatchClick = () => {
    setPopoverOpen(false);
    setAutoMatchOpen(true);
  };

  return (
    <>
      <Popover open={popoverOpen} onOpenChange={setPopoverOpen}>
        <PopoverTrigger asChild>
          <Button
            className="fixed right-6 bottom-6 z-40 h-12 rounded-full px-4 shadow-lg"
            size="lg"
            type="button"
            onClick={() => setPopoverOpen((v) => !v)}
          >
            <Bot className="h-4 w-4" />
            Ask MediBot
          </Button>
        </PopoverTrigger>
        <PopoverContent
          align="end"
          sideOffset={12}
          className="!bg-transparent !border-0 !shadow-none p-0 w-auto"
        >
          <Button
            type="button"
            className="h-10 rounded-full w-full justify-start mb-2"
            onClick={handleAutoMatchClick}
            disabled={isRunning || studies.length === 0}
          >
            {isRunning ? (
                <Spinner className="h-4 w-4" />
              ) : (
                <Sparkles className="h-4 w-4" />
              )}
            Auto Match
          </Button>
          <Button
            type="button"
            className="h-10 rounded-full w-full justify-start"
            onClick={handleChatClick}
          >
            <MessageSquareText className="h-4 w-4" />
            Chat
          </Button>
        </PopoverContent>
      </Popover>
      <ReportChat reportId={reportId} open={chatOpen} setOpen={setChatOpen}/>
      <AIMatchSettingsDialog
              open={autoMatchOpen}
              onOpenChange={setAutoMatchOpen}
              reportId={reportId}
              studies={studies}
            />
    </>
  );
}
