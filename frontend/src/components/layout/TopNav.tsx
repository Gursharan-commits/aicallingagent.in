import { Bell, HelpCircle, Search } from "lucide-react";
import { Input } from "@/components/ui/input";

export function TopNav() {
  return (
    <header className="h-16 flex items-center justify-between px-8 bg-surface-container-lowest border-b border-outline-variant/20 shrink-0">
      <div className="flex flex-1 items-center max-w-md">
        <div className="relative w-full">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-on-surface-variant" />
          <Input 
            placeholder="Search active streams..." 
            className="w-full pl-9 bg-surface-container rounded-full border-none shadow-none text-sm placeholder:text-on-surface-variant focus-visible:ring-0 focus-visible:ring-offset-0 h-10"
          />
        </div>
      </div>
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2 text-sm font-semibold tracking-wider text-error">
          <div className="w-2 h-2 rounded-full bg-error animate-pulse" />
          LIVE: 24 CALLS
        </div>
        <div className="flex items-center gap-4 text-on-surface-variant">
          <button className="hover:text-on-surface transition-colors">
            <Bell className="h-5 w-5" />
          </button>
          <button className="hover:text-on-surface transition-colors">
            <HelpCircle className="h-5 w-5 fill-on-surface-variant text-surface-container-lowest" />
          </button>
        </div>
      </div>
    </header>
  );
}
