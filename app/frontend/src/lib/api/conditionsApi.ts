import { TagDto } from "../../types/apiDTOs";
import { listGetter } from "./requests";

export const getConditions = listGetter<TagDto>("/conditions", "conditions");
