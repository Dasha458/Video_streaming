import * as React from "react"
import { cn } from "@/lib/utils"
import { toastVariants, type ToastProps } from "./toast-variants"

export { type ToastProps } from "./toast-variants"
export { type ToastActionElement } from "./toast-variants"

// `variant` and the store's bookkeeping fields are pulled out rather than
// spread: toastVariants() was previously called with no argument, so the
// destructive style never applied and React received `variant="destructive"`
// as an unknown DOM attribute on the div.
export const Toast = React.forwardRef<HTMLDivElement, ToastProps>(
    ({ className, variant, open: _open, onOpenChange: _onOpenChange, title: _title, description: _description, action: _action, ...props }, ref) => (
        <div ref={ref} className={cn(toastVariants({ variant }), className)} {...props} />
    )
)
Toast.displayName = "Toast"

export const ToastTitle = ({
    className,
    ...props
}: React.HTMLAttributes<HTMLHeadingElement>) => (
    <div className={cn("font-semibold", className)} {...props} />
)

export const ToastDescription = ({
    className,
    ...props
}: React.HTMLAttributes<HTMLParagraphElement>) => (
    <div className={cn("text-sm opacity-90", className)} {...props} />
)
