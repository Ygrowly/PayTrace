"use client";

import { useEffect, useState } from "react";
import type { DiagnosisEvent } from "@/lib/api/client";
import { apiUrl } from "@/lib/api/client";

const eventTypes = [
  "run_queued",
  "run_started",
  "tool_completed",
  "run_succeeded",
  "run_needs_data",
  "run_failed",
  "dispatch_failed",
];

export function useDiagnosisEvents(runId: string | null, enabled: boolean) {
  const [state, setState] = useState<{ runId: string | null; events: DiagnosisEvent[]; connected: boolean; error: string | null }>({ runId: null, events: [], connected: false, error: null });

  useEffect(() => {
    if (!runId || !enabled || typeof window === "undefined") return;

    let active = true;
    const source = new EventSource(apiUrl(`/api/v1/diagnosis-runs/${runId}/events`));
    const onOpen = () => {
      if (!active) return;
      setState({ runId, events: [], connected: true, error: null });
    };
    const onError = () => {
      if (!active) return;
      setState((current) => ({ ...current, runId, connected: false, error: "SSE connection interrupted; the browser will retry automatically." }));
    };
    const onEvent = (raw: Event) => {
      if (!active) return;
      const message = raw as MessageEvent<string>;
      try {
        const item = JSON.parse(message.data) as DiagnosisEvent;
        setState((current) => {
          const currentEvents = current.runId === runId ? current.events : [];
          if (currentEvents.some((event) => event.sequence === item.sequence)) return current;
          return { runId, events: [...currentEvents, item].sort((a, b) => a.sequence - b.sequence), connected: true, error: null };
        });
      } catch {
        setState((current) => ({ ...current, runId, error: "Received an invalid progress event from the diagnosis run." }));
      }
    };

    source.onopen = onOpen;
    source.onerror = onError;
    for (const eventType of eventTypes) source.addEventListener(eventType, onEvent);
    return () => {
      active = false;
      source.close();
      for (const eventType of eventTypes) source.removeEventListener(eventType, onEvent);
    };
  }, [enabled, runId]);

  const current = state.runId === runId ? state : { runId, events: [], connected: false, error: null };
  return { events: enabled ? current.events : [], connected: enabled && current.connected, error: enabled ? current.error : null };
}
