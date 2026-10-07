// The views of a study (`views` of config/study.yaml): parts of the study shown together as groups, e.g. a comparison
// of interventions ("Drug A vs Placebo"). Which views exist and how they look comes from the study schema.
import type { ReactNode } from "react";
import { useStudySchema } from "@/hooks/use-study-schema";
import { useStudyViews } from "@/hooks/use-study-views";
import { colorClasses } from "@/lib/colors";
import { iconByName } from "@/lib/icons";
import type { StudyViewDto, StudyViewSchemaDto, ViewPartDto } from "@/types/apiDTOs";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

// A part as text: its tags ("A + B") and, if it has any, the values kept with them ("5 days").
const partText = (part: ViewPartDto): string => {
  const tags = part.tags.map((tag) => tag.keyword).join(" + ");
  const values = Object.values(part.values).join(", ");
  return tags && values ? `${tags} (${values})` : tags || values;
};

// The groups of a view as text, each on one line ("A + B vs C"); an older study's plain text as it is.
export function viewText(schema: StudyViewSchemaDto, view: StudyViewDto | undefined): string {
  if (!view) return "";
  if (view.text) return view.text;
  return view.groups
    .map((group) => schema.parts.map((part) => partText(group[part.key] ?? { tags: [], values: {} })).filter(Boolean).join(schema.separator))
    .join("; ");
}

// The views of the study schema, with the groups of the study in each.
function useViews(studyId: number, select: (view: StudyViewSchemaDto) => boolean) {
  const { schema } = useStudySchema();
  const views = useStudyViews(studyId);
  return (schema?.views ?? []).filter(select).map((schemaView) => ({ schemaView, view: views?.[schemaView.key] }));
}

function Group({ schema, group }: { schema: StudyViewSchemaDto; group: Record<string, ViewPartDto> }) {
  const parts = schema.parts.filter((part) => partText(group[part.key] ?? { tags: [], values: {} }));
  return (
    <li className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
      {parts.map((part, index) => (
        <span key={part.key} className="flex flex-wrap items-center gap-x-2 gap-y-1">
          {index > 0 && (
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{schema.separator.trim() || "·"}</span>
          )}
          <span className="rounded-md bg-muted px-1.5 py-0.5 text-xs text-foreground">{partText(group[part.key])}</span>
        </span>
      ))}
    </li>
  );
}

// The views of a study in its details: a block per view with its groups, one per row. Views without content are left out.
export function StudyViewsBlock({ studyId }: { studyId: number }): ReactNode {
  const shown = useViews(studyId, () => true).filter(({ view }) => view && (view.text || view.groups.length > 0));
  return shown.map(({ schemaView, view }) => {
    const colors = colorClasses(schemaView.color);
    const Icon = iconByName(schemaView.icon);
    return (
      <div key={schemaView.key} className="space-y-2">
        <div className="flex items-center gap-2">
          <div className={`p-1 rounded ${colors.bg}`}>
            <Icon className={`h-3.5 w-3.5 ${colors.accent}`} />
          </div>
          <span className="text-sm font-medium">{schemaView.label}</span>
        </div>
        <div className="pl-6">
          {view?.text ? (
            <p className="text-sm text-muted-foreground leading-relaxed">{view.text}</p>
          ) : (
            <ul className="space-y-1.5">
              {view?.groups.map((group, index) => (
                <Group key={index} schema={schemaView} group={group} />
              ))}
            </ul>
          )}
        </div>
      </div>
    );
  });
}

// The views of a study that are shown on its card, one line each (e.g. "Drug A vs Placebo").
export function StudyCardViews({ studyId }: { studyId: number }): ReactNode {
  const shown = useViews(studyId, (view) => view.card)
    .map(({ schemaView, view }) => ({ schemaView, text: viewText(schemaView, view) }))
    .filter(({ text }) => text);
  return shown.map(({ schemaView, text }) => {
    const colors = colorClasses(schemaView.color);
    const Icon = iconByName(schemaView.icon);
    return (
      <div key={schemaView.key} className="flex items-center gap-1.5 text-muted-foreground flex-1 min-w-0 basis-0 max-w-full overflow-hidden">
        <div className={`p-0.5 rounded shrink-0 ${colors.bg}`}>
          <Icon className={`h-3 w-3 ${colors.accent}`} />
        </div>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="truncate block w-full max-w-full">{text}</span>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs">
              <p>{text}</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
    );
  });
}
