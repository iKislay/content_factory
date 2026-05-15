"use client";

import { useEffect, useState } from "react";

interface AgentNode {
  id: string;
  name: string;
  description: string;
  depends_on: string[];
  outputs: string[];
  parallel_capable: boolean;
}

interface GraphData {
  graph: AgentNode[];
  metadata: {
    total_agents: number;
    execution_mode: string;
    description: string;
  };
}

interface WorkflowGraphProps {
  runId?: string;
  currentAgent?: string;
}

export default function WorkflowGraph({ runId, currentAgent }: WorkflowGraphProps) {
  const [graph, setGraph] = useState<AgentNode[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/workflow/graph")
      .then((res) => res.json())
      .then((data: GraphData) => {
        setGraph(data.graph);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="p-4 text-gray-500">Loading workflow...</div>;
  }

  const getNodeStatus = (agentId: string) => {
    if (!currentAgent) return "pending";
    const order = ["orchestrator", "trend_scout", "research", "planner", "narrator", "critic", "production", "publisher"];
    const currentIndex = order.indexOf(currentAgent);
    const agentIndex = order.indexOf(agentId);
    
    if (agentIndex < currentIndex) return "completed";
    if (agentIndex === currentIndex) return "running";
    return "pending";
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "completed": return "bg-green-500";
      case "running": return "bg-blue-500 animate-pulse";
      default: return "bg-gray-300";
    }
  };

  return (
    <div className="p-4 bg-white rounded-lg shadow">
      <h2 className="text-lg font-semibold mb-4">Multi-Agent Pipeline</h2>
      
      <div className="flex flex-wrap gap-2 items-center justify-center">
        {graph.map((agent, index) => {
          const status = getNodeStatus(agent.id);
          const isActive = status !== "pending";
          
          return (
            <div key={agent.id} className="flex items-center">
              <div
                className={`
                  px-4 py-2 rounded-lg text-sm font-medium transition-all
                  ${isActive ? "text-white" : "text-gray-600"}
                  ${getStatusColor(status)}
                  ${agent.parallel_capable ? "ring-2 ring-yellow-400" : ""}
                `}
                title={`${agent.name}\n${agent.description}\nDepends on: ${agent.depends_on.join(", ") || "none"}\nOutputs: ${agent.outputs.join(", ")}`}
              >
                {agent.name}
              </div>
              {index < graph.length - 1 && (
                <div className="mx-1 text-gray-400">→</div>
              )}
            </div>
          );
        })}
      </div>

      <div className="mt-4 flex gap-4 text-xs text-gray-500 justify-center">
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded bg-green-500"></span>
          Completed
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded bg-blue-500 animate-pulse"></span>
          Running
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded bg-gray-300"></span>
          Pending
        </span>
        {graph.some(a => a.parallel_capable) && (
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 rounded ring-2 ring-yellow-400"></span>
            Parallel-capable
          </span>
        )}
      </div>

      {runId && (
        <div className="mt-4 p-3 bg-gray-50 rounded text-xs">
          <strong>Run ID:</strong> {runId}
        </div>
      )}
    </div>
  );
}