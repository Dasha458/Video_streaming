import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, type AxiosResponse } from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LoginForm } from "../src/components/login-form";
import { renderWithProviders } from "./utils";

const login = vi.fn();
const navigate = vi.fn();
const toast = vi.fn();

vi.mock("@/contexts/AuthContext", () => ({
    useAuth: () => ({ login }),
}));

vi.mock("react-router-dom", async () => {
    const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
    return { ...actual, useNavigate: () => navigate };
});

vi.mock("@/components/ui/toast/use-toast", () => ({
    toast: (...args: unknown[]) => toast(...args),
}));

vi.mock("@api/authApi", () => ({
    getGithubAuthUrl: vi.fn(),
}));

describe("LoginForm", () => {
    beforeEach(() => vi.clearAllMocks());

    it("rejects an empty submit before calling the API", () => {
        renderWithProviders(<LoginForm />);

        // fireEvent.submit bypasses the browser's `required` check, which is
        // exactly the path the component's own guard covers.
        fireEvent.submit(screen.getByRole("button", { name: "Login" }).closest("form")!);

        expect(screen.getByText("All fields are required.")).toBeInTheDocument();
        expect(login).not.toHaveBeenCalled();
    });

    it("logs in, toasts and navigates home on success", async () => {
        login.mockResolvedValue(undefined);
        const user = userEvent.setup();
        renderWithProviders(<LoginForm />);

        await user.type(screen.getByLabelText("Email"), "a@b.com");
        await user.type(screen.getByLabelText("Password"), "secret123");
        await user.click(screen.getByRole("button", { name: "Login" }));

        await waitFor(() => expect(login).toHaveBeenCalledWith("a@b.com", "secret123"));
        expect(toast).toHaveBeenCalledWith({ title: "Login successful" });
        expect(navigate).toHaveBeenCalledWith("/");
    });

    it("shows the backend's message when login fails", async () => {
        login.mockRejectedValue(
            new AxiosError("bad", "400", undefined, undefined, {
                data: { code: "INVALID_CREDENTIALS", message: "Invalid credentials" },
            } as AxiosResponse),
        );
        const user = userEvent.setup();
        renderWithProviders(<LoginForm />);

        await user.type(screen.getByLabelText("Email"), "a@b.com");
        await user.type(screen.getByLabelText("Password"), "wrong");
        await user.click(screen.getByRole("button", { name: "Login" }));

        expect(await screen.findByText("Invalid credentials")).toBeInTheDocument();
        expect(navigate).not.toHaveBeenCalled();
    });
});
