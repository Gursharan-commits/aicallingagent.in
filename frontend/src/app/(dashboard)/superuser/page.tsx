import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ShieldAlert, Database, Server, Activity, Globe, Zap, List } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export default function SuperuserPage() {
  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-heading font-bold text-on-surface flex items-center">
            <ShieldAlert className="w-8 h-8 mr-3 text-error" />
            Superuser Panel
          </h1>
          <p className="text-on-surface-variant mt-2">Global platform overview across all multi-tenant regions.</p>
        </div>
        <Badge variant="outline" className="bg-error/10 text-error border-error/20 px-3 py-1 font-bold animate-pulse">
          Live System Monitor
        </Badge>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        {[
          { label: "Global Tenants", val: "142", icon: Globe, color: "text-blue-600", bg: "bg-blue-50" },
          { label: "Active Nodes", val: "18", icon: Server, color: "text-purple-600", bg: "bg-purple-50" },
          { label: "Avg Uptime", val: "99.98%", icon: Activity, color: "text-emerald-600", bg: "bg-emerald-50" },
          { label: "Total Revenue", val: "$42k", icon: Zap, color: "text-orange-600", bg: "bg-orange-50" },
        ].map((stat, i) => (
          <Card key={i} className="border-none shadow-sm bg-white">
            <CardContent className="p-6 flex items-center gap-4">
              <div className={`w-12 h-12 rounded-xl ${stat.bg} ${stat.color} flex items-center justify-center`}>
                <stat.icon className="w-6 h-6" />
              </div>
              <div>
                <p className="text-xs font-bold text-on-surface-variant uppercase tracking-wider">{stat.label}</p>
                <p className="text-2xl font-bold text-on-surface">{stat.val}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <Card className="border-none shadow-sm bg-white">
          <CardHeader className="border-b border-outline-variant/10">
            <CardTitle className="text-lg flex items-center gap-2">
              <Database className="w-5 h-5 text-primary" />
              Regional Databases
            </CardTitle>
          </CardHeader>
          <CardContent className="p-6 space-y-4">
            <div className="space-y-4">
              <div className="flex items-center justify-between p-4 rounded-xl bg-surface-container-lowest border border-outline-variant/10">
                <div className="flex flex-col">
                  <span className="text-sm font-bold">Region: India (IN)</span>
                  <span className="text-xs text-on-surface-variant">SQLite Shared Instance</span>
                </div>
                <Badge variant="secondary" className="bg-emerald-100 text-emerald-700">Healthy (45ms)</Badge>
              </div>
              <div className="flex items-center justify-between p-4 rounded-xl bg-surface-container-lowest border border-outline-variant/10">
                <div className="flex flex-col">
                  <span className="text-sm font-bold">Region: UK (Europe)</span>
                  <span className="text-xs text-on-surface-variant">SQLite High-Availability</span>
                </div>
                <Badge variant="secondary" className="bg-emerald-100 text-emerald-700">Healthy (62ms)</Badge>
              </div>
              <div className="flex items-center justify-between p-4 rounded-xl bg-surface-container-lowest border border-outline-variant/10 opacity-60">
                <div className="flex flex-col">
                  <span className="text-sm font-bold">Region: US East</span>
                  <span className="text-xs text-on-surface-variant">Postgres Migration Pending</span>
                </div>
                <Badge variant="secondary" className="bg-amber-100 text-amber-700">Standby</Badge>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-none shadow-sm bg-white">
          <CardHeader className="border-b border-outline-variant/10">
            <CardTitle className="text-lg flex items-center gap-2">
              <List className="w-5 h-5 text-primary" />
              Recent System Events
            </CardTitle>
          </CardHeader>
          <CardContent className="p-6">
            <div className="space-y-6">
              {[
                { event: "New Tenant Created", details: "Acme Corp (ID: 1042)", time: "2 min ago", color: "bg-blue-500" },
                { event: "Database Backup Complete", details: "Region: India", time: "1 hour ago", color: "bg-emerald-500" },
                { event: "High Traffic Alert", details: "Region: UK @ 450 req/s", time: "3 hours ago", color: "bg-orange-500" },
                { event: "Security Audit Scan", details: "0 vulnerabilities found", time: "5 hours ago", color: "bg-purple-500" },
              ].map((ev, i) => (
                <div key={i} className="flex gap-4 relative">
                  <div className={`w-1 h-8 rounded-full ${ev.color} mt-1`} />
                  <div className="flex flex-col flex-1">
                    <div className="flex justify-between items-center mb-0.5">
                      <span className="text-sm font-bold text-on-surface">{ev.event}</span>
                      <span className="text-[10px] text-on-surface-variant font-medium">{ev.time}</span>
                    </div>
                    <span className="text-xs text-on-surface-variant">{ev.details}</span>
                  </div>
                </div>
              ))}
            </div>
            <Button variant="ghost" className="w-full mt-6 text-primary hover:bg-primary/5 text-xs font-bold">View Global Logs</Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
