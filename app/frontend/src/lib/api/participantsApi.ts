import { ParticipantDto } from "../../types/apiDTOs";
import { listGetter } from "./requests";

export const getParticipants = listGetter<ParticipantDto>("/participants", "participants");
