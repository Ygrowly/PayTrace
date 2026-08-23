"use client";

import { useEffect, useRef } from "react";
import type { ECharts } from "echarts";
import type { FunnelResult } from "@/lib/api/client";

function stageLabel(stage: string): string {
  return stage.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function FunnelChart({ data }: { data: FunnelResult }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let chart: ECharts | undefined;
    let observer: ResizeObserver | undefined;
    let disposed = false;

    const render = async () => {
      const echarts = await import("echarts");
      if (disposed || !containerRef.current) return;
      chart = echarts.init(containerRef.current, undefined, { renderer: "canvas" });
      chart.setOption({
        animationDuration: 450,
        color: ["#94a3b8", "#1e40af"],
        grid: { left: 150, right: 26, top: 20, bottom: 38 },
        legend: { bottom: 0, icon: "roundRect", itemWidth: 12, itemHeight: 8, textStyle: { color: "#64748b", fontSize: 11 } },
        tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (value: number) => `${(value * 100).toFixed(1)}%` },
        xAxis: { type: "value", min: 0, max: 1, axisLabel: { color: "#94a3b8", formatter: (value: number) => `${Math.round(value * 100)}%` }, splitLine: { lineStyle: { color: "#e2e8f0" } } },
        yAxis: { type: "category", data: data.deltas.map((item) => stageLabel(item.stage)), axisLabel: { color: "#475569", fontSize: 11 } },
        series: [
          { name: "Baseline", type: "bar", barMaxWidth: 12, data: data.deltas.map((item) => item.baseline_overall_rate), itemStyle: { borderRadius: [0, 4, 4, 0] } },
          { name: "Incident", type: "bar", barMaxWidth: 12, data: data.deltas.map((item) => item.incident_overall_rate), itemStyle: { borderRadius: [0, 4, 4, 0] } },
        ],
      });
      observer = new ResizeObserver(() => chart?.resize());
      observer.observe(containerRef.current);
    };

    void render();
    return () => {
      disposed = true;
      observer?.disconnect();
      chart?.dispose();
    };
  }, [data]);

  return <div aria-label="Baseline and incident funnel conversion comparison" className="h-[340px] w-full" ref={containerRef} role="img" />;
}
