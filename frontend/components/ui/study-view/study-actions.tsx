"use client";

import { Button } from "@/components/ui/button";
import { 
  Sparkles, 
  FileCheck, 
  Download,
} from "lucide-react";
import { toast } from "sonner";

interface StudyActionsProps {
  studyId: string;
  studyName: string;
}

export function StudyActions({ studyId, studyName }: StudyActionsProps) {
  const handleAskLLM = () => {
    toast.info("LLM assistant feature coming soon!");
  };

  const handleMatchReport = () => {
    toast.info("Report matching feature coming soon!");
  };

  const handleExport = () => {
    toast.info("Export feature coming soon!");
  };

  return (
    <div className="flex items-center justify-end gap-2 py-2">
      <Button 
        size="sm" 
        variant="outline"
        onClick={handleMatchReport}
        className="gap-2"
      >
        <FileCheck className="h-4 w-4" />
        <span className="hidden sm:inline">Match Report</span>
        <span className="sm:hidden">Match</span>
      </Button>
      
      <Button 
        size="sm" 
        variant="outline"
        onClick={handleAskLLM}
        className="gap-2"
      >
        <Sparkles className="h-4 w-4" />
        <span className="hidden sm:inline">Ask AI</span>
        <span className="sm:hidden">AI</span>
      </Button>
      
      <Button 
        size="sm" 
        variant="ghost"
        onClick={handleExport}
      >
        <Download className="h-4 w-4" />
      </Button>
    </div>
  );
}
