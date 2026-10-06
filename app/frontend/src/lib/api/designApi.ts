import { TagDto } from "../../types/apiDTOs";
import { listGetter } from "./requests";

export const getDesigns = listGetter<TagDto>("/design", "design items");
