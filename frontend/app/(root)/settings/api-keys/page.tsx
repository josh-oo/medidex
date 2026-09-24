import { ApiKeysTable } from "./api-keys-table";
import { getMyApiKeys } from "./server";

export default async function ApiKeysPage() {
  const apiKeys = await getMyApiKeys();

  return (
    <div className="p-4 md:px-8 md:py-6">
      <h1 className="text-2xl font-bold">API Keys</h1>
      <p className="text-sm text-gray-500">
        Create API keys to call the Medidex backend from scripts (e.g. evaluation runs)
        without logging in interactively.
      </p>
      <div className="mt-4"></div>
      <ApiKeysTable initialApiKeys={apiKeys} />
    </div>
  );
}
