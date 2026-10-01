import type { ReactNode } from "react";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AppRoutes } from "./router";

export default function App({ extraRoutes }: { extraRoutes?: ReactNode } = {}) {
  return (
    <BrowserRouter>
      <AppRoutes extraRoutes={extraRoutes} />
      <Toaster />
    </BrowserRouter>
  );
}
