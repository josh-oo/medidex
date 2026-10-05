import { TagDto } from "../../types/apiDTOs";
import { listGetter } from "./requests";

export const getOutcomes = listGetter<TagDto>("/outcomes", "outcomes");
