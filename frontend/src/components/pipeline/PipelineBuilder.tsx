"use client";

/**
 * PipelineBuilder — interactive visual editor for the AI execution graph.
 *
 * Fetches the active pipeline JSON from the Django backend (via Next.js proxy)
 * and lets users rearrange nodes / edges, then persist changes via POST.
 */

import { useCallback, useEffect, useState } from "react";
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  addEdge,
  type Connection,
  type Node,
  type Edge,
  type OnConnect,
  Handle,
  Position,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Save } from "lucide-react";

// ────────────────────────────────────────────────────────────
// Node data shape coming from the Django backend
// ────────────────────────────────────────────────────────────
interface PipelineNodeData extends Record<string, unknown> {
  label?: string;
}

type PipelineNode = Node<PipelineNodeData>;
type PipelineEdge = Edge;

// ────────────────────────────────────────────────────────────
// Custom node renderer (shared by all pipeline node types)
// ────────────────────────────────────────────────────────────
interface BaseNodeProps {
  data: PipelineNodeData;
  typeLabel: string;
}

function BaseNode({ data, typeLabel }: BaseNodeProps) {
  return (
    <div className="bg-surface-container-lowest border border-outline-variant/20 shadow-sm rounded-lg p-4 font-heading text-on-surface w-[200px]">
      <Handle type="target" position={Position.Left} />
      <div className="flex flex-col">
        <span className="text-[10px] font-bold text-primary tracking-wider uppercase mb-1">
          {typeLabel}
        </span>
        <span className="text-sm">{String(data.label ?? "")}</span>
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

/**
 * nodeTypes must live at module scope so ReactFlow gets a stable reference
 * and does not unmount/remount nodes on every render.
 */
const nodeTypes = {
  STT: (props: { data: PipelineNodeData }) => <BaseNode {...props} typeLabel="Speech to Text" />,
  LLM: (props: { data: PipelineNodeData }) => <BaseNode {...props} typeLabel="LLM Engine" />,
  TTS: (props: { data: PipelineNodeData }) => <BaseNode {...props} typeLabel="Text to Speech" />,
  LOGIC: (props: { data: PipelineNodeData }) => <BaseNode {...props} typeLabel="Logic" />,
  RAG: (props: { data: PipelineNodeData }) => <BaseNode {...props} typeLabel="RAG Context" />,
};

// ────────────────────────────────────────────────────────────
// PipelineBuilder component
// ────────────────────────────────────────────────────────────
export function PipelineBuilder() {
  const [nodes, setNodes, onNodesChange] = useNodesState<PipelineNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<PipelineEdge>([]);
  const [isSaving, setIsSaving] = useState(false);

  /** Fetch the current graph configuration from the Django backend. */
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["pipeline-graph"],
    queryFn: async () => {
      const res = await fetch("/api/v1/engine/graph/");
      if (!res.ok) throw new Error("Failed to fetch graph data");
      return res.json() as Promise<{ nodes: PipelineNode[]; edges: PipelineEdge[] }>;
    },
  });

  useEffect(() => {
    if (data && (data.nodes?.length > 0 || data.edges?.length > 0)) {
      setNodes(data.nodes ?? []);
      setEdges(data.edges ?? []);
    } else if (data) {
      // Fallback dummy data if backend is empty
      const initialNodes: PipelineNode[] = [
        { id: "node-1", type: "STT", position: { x: 100, y: 100 }, data: { label: "Deepgram STT (Nova-2)" } },
        { id: "node-2", type: "LLM", position: { x: 400, y: 100 }, data: { label: "GPT-4o Agent Engine" } },
        { id: "node-3", type: "TTS", position: { x: 700, y: 100 }, data: { label: "ElevenLabs (Turbo v2)" } },
        { id: "node-4", type: "RAG", position: { x: 400, y: 250 }, data: { label: "Company Knowledge Base" } },
      ];
      const initialEdges: PipelineEdge[] = [
        { id: "e1-2", source: "node-1", target: "node-2", animated: true },
        { id: "e2-3", source: "node-2", target: "node-3", animated: true },
        { id: "e4-2", source: "node-4", target: "node-2", style: { strokeDasharray: "5 5" } },
      ];
      setNodes(initialNodes);
      setEdges(initialEdges);
    }
  }, [data, setNodes, setEdges]);

  const onConnect: OnConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge(params, eds)),
    [setEdges],
  );

  /** Persist the current graph layout back to the backend. */
  const saveGraph = async () => {
    setIsSaving(true);
    try {
      // Map ReactFlow edge fields to executor-expected from/to keys.
      const mappedEdges = edges.map((e) => ({ ...e, from: e.source, to: e.target }));

      const res = await fetch("/api/v1/engine/graph/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ graph_json: { nodes, edges: mappedEdges } }),
      });
      if (!res.ok) throw new Error("Failed to save graph");
      await refetch();
    } catch (err) {
      // Surface save errors without crashing the editor.
      const message = err instanceof Error ? err.message : "Unknown error";
      alert(`Failed to save pipeline: ${message}`);
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground animate-pulse">
        Loading Pipeline...
      </div>
    );
  }

  return (
    <div className="w-full h-[calc(100vh-100px)] border border-outline-variant/10 rounded-xl overflow-hidden bg-background relative">
      <div className="absolute top-4 right-4 z-10">
        <Button
          onClick={saveGraph}
          disabled={isSaving}
          className="gap-2 bg-primary hover:bg-primary/90 text-white shadow-md"
        >
          <Save className="w-4 h-4" />
          {isSaving ? "Saving..." : "Save Pipeline"}
        </Button>
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        fitView
        attributionPosition="bottom-right"
      >
        <Controls className="bg-surface-container-lowest border-none shadow-sm fill-on-surface" />
        <MiniMap
          className="bg-surface-container-lowest"
          maskColor="var(--surface-container-low)"
        />
        <Background color="var(--outline-variant)" gap={16} />
      </ReactFlow>
    </div>
  );
}
