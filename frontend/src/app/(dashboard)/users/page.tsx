import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Users, UserPlus, MoreHorizontal, Mail, Shield } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const dummyUsers = [
  { id: 1, name: "Alex Chen", email: "alex.chen@example.com", role: "Super Admin", status: "Active", lastActive: "2 mins ago" },
  { id: 2, name: "Sarah Jenkins", email: "sarah.j@example.com", role: "Agent", status: "Active", lastActive: "1 hour ago" },
  { id: 3, name: "Marcus Thorne", email: "m.thorne@example.com", role: "Agent", status: "Offline", lastActive: "Yesterday" },
  { id: 4, name: "Elena Rodriguez", email: "elena.r@example.com", role: "Manager", status: "Active", lastActive: "15 mins ago" },
];

export default function UsersPage() {
  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-heading font-bold text-on-surface">User Management</h1>
          <p className="text-on-surface-variant mt-2">Manage agents and admins in your tenant.</p>
        </div>
        <Button className="bg-primary text-primary-foreground hover:bg-primary/90">
          <UserPlus className="w-4 h-4 mr-2" />
          Invite User
        </Button>
      </div>

      <Card className="border-none shadow-sm bg-white overflow-hidden">
        <CardHeader className="border-b border-outline-variant/10">
          <CardTitle className="text-lg">Active Users</CardTitle>
          <CardDescription>Users with access to this tenant's workspace.</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-surface-container-lowest text-[11px] font-bold text-on-surface-variant uppercase tracking-wider">
                  <th className="px-6 py-4">User</th>
                  <th className="px-6 py-4">Role</th>
                  <th className="px-6 py-4">Status</th>
                  <th className="px-6 py-4">Last Active</th>
                  <th className="px-6 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/10">
                {dummyUsers.map((user) => (
                  <tr key={user.id} className="hover:bg-surface-container-lowest transition-colors group">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-xs">
                          {user.name.split(' ').map(n => n[0]).join('')}
                        </div>
                        <div className="flex flex-col">
                          <span className="text-sm font-bold text-on-surface">{user.name}</span>
                          <span className="text-xs text-on-surface-variant flex items-center gap-1">
                            <Mail className="w-3 h-3" /> {user.email}
                          </span>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-1.5 text-sm text-on-surface">
                        <Shield className="w-3.5 h-3.5 text-on-surface-variant" />
                        {user.role}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <Badge 
                        variant="outline" 
                        className={cn(
                          "rounded-full px-2 py-0.5 text-[10px] font-bold border-none",
                          user.status === "Active" ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-600"
                        )}
                      >
                        {user.status}
                      </Badge>
                    </td>
                    <td className="px-6 py-4 text-sm text-on-surface-variant">
                      {user.lastActive}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <Button variant="ghost" size="icon" className="h-8 w-8 text-on-surface-variant opacity-0 group-hover:opacity-100 transition-opacity">
                        <MoreHorizontal className="w-4 h-4" />
                      </Button>
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
