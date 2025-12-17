import React, { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph3D from "react-force-graph-3d";
import * as THREE from "three";

export default function FraudGraph3D() {
  const fgRef = useRef();

  const [rawGraph, setRawGraph] = useState(null);
  const [showOnlyFraud, setShowOnlyFraud] = useState(false);

  useEffect(() => {
    fetch("/nodes_viz.json")
      .then((res) => res.json())
      .then((data) => setRawGraph(data));
  }, []);

  const visibleGraph = useMemo(() => {
    if (!rawGraph) return null;

    if (!showOnlyFraud) return rawGraph;

    const fraudIds = new Set(
      rawGraph.nodes.filter((n) => n.is_anomalous === 1).map((n) => n.id)
    );

    return {
      nodes: rawGraph.nodes.filter((n) => fraudIds.has(n.id)),
      links: rawGraph.links.filter(
        (l) => fraudIds.has(l.source) && fraudIds.has(l.target)
      ),
    };
  }, [rawGraph, showOnlyFraud]);

  useEffect(() => {
    if (!fgRef.current || !visibleGraph) return;

    // Allow layout to stabilize before fitting
    setTimeout(() => {
      fgRef.current.zoomToFit(900, 80);
    }, 700);
  }, [visibleGraph]);

  if (!visibleGraph) {
    return (
      <div className="flex h-screen items-center justify-center text-gray-400">
        Loading Fraud Network…
      </div>
    );
  }

  return (
    <div className="relative h-screen w-full bg-linear-to-br from-black via-slate-900 to-black">
      <div className="absolute top-6 left-6 z-10">
        <h1 className="text-xl font-semibold text-white">
          Fraud Transaction Network (3D)
        </h1>
        <p className="text-sm text-gray-400 max-w-md">
          Red nodes indicate anomalous / high-risk accounts detected via EIF
        </p>
      </div>

      <div className="absolute top-24 left-6 z-10 rounded-xl bg-black/70 p-4 text-sm text-gray-200 backdrop-blur">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={showOnlyFraud}
            onChange={(e) => setShowOnlyFraud(e.target.checked)}
            className="accent-red-500"
          />
          Show only fraud nodes
        </label>

        <div className="mt-4 space-y-2 text-xs">
          <div className="flex items-center gap-2">
            <span className="h-3 w-3 rounded-full bg-red-500" />
            Fraud / Anomalous
          </div>
          <div className="flex items-center gap-2">
            <span className="h-3 w-3 rounded-full bg-green-500" />
            Normal
          </div>
          <div className="flex items-center gap-2">
            <span className="h-[0.5px] w-6 bg-gray-400" />
            Transaction Edge
          </div>
        </div>
      </div>

      <ForceGraph3D
        ref={fgRef}
        graphData={visibleGraph}
        /* Nodes */
        nodeRelSize={2}
        nodeVal={(n) => Math.max(2, n.size)}
        nodeColor={(n) => n.color}
        nodeOpacity={0.9}
        /* Tooltip */
        nodeLabel={(n) =>
          `Account ${n.id}
Anomaly Score: ${n.height.toFixed(2)}
Status: ${n.is_anomalous ? "Fraud" : "Normal"}`
        }
        /* Edges (CLEAR & DEEP) */
        linkColor={() => "rgba(180,180,180,0.35)"}
        linkOpacity={0.6}
        linkWidth={(l) => Math.min(3, Math.log(l.amount + 1))}
        linkDirectionalParticles={1}
        linkDirectionalParticleWidth={1.4}
        linkDirectionalParticleSpeed={0.004}
        /* Performance */
        enableNodeDrag={false}
        warmupTicks={120}
        cooldownTicks={0}
        /* Background */
        backgroundColor="rgba(0,0,0,0)"
      />

      {/* ---------- Footer Hint ---------- */}
      <div className="absolute bottom-4 w-full text-center text-xs text-gray-500">
        Left-click rotate · Scroll zoom · Right-click pan
      </div>
    </div>
  );
}
