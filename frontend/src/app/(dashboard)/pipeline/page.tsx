import { PipelineBuilder } from "@/components/pipeline/PipelineBuilder";

export default function PipelinePage() {
  return (
    <div className="flex-1 space-y-6 p-8 pt-6">
      <div className="flex items-center justify-between space-y-2">
        <div>
          <h2 className="text-3xl font-heading font-bold tracking-tight text-primary">Pipeline Builder</h2>
          <p className="text-muted-foreground text-sm">Visually orchestrate STT, LLM, and TTS flows.</p>
        </div>
      </div>
      <PipelineBuilder />
    </div>
  );
}
