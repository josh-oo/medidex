"use server";

import { getBackendHeaders } from "../../../../lib/server/backendHeaders";
import * as apiKeysApi from "../../../../lib/api/apiKeysApi";

export async function getMyApiKeys(): Promise<string[]> {
  return apiKeysApi.listApiKeys({ headers: await getBackendHeaders() });
}

export async function createMyApiKey(): Promise<string> {
  return apiKeysApi.createApiKey({ headers: await getBackendHeaders() });
}

export async function deleteMyApiKey(keyId: string): Promise<void> {
  await apiKeysApi.deleteApiKey(keyId, { headers: await getBackendHeaders() });
}
