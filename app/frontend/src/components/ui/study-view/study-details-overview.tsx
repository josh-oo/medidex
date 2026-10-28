import { StudyGraphBlock } from "@/components/ui/study-view/study-graph";
import { DetailRow } from "@/components/ui/study-view/detail-row";
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

/** The fields and the graph of a study as lines of the study details (rows of a `<dl>`). */
export function StudyOverview({ study, fields }: StudyOverviewProps) {
  const shown = fields.filter(
    (field) => (field.display === "metric" || field.display === "text") && fieldText(study, field)
  );

  return (
    <>
      {shown.map((field) => (
        <DetailRow key={field.key} icon={field.icon} label={field.label}>
          <span className={field.display === "metric" ? "font-medium" : "leading-relaxed"}>
            {fieldText(study, field)}
          </span>
        </DetailRow>
      ))}
      <StudyGraphBlock studyId={study.studyId} />
    </>
  );
}
