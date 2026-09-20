import { Role } from "../../enums/role.enum";

export interface UpdateUserDto {
  roles: Role[];
}