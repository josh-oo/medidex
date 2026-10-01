import { BrowserRouter } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AppRoutes } from "./router";
import {
  ExtensionRegistryProvider,
  type ExtensionRegistry,
} from "./context/extension-registry-context";

export default function App({ extensions }: { extensions?: Partial<ExtensionRegistry> } = {}) {
  return (
    <ExtensionRegistryProvider extensions={extensions}>
      <BrowserRouter>
        <AppRoutes />
        <Toaster />
      </BrowserRouter>
    </ExtensionRegistryProvider>
  );
}
