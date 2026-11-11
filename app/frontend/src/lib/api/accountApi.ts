import apiClient from "./apiClient";

export interface OwnedDatabase {
  databaseId: number;
  name: string;
}

// A project the user is assigned to and has not handed in every report of.
export interface OpenTask {
  projectId: string;
  name: string;
  numberReportsUncommitted: number;
  numberReportsOpen: number;
}

// What stands in the way of deleting the account of the caller: the study databases they own (with their updates) and
// whether they are the only administrator block it; their open tasks they are only warned about.
export interface AccountDeletion {
  ownedDatabases: OwnedDatabase[];
  onlyAdmin: boolean;
  openTasks: OpenTask[];
}

export const getAccountDeletion = (): Promise<AccountDeletion> =>
  apiClient.get<AccountDeletion>("/users/me/deletion").then((response) => response.data);

export const deleteAccount = (): Promise<void> => apiClient.delete("/users/me").then(() => undefined);
