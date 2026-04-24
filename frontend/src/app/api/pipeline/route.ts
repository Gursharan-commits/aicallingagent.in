import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export async function GET() {
  try {
    // The graphify output is 2 levels up from frontend (root/graphify-out)
    const filePath = path.join(process.cwd(), '..', 'graphify-out', '.graphify_chunk_01.json');
    
    if (!fs.existsSync(filePath)) {
      return NextResponse.json({ error: "Graphify JSON not found" }, { status: 404 });
    }

    const fileContents = fs.readFileSync(filePath, 'utf8');
    const graphifyData = JSON.parse(fileContents);

    // We will parse the hyperedges to construct our React Flow canvas
    // Specifically looking for STT, LLM, and TTS chains
    const rfNodes: any[] = [];
    const rfEdges: any[] = [];

    const hyperedges = graphifyData.hyperedges || [];
    
    // Y-coordinate tracking to space out nodes
    let yOffset = 50;

    hyperedges.forEach((hedge: any, index: number) => {
      // Find the primary node type (stt, tts, llm) based on label
      let type = "default";
      if (hedge.label.includes("STT")) type = "sttNode";
      if (hedge.label.includes("LLM")) type = "llmNode";
      if (hedge.label.includes("TTS")) type = "ttsNode";

      // Extract the provider nodes mapped to this chain
      const providers = hedge.nodes
        .filter((nId: string) => !nId.includes("servicepy") && !nId.includes("routerpy") && !nId.includes("rule"))
        .map((nId: string) => {
           const nodeData = graphifyData.nodes.find((n: any) => n.id === nId);
           return nodeData ? nodeData.label : nId;
        });

      rfNodes.push({
        id: hedge.id,
        type: "default", // Using default until we build custom nodes
        position: { x: 250, y: yOffset },
        data: { 
          label: hedge.label.split(" (")[0], // Just the title part
          providers: providers 
        },
        className: "bg-surface-container-lowest border border-outline-variant/20 shadow-sm rounded-lg p-4 font-heading text-on-surface w-[300px]",
      });

      // If there is a previous node, connect them
      if (index > 0) {
        rfEdges.push({
          id: `e-${hyperedges[index-1].id}-${hedge.id}`,
          source: hyperedges[index-1].id,
          target: hedge.id,
          animated: true,
          style: { stroke: 'var(--primary)' }
        });
      }

      yOffset += 150;
    });

    return NextResponse.json({ nodes: rfNodes, edges: rfEdges });
  } catch (error) {
    console.error("Error parsing graphify data:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
