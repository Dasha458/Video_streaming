import axios, { type AxiosInstance, AxiosError } from "axios";

// The session lives in an httpOnly cookie set by the backend; the browser
// attaches it because of withCredentials. There is deliberately no
// Authorization header and no token in JavaScript-readable storage.
const apiClient: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "/",
  withCredentials: true,
});

apiClient.interceptors.response.use(
  (res) => res,
  (error: AxiosError) => {
    const status = error.response?.status;

    // Only log unexpected server errors (5xx) or genuine network failures.
    // 4xx errors are expected and handled by the calling code — no need to pollute the console.
    if (!status || status >= 500) {
      console.error("API error:", error.response?.data || error.message);
    }

    return Promise.reject(error);
  },
);

export default apiClient;
