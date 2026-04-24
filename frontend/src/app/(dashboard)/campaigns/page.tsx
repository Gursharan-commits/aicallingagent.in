import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Megaphone, Plus, Search, Calendar, Users, Target } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const dummyCampaigns = [
  { id: 1, name: "Summer Retention 2024", type: "Outbound", status: "Running", progress: 65, calls: "1,240 / 2,000", conversion: "12%" },
  { id: 2, name: "Cold Lead Reactivation", type: "Outbound", status: "Paused", progress: 32, calls: "450 / 1,400", conversion: "8%" },
  { id: 3, name: "Inbound Support Flow", type: "Inbound", status: "Active", progress: 100, calls: "Ongoing", conversion: "94%" },
  { id: 4, name: "New Product Survey", type: "Outbound", status: "Running", progress: 88, calls: "4,400 / 5,000", conversion: "22%" },
  { id: 5, name: "Late Payment Reminders", type: "Outbound", status: "Active", progress: 15, calls: "300 / 2,000", conversion: "45%" },
  { id: 6, name: "VIP Priority Support", type: "Inbound", status: "Active", progress: 100, calls: "Ongoing", conversion: "98%" },
];

export default function CampaignsPage() {
  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-heading font-bold text-on-surface">Campaigns</h1>
          <p className="text-on-surface-variant mt-2">Design and monitor your automated calling workflows.</p>
        </div>
        <Button className="bg-primary text-primary-foreground hover:bg-primary/90">
          <Plus className="w-4 h-4 mr-2" />
          New Campaign
        </Button>
      </div>

      <div className="flex gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-on-surface-variant" />
          <Input className="pl-10 bg-white border-outline-variant/20" placeholder="Search campaigns..." />
        </div>
        <Button variant="outline" className="bg-white border-outline-variant/20">Filter</Button>
      </div>

      <div className="grid grid-cols-1 gap-4">
        {dummyCampaigns.map((camp) => (
          <Card key={camp.id} className="border-none shadow-sm bg-white hover:shadow-md transition-shadow cursor-pointer overflow-hidden group">
            <CardContent className="p-0">
              <div className="flex items-center p-6">
                <div className="w-12 h-12 rounded-xl bg-primary/10 text-primary flex items-center justify-center mr-6">
                  <Megaphone className="w-6 h-6" />
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-1">
                    <h3 className="font-bold text-on-surface">{camp.name}</h3>
                    <Badge variant="outline" className="text-[10px] uppercase font-bold tracking-wider">{camp.type}</Badge>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-on-surface-variant">
                    <span className="flex items-center gap-1"><Users className="w-3 h-3" /> {camp.calls}</span>
                    <span className="flex items-center gap-1"><Target className="w-3 h-3" /> {camp.conversion} success</span>
                  </div>
                </div>
                <div className="flex flex-col items-end gap-2">
                  <Badge 
                    className={cn(
                      "px-2 py-0.5 text-[10px] font-bold border-none",
                      camp.status === "Running" ? "bg-blue-100 text-blue-700" : 
                      camp.status === "Active" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"
                    )}
                  >
                    {camp.status}
                  </Badge>
                  <span className="text-xs font-medium text-on-surface-variant">{camp.progress}%</span>
                </div>
              </div>
              <div className="h-1 w-full bg-surface-container-low">
                <div className={`h-full ${camp.status === 'Paused' ? 'bg-amber-500' : 'bg-primary'} transition-all duration-500`} style={{ width: `${camp.progress}%` }} />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
