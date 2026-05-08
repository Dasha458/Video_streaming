import axios, { type AxiosInstance, AxiosError } from "axios";

const apiClient: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "/",
  withCredentials: true,
});

apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
  },
  (error) => Promise.reject(error),
);

apiClient.interceptors.response.use(
  (res) => res,
  (error: AxiosError) => {
    // On 401, clear the stored token so AuthContext picks up the logged-out state.
    // Avoid redirecting on auth endpoints themselves (login/register).
    if (
      error.response?.status === 401 &&
      !error.config?.url?.includes("/auth")
    ) {
      localStorage.removeItem("token");
    }
    console.error("API error:", error.response?.data || error.message);
    return Promise.reject(error);
  },
);

export default apiClient;
