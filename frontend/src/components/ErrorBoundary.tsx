import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "@/components/ui/button";

interface Props {
    children: ReactNode;
    fallback?: ReactNode;
}

interface State {
    hasError: boolean;
    error: Error | null;
}

/**
 * React class-based Error Boundary.
 * Catches unhandled render/lifecycle errors in the subtree and shows a
 * recovery UI instead of a blank screen.
 *
 * Usage:
 *   <ErrorBoundary>
 *     <SomeComponent />
 *   </ErrorBoundary>
 */
export class ErrorBoundary extends Component<Props, State> {
    constructor(props: Props) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error: Error): State {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, info: ErrorInfo) {
        console.error("[ErrorBoundary] Caught error:", error, info.componentStack);
    }

    private handleReset = () => {
        this.setState({ hasError: false, error: null });
    };

    render() {
        if (this.state.hasError) {
            if (this.props.fallback) return this.props.fallback;

            return (
                <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4 p-8 text-center">
                    <h2 className="text-xl font-semibold text-destructive">
                        Something went wrong
                    </h2>
                    <p className="text-sm text-muted-foreground max-w-md">
                        {this.state.error?.message || "An unexpected error occurred."}
                    </p>
                    <div className="flex gap-3">
                        <Button variant="outline" onClick={this.handleReset}>
                            Try again
                        </Button>
                        <Button variant="default" onClick={() => (window.location.href = "/")}>
                            Go to home
                        </Button>
                    </div>
                </div>
            );
        }

        return this.props.children;
    }
}
