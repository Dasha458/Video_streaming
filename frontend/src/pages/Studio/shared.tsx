import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { DeltaInt, Period } from "@/lib/api/analyticsApi";
import { PERIODS } from "./utils";

export function DeltaBadge({ d }: { d: DeltaInt }) {
    const up = d.delta_percent > 0;
    const flat = d.delta_percent === 0;
    const sign = up ? "+" : "";
    return (
        <span
            className={`text-xs font-medium ${
                flat ? "text-muted-foreground" : up ? "text-emerald-500" : "text-red-500"
            }`}
        >
            {sign}{d.delta_percent}%
        </span>
    );
}

export function StatCard({
    label, value, loading, delta,
}: {
    label: string;
    value: number | string;
    loading: boolean;
    delta?: DeltaInt;
}) {
    return (
        <Card>
            <CardHeader className="pb-1">
                <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <Skeleton className="h-8 w-24" />
                ) : (
                    <div className="flex items-baseline gap-2">
                        <p className="text-2xl font-bold">
                            {typeof value === "number" ? value.toLocaleString() : value}
                        </p>
                        {delta && <DeltaBadge d={delta} />}
                    </div>
                )}
            </CardContent>
        </Card>
    );
}

export function ChartSkeleton() {
    return <Skeleton className="h-[200px] w-full" />;
}

/** Card wrapper every chart on this page shares. */
export function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
    return (
        <Card>
            <CardHeader><CardTitle className="text-base">{title}</CardTitle></CardHeader>
            <CardContent>{children}</CardContent>
        </Card>
    );
}

export function EmptyState({ children }: { children: React.ReactNode }) {
    return <p className="text-sm text-muted-foreground text-center py-12">{children}</p>;
}

export function PeriodSelector({
    value, onChange,
}: { value: Period; onChange: (p: Period) => void }) {
    return (
        <select
            value={value}
            onChange={(e) => onChange(e.target.value as Period)}
            className="rounded-md border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            aria-label="Reporting period"
        >
            {PERIODS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
            ))}
        </select>
    );
}
