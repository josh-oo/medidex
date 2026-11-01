import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
      // The legacy build of pdf.js (used by react-pdf) also runs on Safari, which lacks the async
      // iteration of ReadableStream that the modern build needs ("undefined is not a function").
      "pdfjs-dist$": path.resolve(import.meta.dirname, "node_modules/pdfjs-dist/legacy/build/pdf.mjs"),
    },
  },
  server: {
    port: 3000,
    host: true,
  },
});
