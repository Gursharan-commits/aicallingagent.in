"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LayoutDashboard, PhoneCall, Megaphone, MessageSquare, History, Settings, CreditCard, Users, ShieldAlert, GitMerge, LogOut } from "lucide-react";
import { cn } from "@/lib/utils";

const navigation = [
  { name: "Dashboard", href: "/", icon: LayoutDashboard },
  { name: "Active Calls", href: "/active-calls", icon: PhoneCall },
  { name: "Pipeline", href: "/pipeline", icon: GitMerge },
  { name: "Campaigns", href: "/campaigns", icon: Megaphone },
  { name: "Call Logs", href: "/call-logs", icon: History },
  { name: "Users", href: "/users", icon: Users, spacer: true },
  { name: "Settings", href: "/settings", icon: Settings },
  { name: "Superuser", href: "/superuser", icon: ShieldAlert, spacer: true },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  const handleLogout = () => {
    document.cookie = "access_token=; path=/; max-age=0";
    document.cookie = "refresh_token=; path=/; max-age=0";
    router.push("/login");
  };

  return (
    <div className="flex h-full w-64 flex-col bg-[#F9FAFB] border-r border-outline-variant/20 shrink-0">
      <div className="flex h-24 shrink-0 flex-col justify-center px-8">
        <span className="text-xl font-heading font-bold text-[#111827] tracking-tight">AI calling agent</span>
        <span className="text-[10px] font-bold text-on-surface-variant tracking-[0.2em] uppercase mt-1">Platform</span>
      </div>
      <div className="flex flex-1 flex-col overflow-y-auto py-4">
        <nav className="flex-1 space-y-1">
          {navigation.map((item, idx) => {
            const isActive = pathname === item.href;
            return (
              <div key={item.name}>
                {item.spacer && <div className="h-8" />}
                <Link
                  href={item.href}
                  className={cn(
                    "group flex items-center gap-4 px-8 py-3 text-sm font-medium transition-colors relative",
                    isActive 
                      ? "text-primary bg-white shadow-sm" 
                      : "text-on-surface-variant hover:bg-surface-container hover:text-on-surface"
                  )}
                >
                  {isActive && <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary rounded-r" />}
                  <item.icon className={cn("h-5 w-5 shrink-0", isActive ? "text-primary" : "text-on-surface-variant")} aria-hidden="true" />
                  {item.name}
                </Link>
              </div>
            );
          })}
        </nav>
      </div>
      
      <div className="p-6 border-t border-outline-variant/20 space-y-4">
        <div className="flex items-center gap-3">
          <img src="https://i.pravatar.cc/150?u=a042581f4e29026704d" alt="Alex Chen" className="w-10 h-10 rounded-full" />
          <div className="flex flex-col flex-1">
            <span className="text-sm font-bold text-on-surface">Alex Chen</span>
            <span className="text-xs text-on-surface-variant">Admin Level 4</span>
          </div>
        </div>
        <button 
          onClick={handleLogout}
          className="flex w-full items-center justify-center gap-2 rounded-md py-2 text-sm font-medium transition-colors text-error hover:bg-error/10 border border-error/20 bg-error/5"
        >
          <LogOut className="h-4 w-4" />
          Log Out
        </button>
      </div>
    </div>
  );
}

