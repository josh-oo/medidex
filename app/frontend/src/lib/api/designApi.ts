import { DesignDto } from "../../types/apiDTOs";
import { listGetter } from "./requests";

export const getDesigns = listGetter<DesignDto>("/design", "design items");
