"use client";

import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const data = [
  { time: "00:00", calls: 120, resolved: 110 },
  { time: "02:00", calls: 85, resolved: 80 },
  { time: "04:00", calls: 40, resolved: 38 },
  { time: "06:00", calls: 150, resolved: 140 },
  { time: "08:00", calls: 480, resolved: 450 },
  { time: "10:00", calls: 820, resolved: 780 },
  { time: "12:00", calls: 950, resolved: 890 },
  { time: "14:00", calls: 880, resolved: 840 },
  { time: "16:00", calls: 720, resolved: 680 },
  { time: "18:00", calls: 540, resolved: 500 },
  { time: "20:00", calls: 320, resolved: 300 },
  { time: "22:00", calls: 190, resolved: 180 },
];

export function ActivityChart() {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="colorCalls" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#3B82F6" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="colorResolved" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#10B981" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#10B981" stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis 
          dataKey="time" 
          axisLine={false} 
          tickLine={false} 
          tick={{ fontSize: 12, fill: "#6B7280" }}
          dy={10}
        />
        <YAxis 
          axisLine={false} 
          tickLine={false} 
          tick={{ fontSize: 12, fill: "#6B7280" }}
          dx={-10}
        />
        <Tooltip 
          contentStyle={{ 
            backgroundColor: "#FFFFFF", 
            borderRadius: "8px", 
            border: "1px solid rgba(0,0,0,0.05)",
            boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)" 
          }}
          itemStyle={{ color: "#111827", fontSize: "14px", fontWeight: "600" }}
        />
        <Area 
          type="monotone" 
          dataKey="calls" 
          stroke="#3B82F6" 
          strokeWidth={3}
          fillOpacity={1} 
          fill="url(#colorCalls)" 
        />
        <Area 
          type="monotone" 
          dataKey="resolved" 
          stroke="#10B981" 
          strokeWidth={3}
          fillOpacity={1} 
          fill="url(#colorResolved)" 
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
