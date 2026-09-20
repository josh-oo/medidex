"use client";

import { StudyDto } from "@/types/apiDTOs";
import { Badge } from "@/components/ui/badge";
import { 
  FileText, 
  MapPin, 
  Users, 
  Clock, 
  Scale,
  Calendar,
  Hash,
} from "lucide-react";

interface StudyOverviewProps{
  study : StudyDto
}

const metricConfig = {
  participants: {
    icon: Users,
    label: "Participants",
    accentClass: "text-blue-600 dark:text-blue-400",
    bgClass: "bg-blue-50 dark:bg-blue-950/30",
    borderClass: "border-l-blue-500",
  },
  duration: {
    icon: Clock,
    label: "Duration",
    accentClass: "text-emerald-600 dark:text-emerald-400",
    bgClass: "bg-emerald-50 dark:bg-emerald-950/30",
    borderClass: "border-l-emerald-500",
  },
  countries: {
    icon: MapPin,
    label: "Countries",
    accentClass: "text-amber-600 dark:text-amber-400",
    bgClass: "bg-amber-50 dark:bg-amber-950/30",
    borderClass: "border-l-amber-500",
  },
};

export function StudyOverview({ study }: StudyOverviewProps) {
  const countries = study.countries.filter(Boolean);
  
  const statusVariant = {
    "Closed": "default" as const,
    "Stopped early": "destructive" as const,
    "Open/Ongoing": "default" as const,
    "Planned": "secondary" as const,
  }[study.status] || "secondary" as const;

  const hasTrialIds = study.trialId !== null;

  return (
    <div className="space-y-4 px-4">
      <div className="flex items-center justify-between gap-4">
        <h3 className="text-base font-semibold flex items-center gap-2.5">
            <div className="p-1.5 rounded-md bg-muted">
              <FileText className="h-4 w-4" />
            </div>
            Study Overview
        </h3>
        <div className="flex gap-2 flex-wrap justify-end">
          <Badge variant={statusVariant}>{study.status}</Badge>
        </div>
      </div>
      <div className="space-y-5">
        {/* Key metrics grid */}
        <div className="grid grid-cols-3 gap-3">
          <div className={`flex flex-col gap-1.5 p-3.5 rounded-md border-l-2 ${metricConfig.participants.borderClass} ${metricConfig.participants.bgClass}`}>
            <div className="flex items-center gap-2">
              <Users className={`h-4 w-4 ${metricConfig.participants.accentClass}`} />
              <span className="text-xs text-muted-foreground font-medium">Participants</span>
            </div>
            <p className="text-lg font-semibold">{study.numberParticipants || "-"}</p>
          </div>
          
          <div className={`flex flex-col gap-1.5 p-3.5 rounded-md border-l-2 ${metricConfig.duration.borderClass} ${metricConfig.duration.bgClass}`}>
            <div className="flex items-center gap-2">
              <Clock className={`h-4 w-4 ${metricConfig.duration.accentClass}`} />
              <span className="text-xs text-muted-foreground font-medium">Duration</span>
            </div>
            <p className="text-lg font-semibold">{study.duration || "-"}</p>
          </div>
          
          <div className={`flex flex-col gap-1.5 p-3.5 rounded-md border-l-2 ${metricConfig.countries.borderClass} ${metricConfig.countries.bgClass}`}>
            <div className="flex items-center gap-2">
              <MapPin className={`h-4 w-4 ${metricConfig.countries.accentClass}`} />
              <span className="text-xs text-muted-foreground font-medium">Countries</span>
            </div>
            <p className="text-lg font-semibold">{countries.length}</p>
          </div>
        </div>

        {/* Countries */}
        {countries.length > 0 && (
          <div className="space-y-2.5">
            <div className="flex items-center gap-2">
              <div className="p-1 rounded bg-amber-50 dark:bg-amber-950/30">
                <MapPin className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
              </div>
              <span className="text-sm font-medium">Study Countries</span>
            </div>
            <div className="flex flex-wrap gap-1.5 pl-6">
              {countries.map((country) => (
                <Badge key={country} variant="secondary" className="text-xs">
                  {country}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Comparison */}
        {study.comparison && (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="p-1 rounded bg-violet-50 dark:bg-violet-950/30">
                <Scale className="h-3.5 w-3.5 text-violet-600 dark:text-violet-400" />
              </div>
              <span className="text-sm font-medium">Comparison</span>
            </div>
            <p className="text-sm text-muted-foreground pl-6 leading-relaxed">{study.comparison}</p>
          </div>
        )}

        {/* Trial IDs */}
        {study.trialId !== null && (
          <div className="space-y-2.5">
            <div className="flex items-center gap-2">
              <div className="p-1 rounded bg-cyan-50 dark:bg-cyan-950/30">
                <Hash className="h-3.5 w-3.5 text-cyan-600 dark:text-cyan-400" />
              </div>
              <span className="text-sm font-medium">Trial Identifiers</span>
            </div>
            <div className="grid grid-cols-2 gap-2.5 pl-6">
              <div className="p-2.5 rounded-md bg-muted/50 border border-border/50">
                <code className="text-xs font-mono">{study.trialId}</code>
              </div>
            </div>
          </div>
        )}

        {/* Dates */}
        {(study.createdAt || study.updatedAt) && (
          <div className="space-y-2.5">
            <div className="flex items-center gap-2">
              <div className="p-1 rounded bg-slate-100 dark:bg-slate-800/50">
                <Calendar className="h-3.5 w-3.5 text-slate-600 dark:text-slate-400" />
              </div>
              <span className="text-sm font-medium">Timeline</span>
            </div>
            <div className="grid grid-cols-2 gap-2.5 pl-6">
              {study.createdAt && (
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-muted-foreground">Entered:</span>
                  <span className="font-medium">{new Date(study.createdAt).toLocaleDateString()}</span>
                </div>
              )}
              {study.updatedAt && (
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-muted-foreground">Edited:</span>
                  <span className="font-medium">{new Date(study.updatedAt).toLocaleDateString()}</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

