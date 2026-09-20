"use client";

import { Badge } from "@/components/ui/badge";
import { CheckCircle2, XCircle, HelpCircle, TrendingUp, Star } from "lucide-react";
import type { AIClassification } from "@/hooks/use-genai-evaluation-store";

interface StudyAIBadgeProps {
  classification: AIClassification;
  onClick?: (e: React.MouseEvent) => void;
}

const classificationConfig: Record<
  AIClassification,
  {
    label: string;
    icon: React.ReactNode;
    variant: "default" | "secondary" | "destructive" | "outline";
    className: string;
  }
> = {
  match: {
    label: "Match",
    icon: <Star className="h-3 w-3" />,
    variant: "default",
    className: "bg-green-600 hover:bg-green-700 text-white cursor-pointer",
  },
  likely_match: {
    label: "Likely",
    icon: <TrendingUp className="h-3 w-3" />,
    variant: "secondary",
    className: "bg-yellow-500 hover:bg-yellow-600 text-white cursor-pointer",
  },
  very_likely: {
    label: "Very Likely",
    icon: <CheckCircle2 className="h-3 w-3" />,
    variant: "default",
    className: "bg-blue-600 hover:bg-blue-700 text-white cursor-pointer",
  },
  unsure: {
    label: "Unsure",
    icon: <HelpCircle className="h-3 w-3" />,
    variant: "outline",
    className: "bg-orange-500 hover:bg-orange-600 text-white border-orange-600 cursor-pointer",
  },
  not_match: {
    label: "Not Match",
    icon: <XCircle className="h-3 w-3" />,
    variant: "destructive",
    className: "bg-red-600 hover:bg-red-700 text-white cursor-pointer",
  },
};

export function StudyAIBadge({ classification, onClick }: StudyAIBadgeProps) {
  const config = classificationConfig[classification];

  return (
    <Badge
      variant={config.variant}
      className={`gap-1 ${config.className}`}
      onClick={onClick}
    >
      {config.icon}
      {config.label}
    </Badge>
  );
}
