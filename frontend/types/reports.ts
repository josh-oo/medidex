import { StudyDto } from "./apiDTOs";

export interface RelevanceStudy {
  isLinked: boolean;
  relevance: number;
  study: StudyDto;
}
