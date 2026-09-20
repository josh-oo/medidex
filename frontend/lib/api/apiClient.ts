import axios from "axios";

const baseUrl = process.env.MEERKAT_API_URL;

const API_BASE_URL = `${baseUrl}/api`;

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Add a request interceptor to handle FormData uploads
// When FormData is detected, remove Content-Type so axios can set it automatically with boundary
apiClient.interceptors.request.use((config) => {
  if (config.data instanceof FormData) {
    delete config.headers["Content-Type"];
  }
  return config;
});

export default apiClient;
