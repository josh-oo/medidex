import { useEffect, useState } from "react";
import { ApiKeysTable } from "./api-keys-table";
import { listApiKeys } from "@/lib/api/apiKeysApi";
import { Spinner } from "@/components/ui/spinner";

export default function ApiKeysPage() {
  const [apiKeys, setApiKeys] = useState<string[] | null>(null);

  useEffect(() => {
    listApiKeys()
      .then(setApiKeys)
      .catch((error) => {
        console.error("Failed to fetch API keys:", error);
        setApiKeys([]);
      });
  }, []);

  return (
    <div className="p-4 md:px-8 md:py-6">
      <h1 className="text-2xl font-bold">API Keys</h1>
      <p className="text-sm text-gray-500">
        Create API keys to call the Medidex backend from scripts (e.g. evaluation runs)
        without logging in interactively.
      </p>
      <div className="mt-4"></div>
      {apiKeys === null ? (
        <div className="flex justify-center py-10">
          <Spinner className="h-6 w-6" />
        </div>
      ) : (
        <ApiKeysTable initialApiKeys={apiKeys} />
      )}
    </div>
  );
}
