import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { apiRequestMock } = vi.hoisted(() => ({ apiRequestMock: vi.fn() }));

vi.mock("@/lib/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/client")>(
    "@/lib/api/client",
  );
  return { ...actual, apiRequest: apiRequestMock };
});

vi.mock("@/components/charts/evaluation-chart", () => ({
  EvaluationChart: () => <div data-testid="evaluation-chart" />,
}));

import EvalPage from "./page";

const emptyRuns = { items: [], page: 1, page_size: 8, total: 0 };
const runId = "11111111-1111-4111-8111-111111111111";

function queuedRun() {
  return {
    id: runId,
    status: "QUEUED",
    model_mode: "B1",
    model_name: "demo-model",
    prompt_version: "diagnosis_v1",
    scenario_kinds: ["normal"],
    seed: 42,
    num_intents: 500,
    scenario_count: 1,
    metrics: null,
    scenario_results: null,
    badcases: null,
    error_message: null,
    created_at: "2026-08-20T10:00:00Z",
    updated_at: "2026-08-20T10:00:00Z",
  };
}

function succeededB1Run() {
  return {
    ...queuedRun(),
    status: "SUCCEEDED",
    metrics: {
      scenario_count: 2,
      succeeded_count: 2,
      run_success_rate: 1,
      stage_localization_exact_rate: 1,
      stage_localization_overlap_mean: 1,
      root_cause_precision_mean: 1,
      root_cause_recall_mean: 1,
      root_cause_f1_mean: 1,
      evidence_validity_rate_mean: 1,
      unsupported_claim_rate_mean: 0,
      badcase_count: 0,
      model_invocation_count: 1,
      fallback_count: 1,
      total_input_tokens: 120,
      total_output_tokens: 30,
    },
    scenario_results: [
      {
        scenario_kind: "normal",
        scenario_id: "normal-42",
        diagnosis_status: "SUCCEEDED",
        adapter_name: "OpenAICompatibleModelAdapter",
        fallback_used: false,
        predicted_root_causes: ["NORMAL_PAYMENT_FAILURE"],
        expected_root_causes: ["NORMAL_PAYMENT_FAILURE"],
        badcases: [],
        root_cause_f1: 1,
      },
      {
        scenario_kind: "channel_timeout",
        scenario_id: "timeout-42",
        diagnosis_status: "SUCCEEDED",
        adapter_name: "RuleBasedModelAdapter",
        fallback_used: true,
        fallback_reason: "MODEL_CALL_FAILED",
        predicted_root_causes: ["CHANNEL_TIMEOUT"],
        expected_root_causes: ["CHANNEL_TIMEOUT"],
        badcases: [],
        root_cause_f1: 1,
      },
    ],
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return render(<EvalPage />, { wrapper: Wrapper });
}

describe("Eval Lab", () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
    apiRequestMock.mockResolvedValue(emptyRuns);
  });

  it("shows B1 cost and fallback boundaries only for model-backed mode", async () => {
    renderPage();
    expect(await screen.findByText("No evaluation selected")).toBeInTheDocument();
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Prompt version")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: /B1 · Model backed/i }));

    expect(screen.getByRole("note")).toHaveTextContent("falls back to B0");
    expect(screen.getByRole("note")).toHaveTextContent("not a guaranteed model invocation");
    expect(screen.getByLabelText("Prompt version")).toBeInTheDocument();
  });

  it("submits the explicit B1 contract with all selected scenarios", async () => {
    apiRequestMock.mockImplementation(async (path: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        return { evaluation_run_id: runId, status: "QUEUED", created: true };
      }
      if (path.endsWith(`/${runId}`)) return queuedRun();
      return emptyRuns;
    });
    renderPage();

    fireEvent.click(screen.getByRole("radio", { name: /B1 · Model backed/i }));
    fireEvent.change(screen.getByLabelText("Prompt version"), {
      target: { value: "diagnosis_v2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run B1 evaluation" }));

    await waitFor(() => {
      const request = apiRequestMock.mock.calls.find(([, init]) => init?.method === "POST");
      expect(request).toBeDefined();
      const body = JSON.parse(String(request?.[1]?.body));
      expect(body).toMatchObject({
        model_mode: "B1",
        prompt_version: "diagnosis_v2",
        seed: 42,
        num_intents: 500,
      });
      expect(body.scenario_kinds).toHaveLength(7);
    });
  });

  it("distinguishes verified model calls from rule fallbacks", async () => {
    apiRequestMock.mockImplementation(async (path: string) => {
      if (path.endsWith(`/${runId}`)) return succeededB1Run();
      return {
        ...emptyRuns,
        total: 1,
        items: [queuedRun()],
      };
    });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: new RegExp(runId) }));

    expect(await screen.findByText("Verified model calls")).toBeInTheDocument();
    expect(screen.getByText("Rule fallbacks")).toBeInTheDocument();
    expect(screen.getByText("Recorded tokens")).toBeInTheDocument();
    expect(screen.getByText("MODEL_CALL_FAILED")).toBeInTheDocument();
    expect(screen.getByText("OpenAICompatibleModelAdapter")).toBeInTheDocument();
  });
});
