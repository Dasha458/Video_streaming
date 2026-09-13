import React, { useState, useEffect } from "react";
import { Search } from "lucide-react";
import { Label } from "@/components/ui/label";
import { SearchFiltersDialog } from "@/components/ui/searchFiltersDialog";
import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/popover";
import { useSearch } from "@/hooks/useSearch";

interface SearchFormProps {
    className?: string;
}

export function SearchForm({ className }: SearchFormProps) {
    const { searchQuery, setSearchQuery, runSearch, searchFilters, hints, loadHints, setHints } = useSearch();
    const [isFocused, setIsFocused] = useState(false);

    useEffect(() => {
        const id = setTimeout(() => {
            if (searchQuery.trim().length >= 1) loadHints(searchQuery);
            else setHints([]);
        }, 300);
        return () => clearTimeout(id);
    }, [searchQuery, loadHints, setHints]);

    const handleHintClick = (hint: string) => {
        setSearchQuery(hint);
        runSearch(hint, searchFilters);
        setHints([]);
        setIsFocused(false);
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === "Enter") {
            e.preventDefault();
            setHints([]);
            runSearch(searchQuery, searchFilters);
        }
    };

    const hintsOpen = isFocused && hints.length > 0;

    return (
        <Popover open={hintsOpen} onOpenChange={(open) => setIsFocused(open)}>
            <div className={`relative ${className || ""}`} role="search">
                <div className="flex h-10">
                    {/* Input */}
                    <PopoverAnchor asChild>
                        <div className="relative flex-1">
                            <Label htmlFor="search" className="sr-only">Search</Label>
                            <input
                                id="search"
                                type="text"
                                placeholder="Search"
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                onKeyDown={handleKeyDown}
                                onFocus={() => setIsFocused(true)}
                                autoComplete="off"
                                className="h-10 w-full rounded-l-full border border-border border-r-0 bg-background px-4 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 placeholder:text-muted-foreground"
                            />
                        </div>
                    </PopoverAnchor>

                    {/* Search button */}
                    <button
                        type="button"
                        onClick={() => { setHints([]); runSearch(searchQuery, searchFilters); }}
                        className="flex h-10 w-16 items-center justify-center rounded-r-full border border-border bg-muted hover:bg-muted/80 transition-colors"
                        aria-label="Search"
                    >
                        <Search className="h-4 w-4" />
                    </button>

                    {/* Filters */}
                    <div className="ml-2 flex items-center">
                        <SearchFiltersDialog />
                    </div>
                </div>

                {/* Hints dropdown */}
                <PopoverContent
                    align="start"
                    sideOffset={4}
                    onOpenAutoFocus={(e) => e.preventDefault()}
                    className="w-[var(--radix-popover-trigger-width)] p-0 rounded-xl shadow-lg overflow-hidden py-2"
                >
                    {hints.map((hint, i) => (
                        <button
                            key={i}
                            type="button"
                            onClick={() => handleHintClick(hint)}
                            className="w-full text-left px-4 py-2 text-sm hover:bg-muted flex items-center gap-3 transition-colors"
                        >
                            <Search className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                            <span className="truncate">{hint}</span>
                        </button>
                    ))}
                </PopoverContent>
            </div>
        </Popover>
    );
}
