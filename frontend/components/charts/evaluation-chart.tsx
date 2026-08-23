"use client";

import { useEffect, useRef } from "react";
import type { ECharts } from "echarts";
import type { EvaluationRun } from "@/lib/api/client";

type Metric = { label: string; value: number };

function metricsFor(run: EvaluationRun): Metric[] {
  const metrics = run.metrics;
  if (!metrics) return [];
  return [
    { label: "Run success", value: metrics.run_success_rate },
    { label: "Stage exact", value: metrics.stage_localization_exact_rate },
    { label: "Stage overlap", value: metrics.stage_localization_overlap_mean },
    { label: "Root cause F1", value: metrics.root_cause_f1_mean },
    { label: "Evidence valid", value: metrics.evidence_validity_rate_mean },
  ];
}

export function EvaluationChart({ run }: { run: EvaluationRun }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let chart: ECharts | undefined;
    let observer: ResizeObserver | undefined;
    let disposed = false;

    const render = async () => {
      const echarts = await import("echarts");
      if (disposed || !containerRef.current) return;
      const metrics = metricsFor(run);
      chart = echarts.init(containerRef.current, undefined, { renderer: "canvas" });
      chart.setOption({
        animationDuration: 450,
        color: ["#1e40af"],
        grid: { left: 108, right: 28, top: 18, bottom: 24 },
        tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (value: number) => `${(value * 100).toFixed(1)}%` },
        xAxis: { type: "value", min: 0, max: 1, axisLabel: { color: "#94a3b8", formatter: (value: number) => `${Math.round(value * 100)}%` }, splitLine: { lineStyle: { color: "#e2e8f0" } } },
        yAxis: { type: "category", data: metrics.map((item) => item.label), axisLabel: { color: "#475569", fontSize: 11 } },
        series: [{ type: "bar", barMaxWidth: 18, data: metrics.map((item) => item.value), itemStyle: { borderRadius: [0, 5, 5, 0] }, label: { show: true, position: "right", color: "#1e3a8a", formatter: (params: { value: number }) => `${(params.value * 100).toFixed(1)}%` } }],
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
  }, [run]);

  return <div aria-label="Evaluation aggregate metrics" className="h-[280px] w-full" ref={containerRef} role="img" />;
}
