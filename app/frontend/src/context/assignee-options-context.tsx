import { useExtensionRegistry } from "./extension-registry-context"

import type {
  AssigneeOption,
  AssigneeOptionsGroup,
  AssigneeOptionsResolver,
} from "./extension-registry-context"

export type {
  AssigneeOption,
  AssigneeOptionsGroup,
  AssigneeOptionsResolver,
} from "./extension-registry-context"

export function useAssigneeOptionsSlot(projectId: string): AssigneeOptionsGroup[] {
  const { assigneeOptions } = useExtensionRegistry()
  return assigneeOptions.flatMap((resolve) => resolve(projectId))
}
