import { Layers, FileText, CheckCircle2, Sparkles } from "lucide-react";

interface QuickStatsProps {
  totalProjects: number;
  totalReports: number;
  totalAssigned: number;
  totalEmbedded: number;
}

export function QuickStats({
  totalProjects,
  totalReports,
  totalAssigned,
  totalEmbedded,
}: QuickStatsProps) {
  const assignmentRate = totalReports > 0
    ? Math.round((totalAssigned / totalReports) * 100)
    : 0;

  const stats = [
    {
      label: "Projects",
      value: totalProjects,
      icon: Layers,
      accent: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
    },
    {
      label: "Reports",
      value: totalReports,
      icon: FileText,
      accent: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
    },
    {
      label: "Studyfied",
      value: `${assignmentRate}%`,
      subtext: `${totalAssigned} of ${totalReports}`,
      icon: CheckCircle2,
      accent: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
    },
    {
      label: "Preprocessed",
      value: totalEmbedded,
      icon: Sparkles,
      accent: "bg-violet-500/10 text-violet-600 dark:text-violet-400",
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {stats.map((stat) => (
        <div
          key={stat.label}
          className="group relative bg-card border p-4 transition-all hover:border-primary/20 hover:shadow-sm"
        >
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                {stat.label}
              </p>
              <p className="text-2xl font-bold mt-1 tracking-tight">
                {stat.value}
              </p>
              {stat.subtext && (
                <p className="text-xs text-muted-foreground mt-0.5">
                  {stat.subtext}
                </p>
              )}
            </div>
            <div className={`p-2 rounded-lg ${stat.accent}`}>
              <stat.icon className="h-4 w-4" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
