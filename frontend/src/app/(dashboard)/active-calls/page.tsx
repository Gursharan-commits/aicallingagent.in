"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { Volume2, PhoneOff, User, ShieldAlert, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { AgentAudioVisualizerBar } from "@/components/agents-ui/agent-audio-visualizer-bar";
import { cn } from "@/lib/utils";
import { useCallStore } from "@/store/useCallStore";

export default function ActiveCalls() {
  const { calls, connectWebSocket, disconnectWebSocket, takeoverCall } = useCallStore();
  const [selectedCallId, setSelectedCallId] = useState<string | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /** Format elapsed seconds into MM:SS */
  const formatDuration = useCallback((secs: number) => {
    const m = Math.floor(secs / 60).toString().padStart(2, "0");
    const s = (secs % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  }, []);

  useEffect(() => {
    // Seed demo calls so the UI renders without a live backend.
    const demoCalls = [
      {
        id: "call_alpha_123",
        tenant: "default",
        agent: "Agent Alpha",
        state: "listening",
        phone: "+1 555-0102",
        duration: "02:14",
        transcript: [
          { role: "agent", text: "Hello Sarah, I've pulled up your account. I see you're calling about the intermittent fiber connection in the Austin area. Is that correct?", timestamp: Date.now() - 60_000 },
          { role: "user", text: "Yes, it's been dropping every 20 minutes since the storm last night. I'm working from home and it's quite frustrating.", timestamp: Date.now() - 40_000 },
          { role: "agent", text: "I completely understand the frustration, especially while working. I'm running a remote diagnostic on your ONT box right now. Just a moment...", timestamp: Date.now() - 20_000 },
        ],
      },
      {
        id: "call_delta_456",
        tenant: "default",
        agent: "Agent Delta",
        state: "speaking",
        phone: "+1 555-0199",
        duration: "01:45",
        transcript: [
          { role: "user", text: "I need to upgrade my plan to the 2GB fiber. My current 1GB isn't enough for the new server I set up.", timestamp: Date.now() - 30_000 },
          { role: "agent", text: "That sounds like a great upgrade! I can certainly help you with that. The 2GB plan also includes our premium hardware suite. Would you like me to process that now?", timestamp: Date.now() - 10_000 },
        ],
      },
      {
        id: "call_gamma_789",
        tenant: "default",
        agent: "Agent Gamma",
        state: "listening",
        phone: "+1 555-0244",
        duration: "08:22",
        transcript: [
          { role: "agent", text: "I see the payment was declined by your bank. Have you recently received a new card?", timestamp: Date.now() - 120_000 },
          { role: "user", text: "Oh, you're right! I forgot to update it in the portal. Can I do it over the phone with you?", timestamp: Date.now() - 90_000 },
        ],
      }
    ];

    demoCalls.forEach(call => useCallStore.getState().upsertCall(call));
    setSelectedCallId("call_alpha_123");

    // Live call timer
    timerRef.current = setInterval(() => setElapsedSec((s) => s + 1), 1000);

    // WebSocket — read from env in production, fall back to dev default.
    const wsHost = process.env.NEXT_PUBLIC_WS_HOST ?? "localhost:8000";
    connectWebSocket(`ws://${wsHost}/ws/calls/call_alpha_123/`);

    return () => {
      disconnectWebSocket();
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [connectWebSocket, disconnectWebSocket]);

  const activeCall = selectedCallId ? calls[selectedCallId] : null;
  const isActive = activeCall?.state !== "idle";

  return (
    <div className="flex h-full w-full bg-[#FAFAFA] text-on-surface overflow-hidden">
      {/* LEFT COLUMN: Queue Monitor */}
      <div className="w-[340px] shrink-0 border-r border-outline-variant/20 p-6 flex flex-col overflow-y-auto">
        <h2 className="text-xl font-heading font-bold">Queue Monitor</h2>
        <p className="text-sm text-on-surface-variant mb-6">Real-time status of current AI interactions</p>

        <div className="flex flex-col gap-4">
          {Object.values(calls).map((call) => (
            <div 
              key={call.id}
              onClick={() => setSelectedCallId(call.id)}
              className={cn(
                "relative bg-white rounded-xl p-4 shadow-sm border transition-all cursor-pointer group",
                selectedCallId === call.id ? "border-primary/40 ring-1 ring-primary/10" : "border-outline-variant/10 hover:bg-surface-container"
              )}
            >
              {selectedCallId === call.id && <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary rounded-l-xl" />}
              <div className="flex items-center justify-between mb-2">
                <Badge 
                  variant="secondary" 
                  className={cn(
                    "rounded-sm text-[10px] uppercase font-bold tracking-wider px-2 py-0.5",
                    call.state === "listening" ? "bg-blue-100 text-blue-700" :
                    call.state === "speaking" ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-700"
                  )}
                >
                  {call.state}
                </Badge>
                <span className="text-xs font-mono tabular-nums text-on-surface-variant">
                  {call.duration}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <div className={cn(
                  "w-10 h-10 rounded-full flex items-center justify-center shrink-0",
                  selectedCallId === call.id ? "bg-primary/10 text-primary" : "bg-gray-100 text-gray-500"
                )}>
                  <User className="w-5 h-5" />
                </div>
                <div className="flex flex-col">
                  <span className="font-bold text-sm">
                    {call.id === "call_alpha_123" ? "Sarah Jenkins" : 
                     call.id === "call_delta_456" ? "Marcus Thorne" : 
                     call.id === "call_gamma_789" ? "Elena Rodriguez" : "Anonymous User"}
                  </span>
                  <span className="text-xs text-on-surface-variant">
                    {call.id === "call_alpha_123" ? "Inbound: Tech Support" : 
                     call.id === "call_delta_456" ? "Outbound: Follow-up" : 
                     call.id === "call_gamma_789" ? "Inbound: Billing Query" : "General Inquiry"}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* MIDDLE COLUMN: Live Stream */}
      <div className="flex-1 flex flex-col bg-[#F3F4F6]">
        {/* Header */}
        <div className="flex items-center justify-between p-6 shrink-0 border-b border-outline-variant/10">
          <div>
            <h2 className="text-xl font-heading font-bold text-on-surface">
              Live Stream: {activeCall?.agent ?? "Agent Alpha"}
            </h2>
            <p className="text-sm text-on-surface-variant">
              {activeCall?.state === "idle" ? (
                <span className="text-amber-500 font-medium">● Human Operator Active</span>
              ) : "Processing with GPT-4 Voice Engine"}
            </p>
          </div>
        </div>

        {/* Chat Transcript */}
        <div className="flex-1 overflow-y-auto px-12 py-6 space-y-6">
          {activeCall?.transcript.map((msg, idx) => (
            msg.role === "agent" ? (
              <div key={idx} className="flex flex-col max-w-[80%]">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[10px] font-bold text-primary tracking-wider uppercase">{activeCall.agent}</span>
                  <span className="text-[10px] text-on-surface-variant">
                    {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  </span>
                </div>
                <div className="bg-[#E5E7EB] rounded-2xl rounded-tl-sm p-4 text-sm text-[#1F2937] leading-relaxed">
                  {msg.text}
                </div>
              </div>
            ) : (
              <div key={idx} className="flex flex-col items-end w-full">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[10px] text-on-surface-variant">
                    {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  </span>
                  <span className="text-[10px] font-bold text-[#1F2937] tracking-wider uppercase">User</span>
                </div>
                <div className="bg-white shadow-sm rounded-2xl rounded-tr-sm p-4 text-sm text-[#1F2937] leading-relaxed max-w-[80%]">
                  {msg.text}
                </div>
              </div>
            )
          ))}

          {/* Transcribing Indicator - if state is listening */}
          {activeCall?.state === "listening" && (
            <div className="flex flex-col items-end w-full">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-[10px] text-on-surface-variant italic">Transcribing live...</span>
                <span className="text-[10px] font-bold text-[#1F2937] tracking-wider uppercase">User</span>
              </div>
              <div className="bg-white/60 shadow-sm rounded-2xl rounded-tr-sm p-4 text-sm text-[#9CA3AF] leading-relaxed max-w-[80%] italic">
                ...
              </div>
            </div>
          )}
        </div>

        {/* Suggested Responses + Human Takeover */}
        <div className="p-6 shrink-0 bg-[#F3F4F6] border-t border-outline-variant/10">
          <p className="text-[10px] font-bold text-on-surface-variant uppercase tracking-wider mb-3">AI Suggested Responses</p>
          <div className="flex gap-3">
            <Button variant="outline" className="flex-1 bg-white border-outline-variant/20 hover:bg-primary/5 hover:text-primary hover:border-primary/30 h-auto py-3 whitespace-normal text-left justify-start items-start text-xs shadow-sm">
              Suggest Router<br/>Reboot
            </Button>
            <Button variant="outline" className="flex-1 bg-white border-outline-variant/20 hover:bg-primary/5 hover:text-primary hover:border-primary/30 h-auto py-3 whitespace-normal text-left justify-start items-start text-xs shadow-sm">
              Offer Billing<br/>Credit
            </Button>
            <Button
              variant="outline"
              disabled={!isActive}
              className={cn(
                "flex-1 h-auto py-3 whitespace-normal text-left justify-start items-start text-xs shadow-sm",
                isActive
                  ? "bg-red-50 border-red-200 text-red-700 hover:bg-red-100 hover:border-red-300"
                  : "bg-white border-outline-variant/20 opacity-50 cursor-not-allowed"
              )}
              onClick={() => selectedCallId && takeoverCall(selectedCallId)}
            >
              <ShieldAlert className="w-3.5 h-3.5 mr-1.5 shrink-0" />
              {isActive ? <>Escalate to<br/>Human</> : "Human Active"}
            </Button>
          </div>
        </div>
      </div>

      {/* RIGHT COLUMN: User Info */}
      <div className="w-[340px] shrink-0 bg-white border-l border-outline-variant/20 flex flex-col overflow-y-auto">
        {/* Active Call Controls */}
        <div className="p-6 border-b border-outline-variant/10 flex flex-col items-center bg-blue-50/50">
          <div className="w-full flex items-center justify-between mb-4">
             <span className="text-sm font-heading font-bold text-on-surface">Active Call</span>
             <div className="flex gap-2">
                <Button variant="outline" size="icon" className="rounded-full bg-white border-none shadow-sm text-primary hover:bg-primary/5 h-8 w-8">
                  <Volume2 className="h-4 w-4" />
                </Button>
                <Button variant="outline" size="icon" className="rounded-full bg-white border-none shadow-sm text-error hover:bg-error/5 h-8 w-8">
                  <PhoneOff className="h-4 w-4" />
                </Button>
             </div>
          </div>
          <div className="h-20 flex items-center justify-center shrink-0 w-full bg-white rounded-lg border border-outline-variant/10 shadow-inner">
            <AgentAudioVisualizerBar state="listening" size="sm" color="#3B82F6" />
          </div>
        </div>

        <div className="p-8 flex flex-col items-center border-b border-outline-variant/10">
          <div className="relative mb-4">
            {/* Real mockup has an avatar, we use an image */}
            <img src="https://i.pravatar.cc/150?u=sarahjenkins" alt="Sarah Jenkins" className="w-24 h-24 rounded-2xl object-cover shadow-sm" />
            <div className="absolute -bottom-1.5 -right-1.5 w-4 h-4 bg-green-500 border-2 border-white rounded-full"></div>
          </div>
          <h2 className="text-xl font-heading font-bold mb-1">Sarah Jenkins</h2>
          <p className="text-sm text-on-surface-variant mb-4">Premium Residential Tier</p>
          
          <div className="flex gap-2">
            <Badge variant="secondary" className="bg-[#374151] text-white hover:bg-[#374151] border-none shadow-none text-[10px] px-2">Customer since 2019</Badge>
            <Badge variant="secondary" className="bg-cyan-100 text-cyan-700 hover:bg-cyan-100 border-none shadow-none text-[10px] px-2">LTV: $4.2k</Badge>
          </div>
        </div>

        <div className="p-6 flex gap-4 border-b border-outline-variant/10">
          <div className="flex-1 bg-[#F9FAFB] p-3 rounded-lg flex flex-col">
            <span className="text-[10px] font-bold text-on-surface-variant uppercase tracking-wider mb-1">Location</span>
            <span className="text-sm font-bold">Austin, TX</span>
          </div>
          <div className="flex-1 bg-[#F9FAFB] p-3 rounded-lg flex flex-col">
            <span className="text-[10px] font-bold text-on-surface-variant uppercase tracking-wider mb-1">Local Time</span>
            <span className="text-sm font-bold">10:04 AM</span>
          </div>
        </div>

        <div className="p-6 border-b border-outline-variant/10">
          <span className="text-[10px] font-bold text-on-surface-variant uppercase tracking-wider mb-3 block">Services</span>
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline" className="bg-white border-outline-variant/30 text-xs font-normal">Fiber 1G</Badge>
            <Badge variant="outline" className="bg-white border-outline-variant/30 text-xs font-normal">Smart Home Pro</Badge>
            <Badge variant="outline" className="bg-white border-outline-variant/30 text-xs font-normal">Horizon Mobile</Badge>
          </div>
        </div>

        <div className="p-6 border-b border-outline-variant/10">
          <span className="text-sm font-heading font-bold block mb-4">Contact History</span>
          
          <div className="relative pl-4 space-y-4 before:absolute before:left-1.5 before:top-2 before:bottom-2 before:w-px before:bg-outline-variant/20">
            <div className="relative">
              <div className="absolute -left-5 top-1.5 w-2 h-2 rounded-full bg-primary ring-4 ring-white" />
              <div className="flex flex-col">
                <span className="text-xs font-bold">Billing Inquiry</span>
                <span className="text-[10px] text-on-surface-variant mb-2">Oct 12, 2023 • AI Agent Delta</span>
                <div className="bg-[#F3F4F6] text-xs p-2 rounded text-on-surface-variant">
                  Resolved: Automatic payment update successful.
                </div>
              </div>
            </div>
            
            <div className="relative opacity-60">
              <div className="absolute -left-5 top-1.5 w-2 h-2 rounded-full bg-outline-variant ring-4 ring-white" />
              <div className="flex flex-col">
                <span className="text-xs font-bold">Plan Upgrade</span>
                <span className="text-[10px] text-on-surface-variant">Aug 04, 2023 • Web Portal</span>
              </div>
            </div>
          </div>
        </div>

        <div className="p-6 flex-1">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-heading font-bold">CRM Notes</span>
            <Button variant="ghost" size="sm" className="h-6 text-primary text-xs hover:bg-primary/5 px-2">
              <Plus className="w-3 h-3 mr-1" /> New Note
            </Button>
          </div>
          <div className="bg-[#F9FAFB] rounded-lg p-4 border border-outline-variant/10 relative">
            <p className="text-xs italic text-on-surface-variant mb-2 leading-relaxed">
              "Prefers evening call-backs. Highly technical user, skip basic troubleshooting steps when possible."
            </p>
            <p className="text-[10px] text-on-surface-variant/60">
              — Added by Admin on Sep 15
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
