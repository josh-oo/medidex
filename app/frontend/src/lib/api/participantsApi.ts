import { TagDto } from "../../types/apiDTOs";
import { listGetter } from "./requests";

export const getParticipants = listGetter<TagDto>("/participants", "participants");
