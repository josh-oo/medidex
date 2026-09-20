"use client";

import { useState } from "react";
import Image from "next/image";
import { cn } from "@/lib/utils";
import {
  Upload,
  Search,
  Sparkles,
  FileText,
  CheckCircle2,
  LayoutDashboard,
  Settings2,
  Download,
  Users,
  Clock,
  Globe,
  ChevronRight,
} from "lucide-react";

interface Feature {
  id: string;
  title: string;
  description: string;
  icon: React.ElementType;
  image: string;
  highlights: string[];
}

const features: Feature[] = [
  {
    id: "dashboard",
    title: "Research Dashboard",
    description:
      "Get a bird's-eye view of your research progress with personalized stats and project overview.",
    icon: LayoutDashboard,
    image: "/images/showcase/hompage.png",
    highlights: [
      "Track total projects, reports, and assignment progress",
      "Quick access to all your research projects",
      "Visual progress indicators for each project",
      "Personalized greeting with motivational messages",
    ],
  },
  {
    id: "reports",
    title: "Report Management",
    description:
      "Browse, search, and filter through your reports with an intuitive interface.",
    icon: FileText,
    image: "/images/showcase/empty.png",
    highlights: [
      "Search reports by title, author, or content",
      "Filter by All, Assigned, or Unassigned status",
      "View report details including year and authors",
      "Download individual reports as PDFs",
    ],
  },
  {
    id: "ai-matching",
    title: "AI-Powered Study Matching",
    description:
      "Leverage advanced AI to automatically find relevant clinical studies for your reports.",
    icon: Sparkles,
    image: "/images/showcase/ai-settings.png",
    highlights: [
      "Choose from multiple AI models (GPT-5-mini and more)",
      "Option to include report PDFs for better matching",
      "Customizable prompts for background, evaluation, and comparison",
      "Step-by-step evaluation history and explanations",
    ],
  },
  {
    id: "relevant-studies",
    title: "Relevant Studies Discovery",
    description:
      "Discover studies ranked by relevance with detailed information at a glance.",
    icon: Search,
    image: "/images/showcase/relevant-studies.png",
    highlights: [
      "Color-coded relevance scores (high, medium, low)",
      "Participant count and study duration visible",
      "Comparison groups clearly displayed",
      "Quick search by name, ID, or comparison type",
    ],
  },
  {
    id: "study-assignment",
    title: "Study Assignment",
    description:
      "Assign relevant studies to reports with a single click and track your progress.",
    icon: CheckCircle2,
    image: "/images/showcase/study-assigned.png",
    highlights: [
      "One-click study assignment to reports",
      "Visual confirmation of successful assignment",
      "Assigned studies shown as badges on reports",
      "Track assignment progress across projects",
    ],
  },
  {
    id: "study-details",
    title: "Comprehensive Study Details",
    description:
      "Dive deep into study information with a comprehensive details panel.",
    icon: Globe,
    image: "/images/showcase/study-details.png",
    highlights: [
      "Study overview with open/closed status",
      "Participant count, duration, and countries",
      "Comparison groups and trial identifiers",
      "Timeline with entry and edit dates",
    ],
  },
  {
    id: "associated-reports",
    title: "Associated Reports",
    description:
      "View all reports connected to a study and download them individually or in bulk.",
    icon: Download,
    image: "/images/showcase/associated-reports.png",
    highlights: [
      "List of all reports linked to a study",
      "ID and title for each report",
      "Individual PDF download for each report",
      "Download All option for bulk export",
    ],
  },
  {
    id: "detailed-metadata",
    title: "Rich Study Metadata",
    description:
      "Access comprehensive study metadata including outcomes, interventions, and design.",
    icon: Settings2,
    image: "/images/showcase/study-details-2.png",
    highlights: [
      "Study outcomes with expandable details",
      "Study design classification",
      "Person/participant information",
      "Interventions breakdown",
    ],
  },
];

