import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Settings, Phone, Globe, Shield, Save, Volume2, Mic } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";

export default function SettingsPage() {
  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-heading font-bold text-on-surface">Tenant Settings</h1>
          <p className="text-on-surface-variant mt-2">Manage your organization's configurations and integrations.</p>
        </div>
        <Button className="bg-primary text-primary-foreground hover:bg-primary/90 gap-2">
          <Save className="w-4 h-4" />
          Save Changes
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <div className="space-y-8">
          <Card className="border-none shadow-sm bg-white">
            <CardHeader>
              <div className="w-10 h-10 rounded-full bg-blue-50 text-primary flex items-center justify-center mb-2">
                <Phone className="w-5 h-5" />
              </div>
              <CardTitle>Telephony Setup</CardTitle>
              <CardDescription>Configure SIP trunks and Twilio numbers.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="twilio-sid">Twilio Account SID</Label>
                <Input id="twilio-sid" placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" defaultValue="AC73f2a81b94d2e5c9a03f..." className="bg-surface-container-lowest" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="twilio-secret">Auth Token</Label>
                <Input id="twilio-secret" type="password" value="••••••••••••••••" className="bg-surface-container-lowest" readOnly />
              </div>
              <div className="flex items-center justify-between pt-2">
                <div className="space-y-0.5">
                  <Label>Call Recording</Label>
                  <p className="text-xs text-on-surface-variant">Automatically record all inbound sessions</p>
                </div>
                <Switch defaultChecked />
              </div>
            </CardContent>
          </Card>

          <Card className="border-none shadow-sm bg-white">
            <CardHeader>
              <div className="w-10 h-10 rounded-full bg-purple-50 text-purple-600 flex items-center justify-center mb-2">
                <Volume2 className="w-5 h-5" />
              </div>
              <CardTitle>Voice Synthesis</CardTitle>
              <CardDescription>Default TTS engine and latency optimization.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label>Default Provider</Label>
                <div className="grid grid-cols-2 gap-2">
                  <Button variant="outline" className="justify-start border-primary/20 bg-primary/5 text-primary">ElevenLabs (Fast)</Button>
                  <Button variant="outline" className="justify-start border-outline-variant/20">Azure Cognitive</Button>
                </div>
              </div>
              <div className="flex items-center justify-between pt-2">
                <div className="space-y-0.5">
                  <Label>Ultra-Low Latency</Label>
                  <p className="text-xs text-on-surface-variant">Reduces quality for faster response time</p>
                </div>
                <Switch />
              </div>
            </CardContent>
          </Card>
        </div>
        
        <div className="space-y-8">
          <Card className="border-none shadow-sm bg-white">
            <CardHeader>
              <div className="w-10 h-10 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center mb-2">
                <Globe className="w-5 h-5" />
              </div>
              <CardTitle>Regional Routing</CardTitle>
              <CardDescription>Set your primary data residency region.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="p-3 rounded-lg bg-surface-container-lowest border border-outline-variant/10 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-2 h-2 rounded-full bg-emerald-500" />
                  <span className="text-sm font-medium">India (Primary)</span>
                </div>
                <Badge variant="secondary" className="text-[10px] bg-emerald-50 text-emerald-700">Active</Badge>
              </div>
              <div className="p-3 rounded-lg bg-surface-container-lowest border border-outline-variant/10 flex items-center justify-between opacity-50">
                <div className="flex items-center gap-3">
                  <div className="w-2 h-2 rounded-full bg-gray-400" />
                  <span className="text-sm font-medium">United Kingdom</span>
                </div>
                <Button variant="ghost" size="sm" className="h-6 text-xs">Switch</Button>
              </div>
              <p className="text-xs text-on-surface-variant italic">Region affects data persistence and LLM endpoint selection.</p>
            </CardContent>
          </Card>

          <Card className="border-none shadow-sm bg-white">
            <CardHeader>
              <div className="w-10 h-10 rounded-full bg-orange-50 text-orange-600 flex items-center justify-center mb-2">
                <Mic className="w-5 h-5" />
              </div>
              <CardTitle>STT Sensitivity</CardTitle>
              <CardDescription>Voice activity detection thresholds.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <Label>Silence Timeout</Label>
                    <span className="text-xs font-mono text-on-surface-variant">800ms</span>
                  </div>
                  <div className="h-2 w-full bg-surface-container-low rounded-full">
                    <div className="h-full w-3/4 bg-primary rounded-full" />
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <Label>Interruption Logic</Label>
                    <span className="text-xs font-mono text-on-surface-variant">Aggressive</span>
                  </div>
                  <div className="h-2 w-full bg-surface-container-low rounded-full">
                    <div className="h-full w-1/2 bg-orange-500 rounded-full" />
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
