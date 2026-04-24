"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ActivityChart } from "@/components/dashboard/ActivityChart";
import { ArrowUpRight, ArrowDownRight, Users, PhoneCall, Clock, BrainCircuit } from "lucide-react";

export default function Dashboard() {
  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      <div>
        <h1 className="text-3xl font-heading font-bold text-on-surface">System Overview</h1>
        <p className="text-on-surface-variant mt-2">Real-time metrics and pipeline performance for AI calling agent.</p>
      </div>

      {/* Metrics Grid */}
      {/* Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <Card className="border-none shadow-sm bg-white hover:shadow-md transition-shadow">
          <CardContent className="p-6">
            <div className="flex justify-between items-start mb-4">
              <div className="w-10 h-10 rounded-full bg-blue-50 text-primary flex items-center justify-center">
                <PhoneCall className="w-5 h-5" />
              </div>
              <div className="flex items-center text-secondary text-sm font-bold">
                <ArrowUpRight className="w-4 h-4 mr-1" />
                18.4%
              </div>
            </div>
            <div className="flex flex-col">
              <span className="text-3xl font-heading font-bold text-on-surface">1,482</span>
              <span className="text-sm font-medium text-on-surface-variant mt-1">Total Calls Today</span>
            </div>
          </CardContent>
        </Card>

        <Card className="border-none shadow-sm bg-white hover:shadow-md transition-shadow">
          <CardContent className="p-6">
            <div className="flex justify-between items-start mb-4">
              <div className="w-10 h-10 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center">
                <Users className="w-5 h-5" />
              </div>
              <div className="flex items-center text-secondary text-sm font-bold">
                <ArrowUpRight className="w-4 h-4 mr-1" />
                5.2%
              </div>
            </div>
            <div className="flex flex-col">
              <span className="text-3xl font-heading font-bold text-on-surface">92.8%</span>
              <span className="text-sm font-medium text-on-surface-variant mt-1">Resolution Rate</span>
            </div>
          </CardContent>
        </Card>

        <Card className="border-none shadow-sm bg-white hover:shadow-md transition-shadow">
          <CardContent className="p-6">
            <div className="flex justify-between items-start mb-4">
              <div className="w-10 h-10 rounded-full bg-purple-50 text-purple-600 flex items-center justify-center">
                <Clock className="w-5 h-5" />
              </div>
              <div className="flex items-center text-error text-sm font-bold">
                <ArrowUpRight className="w-4 h-4 mr-1" />
                1.4%
              </div>
            </div>
            <div className="flex flex-col">
              <span className="text-3xl font-heading font-bold text-on-surface">01:58</span>
              <span className="text-sm font-medium text-on-surface-variant mt-1">Avg Handle Time</span>
            </div>
          </CardContent>
        </Card>

        <Card className="border-none shadow-sm bg-white hover:shadow-md transition-shadow relative overflow-hidden">
          <div className="absolute top-0 right-0 p-4 opacity-5 pointer-events-none">
            <BrainCircuit className="w-32 h-32" />
          </div>
          <CardContent className="p-6 relative z-10">
            <div className="flex justify-between items-start mb-4">
              <div className="w-10 h-10 rounded-full bg-orange-50 text-orange-600 flex items-center justify-center">
                <BrainCircuit className="w-5 h-5" />
              </div>
              <div className="flex items-center text-secondary text-sm font-bold">
                <ArrowDownRight className="w-4 h-4 mr-1" />
                12ms
              </div>
            </div>
            <div className="flex flex-col">
              <span className="text-3xl font-heading font-bold text-on-surface">72ms</span>
              <span className="text-sm font-medium text-on-surface-variant mt-1">Avg AI Latency</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Main Chart */}
      <Card className="border-none shadow-sm bg-white">
        <CardHeader className="pb-2 border-b border-outline-variant/10">
          <CardTitle className="text-lg font-heading font-bold">Activity Heatmap</CardTitle>
          <p className="text-sm text-on-surface-variant">Call volume and resolution success over time.</p>
        </CardHeader>
        <CardContent className="p-6">
          <div className="h-[350px] w-full">
            <ActivityChart />
          </div>
        </CardContent>
      </Card>

      {/* Secondary Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="border-none shadow-sm bg-white lg:col-span-2">
          <CardHeader className="pb-2 border-b border-outline-variant/10">
            <CardTitle className="text-lg font-heading font-bold">Pipeline Insights</CardTitle>
          </CardHeader>
          <CardContent className="p-6">
            <div className="space-y-6">
              {[
                { name: "Deepgram STT", value: "99.9%", desc: "Uptime", color: "bg-emerald-500" },
                { name: "GPT-4o Reasoning", value: "82ms", desc: "Latency", color: "bg-blue-500" },
                { name: "ElevenLabs TTS", value: "115ms", desc: "Latency", color: "bg-purple-500" },
                { name: "RAG Knowledge Base", value: "94%", desc: "Hit Rate", color: "bg-orange-500" }
              ].map((item, i) => (
                <div key={i} className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full ${item.color}`} />
                    <span className="font-medium text-sm text-on-surface">{item.name}</span>
                  </div>
                  <div className="flex flex-col items-end">
                    <span className="font-bold text-sm text-on-surface">{item.value}</span>
                    <span className="text-xs text-on-surface-variant">{item.desc}</span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className="border-none shadow-sm bg-white">
          <CardHeader className="pb-2 border-b border-outline-variant/10">
            <CardTitle className="text-lg font-heading font-bold">Recent Errors</CardTitle>
          </CardHeader>
          <CardContent className="p-6">
            <div className="space-y-4">
              {[
                { time: "10:42 AM", msg: "TTS API Timeout (Fallback engaged)" },
                { time: "09:15 AM", msg: "Websocket connection dropped" },
                { time: "08:30 AM", msg: "High latency on STT cluster" }
              ].map((err, i) => (
                <div key={i} className="flex gap-3 text-sm">
                  <span className="text-xs font-mono text-on-surface-variant shrink-0">{err.time}</span>
                  <span className="text-error font-medium">{err.msg}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
