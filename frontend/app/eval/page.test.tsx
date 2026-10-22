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

import EvalPage from "./page";

const emptyRuns = { items: [], page: 1, page_size: 12, total: 0 };
const runId = "11111111-1111-4111-8111-111111111111";

function baseRun(overrides: Record<string, unknown> = {}) {
  return {
    id: runId,
    status: "SUCCEEDED",
    model_mode: "B2",
    model_name: null,
    prompt_version: null,
    scenario_kinds: ["mixed_failure"],
    seed: 42,
    num_intents: 500,
    scenario_count: 1,
    metrics: {
      scenario_count: 1,
      succeeded_count: 1,
      run_success_rate: 1,
      stage_localization_exact_rate: 1,
      stage_localization_overlap_mean: 1,
      root_cause_precision_mean: 1,
      root_cause_recall_mean: 1,
      root_cause_f1_mean: 1,
      evidence_validity_rate_mean: 1,
      unsupported_claim_rate_mean: 0,
      loss_attribution_mape: 0.08,
      tool_call_count_mean: 2.17,
      badcase_count: 0,
      model_invocation_count: 0,
      fallback_count: 1,
      total_input_tokens: null,
      total_output_tokens: null,
    },
    scenario_results: [
      {
        scenario_kind: "mixed_failure",
        scenario_id: "mixed-42",
        diagnosis_status: "SUCCEEDED",
        agent_mode: "B2",
        // The report writer stays the rule adapter on purpose; B2's provenance
        // is the policy that gathered the evidence.
        adapter_name: "RuleBasedModelAdapter",
        policy_name: "OpenAIToolCallingPolicy",
        tool_call_count: 6,
        fallback_used: true,
        fallback_reason: "MODEL_CALL_FAILED",
        stage_exact: true,
        root_cause_f1: 1,
        loss_attribution_rel_error: 0.08,
        badcases: [],
      },
    ],
    badcases: [],
    error_message: null,
    created_at: "2026-09-12T10:00:00Z",
    updated_at: "2026-09-12T10:00:00Z",
    ...overrides,
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

  it("defaults to the investigated mode and explains what it does", async () => {
    renderPage();
    expect(await screen.findByText("No evaluation selected")).toBeInTheDocument();

    const b2 = screen.getByRole("radio", { name: /B2/ });
    expect(b2).toBeChecked();
    // The selected mode's explanation is shown; the others stay collapsed.
    expect(
      screen.getByText(/Routed capabilities, a hypothesis ledger and a budget/i),
    ).toBeInTheDocument();
  });

  it("submits B2 without a prompt version", async () => {
    apiRequestMock.mockImplementation(async (path: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        return { evaluation_run_id: runId, status: "QUEUED", created: true };
      }
      if (path.endsWith(`/${runId}`)) return baseRun({ status: "QUEUED" });
      return emptyRuns;
    });
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Run B2 evaluation" }));

    await waitFor(() => {
      const request = apiRequestMock.mock.calls.find(([, init]) => init?.method === "POST");
      const body = JSON.parse(String(request?.[1]?.body));
      expect(body).toMatchObject({ model_mode: "B2", prompt_version: null, seed: 42 });
      expect(body.scenario_kinds).toHaveLength(7);
    });
  });

  it("asks for a prompt version only in the one-shot mode", async () => {
    renderPage();
    await screen.findByText("No evaluation selected");
    expect(screen.queryByText("Prompt version")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: /B1/ }));
    expect(screen.getByText("Prompt version")).toBeInTheDocument();
  });

  it("shows the investigation policy rather than the report writer", async () => {
    apiRequestMock.mockImplementation(async (path: string) => {
      if (path.endsWith(`/${runId}`)) return baseRun();
      return { ...emptyRuns, total: 1, items: [baseRun()] };
    });
    renderPage();

    fireEvent.click(
      await screen.findByRole("button", { name: /Open the B2 evaluation/ }),
    );
    // The scenario row must name the policy, and must not claim a model call.
    expect(await screen.findByText("model · tool-calling")).toBeInTheDocument();
    expect(screen.getByText("MODEL_CALL_FAILED")).toBeInTheDocument();
  });

  it("fills the comparison column from another mode run at the same seed", async () => {
    const b0 = baseRun({
      id: "22222222-2222-4222-8222-222222222222",
      model_mode: "B0",
      metrics: { ...baseRun().metrics, tool_call_count_mean: 6, fallback_count: 0 },
    });
    apiRequestMock.mockImplementation(async (path: string) => {
      if (path.endsWith(`/${runId}`)) return baseRun();
      return { ...emptyRuns, total: 2, items: [baseRun(), b0] };
    });
    renderPage();

    fireEvent.click(
      await screen.findByRole("button", { name: /Open the B2 evaluation/ }),
    );

    // Both modes appear as columns, so the delta is a real comparison.
    expect(await screen.findByText("Tool calls per scenario")).toBeInTheDocument();
    expect(screen.getByText("6.00")).toBeInTheDocument();
  });
});
