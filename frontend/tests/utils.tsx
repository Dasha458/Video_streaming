import type { ReactElement, ReactNode } from "react";
import { render, renderHook, type RenderOptions } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/**
 * A QueryClient tuned for tests: no retries (a failing queryFn should fail
 * the test immediately, not after three back-offs) and no garbage-collection
 * delay between tests.
 */
export function createTestQueryClient() {
    return new QueryClient({
        defaultOptions: {
            queries: { retry: false, gcTime: 0 },
            mutations: { retry: false },
        },
    });
}

interface ProviderOptions {
    queryClient?: QueryClient;
    /** Initial URL for MemoryRouter, e.g. "/watch?v=abc". */
    route?: string;
}

function makeWrapper({ queryClient, route = "/" }: ProviderOptions) {
    const client = queryClient ?? createTestQueryClient();
    return function Wrapper({ children }: { children: ReactNode }) {
        return (
            <QueryClientProvider client={client}>
                <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
            </QueryClientProvider>
        );
    };
}

/** render() with the same providers the app has (React Query + router). */
export function renderWithProviders(
    ui: ReactElement,
    { queryClient, route, ...options }: ProviderOptions & Omit<RenderOptions, "wrapper"> = {},
) {
    return render(ui, { wrapper: makeWrapper({ queryClient, route }), ...options });
}

/** renderHook() with the same providers. */
export function renderHookWithProviders<T>(hook: () => T, opts: ProviderOptions = {}) {
    return renderHook(hook, { wrapper: makeWrapper(opts) });
}
