import { useState } from "react";
import CreateChannelGate from "@/components/CreateChannelGate";
import { Button } from "@/components/ui/button";
import type { Period } from "@/lib/api/analyticsApi";
import { PeriodSelector } from "./shared";
import { OverviewTab } from "./tabs/OverviewTab";
import { RealtimeTab } from "./tabs/RealtimeTab";
import { ContentTab } from "./tabs/ContentTab";
import { AudienceTab } from "./tabs/AudienceTab";
import { EngagementTab } from "./tabs/EngagementTab";
import { TrafficTab } from "./tabs/TrafficTab";

type Tab = "overview" | "content" | "audience" | "engagement" | "realtime" | "traffic";

const TABS: { id: Tab; label: string }[] = [
    { id: "overview",   label: "Overview" },
    { id: "realtime",   label: "Real-time" },
    { id: "content",    label: "Content" },
    { id: "audience",   label: "Audience" },
    { id: "engagement", label: "Engagement" },
    { id: "traffic",    label: "Traffic sources" },
];

export default function Studio() {
    const [activeTab, setActiveTab] = useState<Tab>("overview");
    const [period, setPeriod] = useState<Period>("28d");

    return (
        <CreateChannelGate>
            <div className="px-4 py-6 space-y-6">
                <div className="flex flex-wrap items-center justify-between gap-3">
                    <h1 className="text-2xl font-bold">Creator Studio</h1>
                    {activeTab !== "realtime" && (
                        <PeriodSelector value={period} onChange={setPeriod} />
                    )}
                </div>

                <div className="flex gap-1 border-b overflow-x-auto">
                    {TABS.map((t) => (
                        <Button
                            key={t.id}
                            variant="ghost"
                            size="sm"
                            onClick={() => setActiveTab(t.id)}
                            className={`rounded-none border-b-2 px-4 whitespace-nowrap ${
                                activeTab === t.id
                                    ? "border-primary text-foreground font-medium"
                                    : "border-transparent text-muted-foreground"
                            }`}
                        >
                            {t.label}
                        </Button>
                    ))}
                </div>

                {activeTab === "overview"   && <OverviewTab period={period} />}
                {activeTab === "realtime"   && <RealtimeTab />}
                {activeTab === "content"    && <ContentTab period={period} />}
                {activeTab === "audience"   && <AudienceTab period={period} />}
                {activeTab === "engagement" && <EngagementTab period={period} />}
                {activeTab === "traffic"    && <TrafficTab period={period} />}
            </div>
        </CreateChannelGate>
    );
}
