import { AxiosError } from "axios";

export function getApiErrorMessage(err: unknown, fallback = "Something went wrong"): string {
    if (err instanceof AxiosError && err.response?.data) {
        const data = err.response.data as { detail?: string; message?: string };
        return data.detail || data.message || fallback;
    }
    return fallback;
}
