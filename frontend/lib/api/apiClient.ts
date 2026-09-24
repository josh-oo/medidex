"use client";

import axios from "axios";
import { getAccessToken } from "@/lib/client/keycloak";

// Public because this now runs entirely in the browser - there is no Next.js
// server hop between the app and the FastAPI backend anymore. The backend's
// CORS policy (allow_origins=["*"]) and its own JWT verification are the
// real security boundary, same as before.
const API_BASE_URL = `${process.env.NEXT_PUBLIC_BACKEND_API_URL}/api`;

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

apiClient.interceptors.request.use(async (config) => {
  if (config.data instanceof FormData) {
    delete config.headers["Content-Type"];
  }

  const token = await getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});

export default apiClient;
