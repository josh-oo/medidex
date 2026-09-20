import { Role } from "../../enums/role.enum";

export interface UserDto {
  id: string;
  name: string;
  email: string;
  roles: Role[];
  isApproved: boolean;
}