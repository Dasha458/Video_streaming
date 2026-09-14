import { QueryClient } from "@tanstack/react-query";

/**
 * One shared cache for the whole app.
 *
 * staleTime keeps navigating back to a page you just left from refetching
 * everything again -- the old hand-rolled hooks refetched from scratch on
 * every mount, which is what made Home/Channel/Studio feel like they
 * reloaded constantly.
 */
export const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            staleTime: 60_000,
            gcTime: 5 * 60_000,
            retry: 1,
            refetchOnWindowFocus: false,
        },
    },
});