export function FeaturesShowcase() {
  const [activeFeature, setActiveFeature] = useState<string>(features[0].id);

  const currentFeature = features.find((f) => f.id === activeFeature)!;

  return (
    <section className="mt-16 mb-8">
      <div className="mb-8">
        <p className="text-sm font-medium text-primary mb-1 tracking-wide uppercase">
          How It Works
        </p>
        <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">
          Discover MediDex Features
        </h2>
        <p className="text-muted-foreground mt-2 max-w-2xl">
          From project creation to AI-powered study matching, explore how MediDex
          streamlines your medical research workflow.
        </p>
      </div>

      <div className="grid lg:grid-cols-[320px_1fr] gap-6">
        {/* Feature Navigation */}
        <div className="space-y-2">
          {features.map((feature) => {
            const Icon = feature.icon;
            const isActive = activeFeature === feature.id;

            return (
              <button
                key={feature.id}
                onClick={() => setActiveFeature(feature.id)}
                className={cn(
                  "w-full text-left p-3 border transition-all group flex items-start gap-3",
                  isActive
                    ? "bg-primary/5 border-primary/30 shadow-sm"
                    : "bg-card border-transparent hover:border-border hover:bg-muted/50"
                )}
              >
                <div
                  className={cn(
                    "p-2 rounded-lg shrink-0 transition-colors",
                    isActive
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground group-hover:bg-primary/10 group-hover:text-primary"
                  )}
                >
                  <Icon className="h-4 w-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <p
                    className={cn(
                      "font-medium text-sm leading-snug",
                      isActive ? "text-primary" : "text-foreground"
                    )}
                  >
                    {feature.title}
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                    {feature.description}
                  </p>
                </div>
                <ChevronRight
                  className={cn(
                    "h-4 w-4 shrink-0 mt-1 transition-transform",
                    isActive
                      ? "text-primary translate-x-0.5"
                      : "text-muted-foreground/50"
                  )}
                />
              </button>
            );
          })}
        </div>

        {/* Feature Preview */}
        <div className="space-y-4">
          {/* Image Preview */}
          <div className="bg-gradient-to-br from-muted/50 to-muted border overflow-hidden">
            <Image
              src={currentFeature.image}
              alt={currentFeature.title}
              width={1200}
              height={750}
              className="w-full h-auto"
              sizes="(max-width: 1024px) 100vw, 60vw"
            />
          </div>

          {/* Feature Highlights */}
          <div className="bg-card border p-5">
            <div className="flex items-center gap-2 mb-4">
              <currentFeature.icon className="h-5 w-5 text-primary" />
              <h3 className="font-semibold text-lg">{currentFeature.title}</h3>
            </div>
            <p className="text-muted-foreground mb-4">
              {currentFeature.description}
            </p>
            <div className="grid sm:grid-cols-2 gap-2">
              {currentFeature.highlights.map((highlight, index) => (
                <div
                  key={index}
                  className="flex items-start gap-2 text-sm"
                >
                  <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" />
                  <span>{highlight}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Quick Feature Pills */}
      <div className="mt-8 flex flex-wrap gap-3 justify-center">
        <FeaturePill icon={Upload} label="Project Creation" />
        <FeaturePill icon={Sparkles} label="AI Matching" />
        <FeaturePill icon={Search} label="Smart Search" />
        <FeaturePill icon={Download} label="PDF Export" />
        <FeaturePill icon={Users} label="User Management" />
        <FeaturePill icon={Clock} label="Progress Tracking" />
      </div>
    </section>
  );
}

function FeaturePill({
  icon: Icon,
  label,
}: {
  icon: React.ElementType;
  label: string;
}) {
  return (
    <div className="flex items-center gap-2 px-4 py-2 bg-muted/50 border text-sm text-muted-foreground">
      <Icon className="h-4 w-4" />
      <span>{label}</span>
    </div>
  );
}
