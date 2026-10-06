import { FileText } from "lucide-react";
import { colorClasses } from "@/lib/colors";
import { iconByName } from "@/lib/icons";
import type { StudyDto, StudyFieldSchemaDto } from "@/types/apiDTOs";

interface StudyOverviewProps {
  study: StudyDto;
  // The primitive fields of the study (the `fields` of the study schema).
  fields: StudyFieldSchemaDto[];
}

// The value of a field of the study as text; empty when the study has none.
const fieldText = (study: StudyDto, field: StudyFieldSchemaDto): string => {
  const value = study[field.key];
  return value === null || value === undefined ? "" : String(value);
};

function MetricValue({ study, field }: { study: StudyDto; field: StudyFieldSchemaDto }) {
  return <p className="text-lg font-semibold">{fieldText(study, field) || "-"}</p>;
}

export function StudyOverview({ study, fields }: StudyOverviewProps) {
  const metrics = fields.filter((field) => field.display === "metric");
  const texts = fields.filter((field) => field.display === "text" && fieldText(study, field));

  return (
    <div className="space-y-4 px-4">
      <h3 className="text-base font-semibold flex items-center gap-2.5">
        <div className="p-1.5 rounded-md bg-muted">
          <FileText className="h-4 w-4" />
        </div>
        Study Overview
      </h3>
      <div className="space-y-5">
        {metrics.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {metrics.map((field) => {
              const colors = colorClasses(field.color);
              const Icon = iconByName(field.icon);
              return (
                <div
                  key={field.key}
                  className={`flex flex-col gap-1.5 p-3.5 rounded-md border-l-2 ${colors.border} ${colors.bg}`}
                >
                  <div className="flex items-center gap-2">
                    <Icon className={`h-4 w-4 ${colors.accent}`} />
                    <span className="text-xs text-muted-foreground font-medium">{field.label}</span>
                  </div>
                  <MetricValue study={study} field={field} />
                </div>
              );
            })}
          </div>
        )}

        {texts.map((field) => {
          const colors = colorClasses(field.color);
          const Icon = iconByName(field.icon);
          return (
            <div key={field.key} className="space-y-2">
              <div className="flex items-center gap-2">
                <div className={`p-1 rounded ${colors.bg}`}>
                  <Icon className={`h-3.5 w-3.5 ${colors.accent}`} />
                </div>
                <span className="text-sm font-medium">{field.label}</span>
              </div>
              <p className="text-sm text-muted-foreground pl-6 leading-relaxed">{fieldText(study, field)}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
