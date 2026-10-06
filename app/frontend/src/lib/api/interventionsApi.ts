import { TagDto } from "../../types/apiDTOs";
import { listGetter } from "./requests";

export const getInterventions = listGetter<TagDto>("/interventions", "interventions");
