import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { History, Search, Download, Filter, PhoneIncoming, PhoneOutgoing, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const dummyLogs = [
  { id: 1, direction: "inbound", phone: "+91 98765 43210", agent: "Agent Alpha", duration: "4m 32s", status: "Resolved", time: "Oct 24, 11:42 AM" },
  { id: 2, direction: "outbound", phone: "+1 (555) 987-6543", agent: "Agent Delta", duration: "1m 15s", status: "No Answer", time: "Oct 24, 10:15 AM" },
  { id: 3, direction: "inbound", phone: "+44 20 7946 0958", agent: "Agent Alpha", duration: "8m 45s", status: "Escalated", time: "Oct 24, 09:30 AM" },
  { id: 4, direction: "outbound", phone: "+1 (555) 135-7924", agent: "Agent Gamma", duration: "3m 22s", status: "Resolved", time: "Oct 24, 08:05 AM" },
  { id: 5, direction: "inbound", phone: "+91 88888 77777", agent: "Agent Alpha", duration: "5m 10s", status: "Resolved", time: "Oct 23, 04:20 PM" },
  { id: 6, direction: "outbound", phone: "+1 (555) 555-1212", agent: "Agent Delta", duration: "0m 45s", status: "Voicemail", time: "Oct 23, 02:15 PM" },
  { id: 7, direction: "inbound", phone: "+44 7700 900077", agent: "Agent Gamma", duration: "12m 04s", status: "Resolved", time: "Oct 23, 11:00 AM" },
  { id: 8, direction: "outbound", phone: "+1 (555) 111-2222", agent: "Agent Alpha", duration: "2m 55s", status: "Resolved", time: "Oct 23, 09:45 AM" },
  { id: 9, direction: "inbound", phone: "+91 99999 11111", agent: "Agent Beta", duration: "6m 12s", status: "Resolved", time: "Oct 22, 06:15 PM" },
  { id: 10, direction: "outbound", phone: "+1 (555) 222-3333", agent: "Agent Delta", duration: "3m 50s", status: "Resolved", time: "Oct 22, 03:30 PM" },
  { id: 11, direction: "inbound", phone: "+44 20 1234 5678", agent: "Agent Alpha", duration: "1m 20s", status: "Dropped", time: "Oct 22, 01:20 PM" },
  { id: 12, direction: "outbound", phone: "+91 77777 66666", agent: "Agent Gamma", duration: "9m 40s", status: "Resolved", time: "Oct 22, 10:45 AM" },
  { id: 13, direction: "inbound", phone: "+1 (555) 444-5555", agent: "Agent Alpha", duration: "5m 25s", status: "Escalated", time: "Oct 21, 05:10 PM" },
  { id: 14, direction: "outbound", phone: "+44 7700 900123", agent: "Agent Beta", duration: "0m 30s", status: "No Answer", time: "Oct 21, 02:20 PM" },
  { id: 15, direction: "inbound", phone: "+91 88888 99999", agent: "Agent Gamma", duration: "7m 15s", status: "Resolved", time: "Oct 21, 11:30 AM" },
];

export default function CallLogsPage() {
  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-heading font-bold text-on-surface">Call Logs</h1>
          <p className="text-on-surface-variant mt-2">Historical record of all AI and human-assisted interactions.</p>
        </div>
        <Button variant="outline" className="bg-white border-outline-variant/20 gap-2">
          <Download className="w-4 h-4" />
          Export CSV
        </Button>
      </div>

      <div className="flex gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-on-surface-variant" />
          <Input className="pl-10 bg-white border-outline-variant/20" placeholder="Search by phone number or agent..." />
        </div>
        <Button variant="outline" className="bg-white border-outline-variant/20 gap-2">
          <Filter className="w-4 h-4" />
          More Filters
        </Button>
      </div>

      <Card className="border-none shadow-sm bg-white overflow-hidden">
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-surface-container-lowest text-[11px] font-bold text-on-surface-variant uppercase tracking-wider">
                  <th className="px-6 py-4">Direction</th>
                  <th className="px-6 py-4">Phone Number</th>
                  <th className="px-6 py-4">Agent</th>
                  <th className="px-6 py-4 text-right">Duration</th>
                  <th className="px-6 py-4">Status</th>
                  <th className="px-6 py-4">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/10">
                {dummyLogs.map((log) => (
                  <tr key={log.id} className="hover:bg-surface-container-lowest transition-colors cursor-pointer group">
                    <td className="px-6 py-4">
                      {log.direction === "inbound" ? (
                        <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
                          <PhoneIncoming className="w-4 h-4" />
                        </div>
                      ) : (
                        <div className="w-8 h-8 rounded-lg bg-purple-50 text-purple-600 flex items-center justify-center">
                          <PhoneOutgoing className="w-4 h-4" />
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <span className="text-sm font-bold text-on-surface">{log.phone}</span>
                    </td>
                    <td className="px-6 py-4">
                      <span className="text-sm text-on-surface-variant">{log.agent}</span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-1 text-xs text-on-surface-variant">
                        <Clock className="w-3 h-3" />
                        {log.duration}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <Badge 
                        variant="outline" 
                        className={cn(
                          "rounded-full px-2 py-0.5 text-[10px] font-bold border-none",
                          log.status === "Resolved" ? "bg-emerald-100 text-emerald-700" : 
                          log.status === "Escalated" ? "bg-red-100 text-red-700" : "bg-gray-100 text-gray-600"
                        )}
                      >
                        {log.status}
                      </Badge>
                    </td>
                    <td className="px-6 py-4 text-sm text-on-surface-variant">
                      {log.time}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
