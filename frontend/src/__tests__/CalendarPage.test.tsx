import { describe, it, expect, vi, beforeEach } from "vitest";
import { act } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { CalendarPage } from "../pages/personal/CalendarPage";
import { ApiError, NetworkError } from "../lib/api";
import type {
  CalendarDashboard,
  CalendarEvent,
  CalendarResponse,
  UpcomingTask,
} from "../lib/api";
import { useNotification } from "../state/notifications";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      calendar: {
        get: vi.fn(),
        getUpcoming: vi.fn(),
        getDashboard: vi.fn(),
        markComplete: vi.fn(),
        scheduleReminder: vi.fn(),
        getTypes: vi.fn(),
      },
    },
  };
});

const mockEvent: CalendarEvent = {
  id: "evt-1",
  title: "File Income Tax Return",
  description: "Annual income tax return filing deadline.",
  due_date: "2026-09-30",
  fiscal_year: 2026,
  priority: "critical",
  category: "income_tax",
  event_type: "filing",
  legal_reference: "Section 114",
  penalty: "Late fee applies",
  days_remaining: 17,
  is_overdue: false,
  is_completed: false,
  extension_available: true,
};

const mockDashboard: CalendarDashboard = {
  taxpayer_type: "individual",
  compliance_score: 85,
  compliance_grade: "B",
  total_events: 10,
  overdue_count: 1,
  critical_upcoming_30d: 2,
  critical_upcoming_7d: 1,
  next_7_days_tasks: [
    { title: "File Income Tax Return", due_date: "2026-09-30", days_remaining: 17 },
  ],
  compliance_grade_color: "var(--c-accent)",
  summary_message: "You are in good standing.",
};

const mockCalendarResponse: CalendarResponse = {
  query: {},
  total_events: 1,
  events: [mockEvent],
  summary: { by_category: {}, by_priority: {}, by_month: {}, by_type: {} },
  upcoming_tasks: [],
  overdue_events: [],
  compliance_score: 85,
  compliance_grade: "B",
  recommendations: ["File early to avoid penalties."],
  generated_at: "2026-09-13T00:00:00Z",
};

const mockUpcoming: UpcomingTask[] = [
  {
    event_id: "evt-1",
    title: "File Income Tax Return",
    due_date: "2026-09-30",
    days_remaining: 17,
    priority: "critical",
    category: "income_tax",
    event_type: "filing",
    is_overdue: false,
    urgency: "high",
    action_required: "Prepare documents",
  },
];

function renderPage() {
  return render(
    <MemoryRouter>
      <CalendarPage />
    </MemoryRouter>,
  );
}

describe("CalendarPage", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    useNotification.setState({ current: null });
    const { api } = await import("../lib/api");
    vi.mocked(api.calendar.getDashboard).mockResolvedValue(mockDashboard);
    vi.mocked(api.calendar.get).mockResolvedValue(mockCalendarResponse);
    vi.mocked(api.calendar.getUpcoming).mockResolvedValue(mockUpcoming);
    vi.mocked(api.calendar.markComplete).mockResolvedValue({ event_id: "evt-1", completed: true });
    vi.mocked(api.calendar.scheduleReminder).mockResolvedValue({
      event_id: "evt-1",
      reminders_scheduled: 1,
      reminder_ids: ["r1"],
    });
  });

  it("renders the compliance calendar page", () => {
    renderPage();
    expect(screen.getByText("Compliance Calendar")).toBeInTheDocument();
    expect(
      screen.getByText(/tax compliance deadlines, upcoming tasks, and overdue items/),
    ).toBeInTheDocument();
    expect(screen.getByTestId("cal-taxpayer-type")).toBeInTheDocument();
    expect(screen.getByTestId("cal-refresh-btn")).toBeInTheDocument();
    expect(screen.getByTestId("cal-filters")).toBeInTheDocument();
  });

  it("shows the dashboard loader while its request is pending", async () => {
    const { api } = await import("../lib/api");
    vi.mocked(api.calendar.getDashboard).mockImplementation(() => new Promise(() => {}));
    vi.mocked(api.calendar.get).mockImplementation(() => new Promise(() => {}));
    vi.mocked(api.calendar.getUpcoming).mockImplementation(() => new Promise(() => {}));

    renderPage();

    // Dashboard loader shows while its request is pending; the events loader
    // takes over once the dashboard slot resolves (progressive loading).
    expect(screen.getByTestId("cal-dashboard-loading")).toBeInTheDocument();
  });

  it("shows the events loader after the dashboard has loaded", async () => {
    const { api } = await import("../lib/api");
    vi.mocked(api.calendar.getDashboard).mockResolvedValue(mockDashboard);
    vi.mocked(api.calendar.get).mockImplementation(() => new Promise(() => {}));
    vi.mocked(api.calendar.getUpcoming).mockImplementation(() => new Promise(() => {}));

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("cal-dashboard-card")).toBeInTheDocument();
    });
    expect(screen.getByTestId("cal-events-loading")).toBeInTheDocument();
  });

  it("requests the dashboard for the individual taxpayer on mount", async () => {
    const { api } = await import("../lib/api");
    renderPage();

    await waitFor(() => {
      expect(api.calendar.getDashboard).toHaveBeenCalledWith("individual");
    });
    expect(api.calendar.get).toHaveBeenCalled();
    expect(api.calendar.getUpcoming).toHaveBeenCalledWith("individual", 30);
  });

  it("shows Individual for the personal workspace and Business after switching", async () => {
    const { api } = await import("../lib/api");
    const { useWorkspace } = await import("../state/workspace");
    renderPage();

    // Personal workspace → Individual
    await waitFor(() => {
      expect(api.calendar.getDashboard).toHaveBeenCalledWith("individual");
    });
    expect(screen.getByTestId("cal-taxpayer-value")).toHaveTextContent("Individual");

    // Switch workspace → Business
    act(() => {
      useWorkspace.setState({ active: "business" });
    });

    await waitFor(() => {
      expect(api.calendar.getDashboard).toHaveBeenCalledWith("business");
    });
    expect(screen.getByTestId("cal-taxpayer-value")).toHaveTextContent("Business");

    act(() => {
      useWorkspace.setState({ active: "personal" });
    });
  });

  it("refetches the dashboard when refresh is clicked", async () => {
    const { api } = await import("../lib/api");
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(api.calendar.getDashboard).toHaveBeenCalledTimes(1);
    });

    await user.click(screen.getByTestId("cal-refresh-btn"));

    await waitFor(() => {
      expect(api.calendar.getDashboard).toHaveBeenCalledTimes(2);
    });
  });

  it("shows error banner when events fail to load", async () => {
    const { api } = await import("../lib/api");
    vi.mocked(api.calendar.get).mockRejectedValue(
      new ApiError("GET /calendar failed: 500", 500, "Server error"),
    );

    renderPage();

    const banner = await screen.findByTestId("cal-error");
    expect(banner).toHaveTextContent("Could not load events");
    expect(banner).toHaveTextContent("Server error");
  });

  it("shows offline error when the server is unreachable", async () => {
    const { api } = await import("../lib/api");
    vi.mocked(api.calendar.get).mockRejectedValue(new NetworkError("Failed to fetch"));

    renderPage();

    const banner = await screen.findByTestId("cal-error");
    expect(banner).toHaveTextContent("Could not load events");
    expect(banner).toHaveTextContent("Cannot reach the server");
  });
});
