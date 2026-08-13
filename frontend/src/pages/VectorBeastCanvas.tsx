import React, { useState, useCallback, useEffect } from 'react';
import {
  ReactFlow,
  Controls,
  Background,
  applyNodeChanges,
  applyEdgeChanges,
  addEdge,
  Node,
  Edge,
  Handle,
  Position
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Play, Sparkles, AlertTriangle, Layers, ArrowRight, CheckCircle2, RotateCcw } from 'lucide-react';

// Custom Node Card Component
const CanvasNodeCard = ({ data, type }: { data: any, type: string }) => {
  const getBadgeColor = () => {
    switch (type) {
      case 'dataSource': return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
      case 'llmAgent': return 'bg-purple-500/20 text-purple-400 border-purple-500/30';
      case 'filter': return 'bg-amber-500/20 text-amber-400 border-amber-500/30';
      case 'vectorSearch': return 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30';
      case 'rerank': return 'bg-pink-500/20 text-pink-400 border-pink-500/30';
      case 'output': return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
      default: return 'bg-gray-500/20 text-gray-400';
    }
  };

  return (
    <div className="bg-slate-900/90 border border-slate-700/80 rounded-xl p-3 min-w-[200px] shadow-2xl backdrop-blur-md">
      <Handle type="target" position={Position.Left} className="w-3 h-3 bg-emerald-400 border-2 border-slate-900" />
      <div className="flex items-center gap-2 mb-2">
        <span className="text-lg">{data.icon || '📦'}</span>
        <div>
          <div className="font-bold text-sm text-slate-100">{data.label}</div>
          <span className={`text-[10px] px-2 py-0.5 rounded-full border font-mono ${getBadgeColor()}`}>
            {type}
          </span>
        </div>
      </div>
      <div className="text-xs text-slate-400 font-mono bg-slate-950/60 p-2 rounded border border-slate-800/80">
        {data.detail}
      </div>
      <Handle type="source" position={Position.Right} className="w-3 h-3 bg-emerald-400 border-2 border-slate-900" />
    </div>
  );
};

const nodeTypes = {
  dataSource: (props: any) => <CanvasNodeCard {...props} type="dataSource" />,
  llmAgent: (props: any) => <CanvasNodeCard {...props} type="llmAgent" />,
  filter: (props: any) => <CanvasNodeCard {...props} type="filter" />,
  vectorSearch: (props: any) => <CanvasNodeCard {...props} type="vectorSearch" />,
  rerank: (props: any) => <CanvasNodeCard {...props} type="rerank" />,
  output: (props: any) => <CanvasNodeCard {...props} type="output" />,
};

// Preset 1: Default Post-Filter Topology
const defaultPresetNodes: Node[] = [
  { id: 'n1', type: 'dataSource', position: { x: 50, y: 150 }, data: { label: 'Data Source', icon: '📁', detail: 'collection: "profiles"' } },
  { id: 'n2', type: 'vectorSearch', position: { x: 300, y: 150 }, data: { label: 'Vector Search', icon: '🔎', detail: 'index: "persona_chunks_vector"\nlimit: 10' } },
  { id: 'n3', type: 'filter', position: { x: 550, y: 150 }, data: { label: 'Filter', icon: '🎯', detail: 'location == "San Francisco, CA"' } },
  { id: 'n4', type: 'output', position: { x: 800, y: 150 }, data: { label: 'Match Feed Output', icon: '🚀', detail: 'format: "profile_cards"' } },
];

const defaultPresetEdges: Edge[] = [
  { id: 'e1-2', source: 'n1', target: 'n2', animated: true, style: { stroke: '#10B981', strokeWidth: 2 } },
  { id: 'e2-3', source: 'n2', target: 'n3', animated: true, style: { stroke: '#10B981', strokeWidth: 2 } },
  { id: 'e3-4', source: 'n3', target: 'n4', animated: true, style: { stroke: '#10B981', strokeWidth: 2 } },
];

// Preset 2: Pre-Filter Rewired Topology
const preFilterPresetNodes: Node[] = [
  { id: 'n1', type: 'dataSource', position: { x: 50, y: 150 }, data: { label: 'Data Source', icon: '📁', detail: 'collection: "profiles"' } },
  { id: 'n3', type: 'filter', position: { x: 300, y: 150 }, data: { label: 'Filter', icon: '🎯', detail: 'location == "San Francisco, CA"' } },
  { id: 'n2', type: 'vectorSearch', position: { x: 550, y: 150 }, data: { label: 'Vector Search', icon: '🔎', detail: 'index: "persona_chunks_vector"\nlimit: 10' } },
  { id: 'n4', type: 'output', position: { x: 800, y: 150 }, data: { label: 'Match Feed Output', icon: '🚀', detail: 'format: "profile_cards"' } },
];

const preFilterPresetEdges: Edge[] = [
  { id: 'e1-3', source: 'n1', target: 'n3', animated: true, style: { stroke: '#10B981', strokeWidth: 2 } },
  { id: 'e3-2', source: 'n3', target: 'n2', animated: true, style: { stroke: '#10B981', strokeWidth: 2 } },
  { id: 'e2-4', source: 'n2', target: 'n4', animated: true, style: { stroke: '#10B981', strokeWidth: 2 } },
];

export default function VectorBeastCanvas() {
  const [nodes, setNodes] = useState<Node[]>(defaultPresetNodes);
  const [edges, setEdges] = useState<Edge[]>(defaultPresetEdges);
  const [compiledResult, setCompiledResult] = useState<any>(null);
  const [executionMatches, setExecutionMatches] = useState<any[]>([]);
  const [isExecuting, setIsExecuting] = useState(false);
  const [activePreset, setActivePreset] = useState<'default' | 'preFilter'>('default');

  const onNodesChange = useCallback(
    (changes: any) => setNodes((nds) => applyNodeChanges(changes, nds)),
    []
  );

  const onEdgesChange = useCallback(
    (changes: any) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    []
  );

  const onConnect = useCallback(
    (params: any) => setEdges((eds) => addEdge({ ...params, animated: true, style: { stroke: '#10B981', strokeWidth: 2 } }, eds)),
    []
  );

  // Compile graph changes to API
  const handleCompile = useCallback(async (currentNodes: Node[], currentEdges: Edge[]) => {
    try {
      const payload = {
        nodes: currentNodes.map((n) => ({
          id: n.id,
          type: n.type,
          data: n.data
        })),
        edges: currentEdges.map((e) => ({
          id: e.id,
          source: e.source,
          target: e.target
        }))
      };

      const res = await fetch('/api/canvas/compile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      setCompiledResult(data);
    } catch (err) {
      console.error('Compilation failed:', err);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      handleCompile(nodes, edges);
    }, 250);
    return () => clearTimeout(timer);
  }, [nodes, edges, handleCompile]);

  const loadPreset = (preset: 'default' | 'preFilter') => {
    setActivePreset(preset);
    if (preset === 'default') {
      setNodes(defaultPresetNodes);
      setEdges(defaultPresetEdges);
    } else {
      setNodes(preFilterPresetNodes);
      setEdges(preFilterPresetEdges);
    }
  };

  const executePipeline = async () => {
    setIsExecuting(true);
    try {
      const payload = {
        nodes: nodes.map((n) => ({ id: n.id, type: n.type, data: n.data })),
        edges: edges.map((e) => ({ id: e.id, source: e.source, target: e.target }))
      };

      const res = await fetch('/api/canvas/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.matches) {
        setExecutionMatches(data.matches);
      }
    } catch (err) {
      console.error('Execution error:', err);
    } finally {
      setIsExecuting(false);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-64px)] bg-slate-950 text-slate-100 font-sans overflow-hidden">
      {/* Header Bar */}
      <header className="flex justify-between items-center px-6 py-3 bg-slate-900/90 border-b border-slate-800 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <span className="text-2xl">🐉</span>
          <div>
            <h1 className="text-lg font-bold bg-gradient-to-r from-emerald-400 to-cyan-400 bg-clip-text text-transparent">
              Vector Beast — Canvas Topology Engine
            </h1>
            <p className="text-xs text-slate-400">Rearrange nodes to recompile MongoDB Atlas aggregation pipelines in real-time</p>
          </div>
        </div>

        {/* Demo Presets & Controls */}
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-400 font-mono">DEMO PRESETS:</span>
          <button
            onClick={() => loadPreset('default')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg border transition-all flex items-center gap-1.5 ${
              activePreset === 'default'
                ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/50 shadow-lg shadow-emerald-500/10'
                : 'bg-slate-800 text-slate-300 border-slate-700 hover:border-slate-600'
            }`}
          >
            <RotateCcw size={14} /> Preset 1: Default (Post-Filter)
          </button>
          <button
            onClick={() => loadPreset('preFilter')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg border transition-all flex items-center gap-1.5 ${
              activePreset === 'preFilter'
                ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/50 shadow-lg shadow-emerald-500/10'
                : 'bg-slate-800 text-slate-300 border-slate-700 hover:border-slate-600'
            }`}
          >
            <Sparkles size={14} /> Preset 2: Pre-Filter Rewired
          </button>
          <button
            onClick={executePipeline}
            disabled={isExecuting || compiledResult?.status === 'error'}
            className="px-4 py-1.5 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs rounded-lg shadow-lg shadow-emerald-500/20 transition-all flex items-center gap-2 disabled:opacity-50"
          >
            <Play size={14} fill="currentColor" /> {isExecuting ? 'Executing...' : 'Run Pipeline'}
          </button>
        </div>
      </header>

      {/* Main Workspace Layout */}
      <div className="grid grid-cols-12 flex-1 overflow-hidden">
        {/* React Flow Canvas */}
        <div className="col-span-7 relative border-r border-slate-800 bg-slate-950">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            nodeTypes={nodeTypes}
            fitView
          >
            <Background color="#1e293b" gap={20} />
            <Controls className="bg-slate-900 border-slate-800 text-slate-200" />
          </ReactFlow>
        </div>

        {/* Live Compiler & Inspector Panel */}
        <div className="col-span-5 flex flex-col bg-slate-900/50 backdrop-blur-md overflow-hidden">
          {/* Header */}
          <div className="px-5 py-3 border-b border-slate-800 flex justify-between items-center bg-slate-900">
            <div className="flex items-center gap-2 font-bold text-sm text-slate-200">
              <Layers size={16} className="text-emerald-400" />
              <span>Compiled MongoDB Aggregation Pipeline</span>
            </div>
            {compiledResult?.status === 'success' ? (
              <span className="text-[10px] font-mono px-2 py-0.5 bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded-full flex items-center gap-1">
                <CheckCircle2 size={12} /> Valid DAG
              </span>
            ) : (
              <span className="text-[10px] font-mono px-2 py-0.5 bg-red-500/20 text-red-400 border border-red-500/30 rounded-full flex items-center gap-1">
                <AlertTriangle size={12} /> Invalid Graph
              </span>
            )}
          </div>

          {/* Validation & Error Alert Banner */}
          {compiledResult?.status === 'error' && (
            <div className="m-4 p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-xs text-red-300 flex items-start gap-2">
              <AlertTriangle size={16} className="text-red-400 shrink-0 mt-0.5" />
              <div>
                <div className="font-bold mb-1">Graph Topology Error:</div>
                <ul className="list-disc pl-4 space-y-1">
                  {compiledResult.errors.map((err: string, idx: number) => (
                    <li key={idx}>{err}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* Topology Optimization Banner */}
          {compiledResult?.status === 'success' && (
            <div className="mx-4 mt-4 p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-xs text-emerald-300">
              <span className="font-bold">Topology Status: </span>
              {activePreset === 'preFilter' ? (
                <span>⚡ <b>Pre-Filter Optimization Active:</b> $match filter precedes $vectorSearch, restricting candidate search space for optimal performance.</span>
              ) : (
                <span>💡 <b>Post-Filter Active:</b> $vectorSearch runs over un-indexed profiles before applying $match filter stage.</span>
              )}
            </div>
          )}

          {/* Live JSON Inspector */}
          <div className="flex-1 p-4 overflow-y-auto font-mono text-xs bg-slate-950/80 m-4 rounded-xl border border-slate-800 text-emerald-300">
            <pre className="whitespace-pre-wrap">
              {compiledResult ? JSON.stringify(compiledResult, null, 2) : '// Drag nodes to compile graph...'}
            </pre>
          </div>

          {/* Match Feed Output Preview Section */}
          {executionMatches.length > 0 && (
            <div className="h-64 border-t border-slate-800 p-4 overflow-y-auto bg-slate-900/80">
              <div className="font-bold text-xs text-slate-300 mb-3 flex items-center justify-between">
                <span>🎯 Live Match Feed Results ({executionMatches.length})</span>
                <span className="text-[10px] text-slate-400 font-mono">Executed against MongoDB Atlas</span>
              </div>
              <div className="space-y-2">
                {executionMatches.map((m, idx) => (
                  <div key={idx} className="bg-slate-950 p-3 rounded-lg border border-slate-800 text-xs flex justify-between items-start">
                    <div>
                      <div className="font-bold text-slate-200">{m.display_name} <span className="text-slate-500 font-normal">({m.location})</span></div>
                      <div className="text-slate-400 text-[11px] mb-1">{m.headline}</div>
                      <div className="text-emerald-400/90 text-[10px] font-mono">{m.match_reason}</div>
                    </div>
                    <span className="bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded text-[10px] font-bold">
                      {m.match_score * 100}% Fit
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
