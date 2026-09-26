import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
const run = {
  id: "run-example",
  project_id: "project-example",
  branch: "main",
  commit_sha: "a1b2c3d4",
  status: "COMPLETED",
  failure_reason: null,
  failure_stage: null,
  cancellation_requested: false,
  discovery_enabled: true,
  testing_enabled: true,
  progress: {
    cloning: "completed",
    building: "completed",
    discovering: "completed",
    testing: "completed",
  },
  total_tests: 10,
  passed_tests: 8,
  failed_tests: 2,
  created_at: "2026-09-26T09:00:00Z",
  started_at: "2026-09-26T09:00:00Z",
  finished_at: "2026-09-26T09:02:00Z",
};
async function mock(page: import("@playwright/test").Page) {
  await page.route("**/health", (r) =>
    r.fulfill({ json: { status: "healthy" } }),
  );
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown = {};
    if (path === "/api/test-runs")
      data =
        route.request().method() === "POST" ? run : { runs: [run], total: 1 };
    else if (path === "/api/projects/project-example")
      data = {
        id: "project-example",
        repository_url: "https://github.com/testq/storefront",
        default_branch: "main",
        detected_framework: "React",
      };
    else if (path.endsWith("/discovery"))
      data = {
        status: "completed",
        pages: [
          {
            url: "http://127.0.0.1:4321/",
            title: "Storefront",
            status: 200,
            navigation: "ok",
            links: [],
            buttons: [],
            inputs: [],
            forms: [],
          },
        ],
        api_endpoints: [],
        observations: [],
      };
    else if (path.endsWith("/logs"))
      data = {
        logs: [
          {
            id: "log1",
            source: "application",
            level: "INFO",
            message: "Server ready",
            timestamp: "2026-09-26T09:00:00Z",
          },
        ],
      };
    else if (path.endsWith("/test-results"))
      data = {
        test_results: [
          {
            id: "result1",
            test_case_id: "test1",
            status: "FAIL",
            duration_ms: 125,
            error: "Expected status 200",
            steps: [],
            assertions: [],
          },
        ],
      };
    else if (path.endsWith("/strategy"))
      data = {
        summary: "Inspect the checkout experience.",
        items: [
          {
            id: "plan1",
            category: "navigation",
            target: "/checkout",
            description: "Verify checkout navigation",
            risk_level: "high",
            priority: "high",
          },
        ],
      };
    else if (path.endsWith("/test-cases"))
      data = {
        test_cases: [
          {
            id: "test1",
            title: "Homepage responds",
            type: "api",
            priority: "high",
            source: "baseline",
            definition: { method: "GET", url: "/" },
          },
        ],
      };
    else if (path.endsWith("/evidence")) data = { evidence: [] };
    else if (path.endsWith("/failures")) data = { failures: [] };
    else data = run;
    await route.fulfill({ json: data });
  });
}

test("welcome is the entry point and every welcome action works", async ({
  page,
}) => {
  await mock(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "You build the idea.",
  );
  await expect(page).toHaveTitle(/A little more certainty/);
  await page.getByRole("button", { name: "Test your application" }).click();
  await expect(page.getByLabel("GitHub repository")).toBeFocused();
  await page.getByRole("button", { name: "Close new run" }).click();
  await page.getByRole("link", { name: "Find your perspective" }).click();
  await expect(page).toHaveURL(/#approach$/);
  await page.getByRole("button", { name: /take a closer look/ }).click();
  await page.keyboard.press("Escape");
  await page.getByRole("link", { name: "Open workspace" }).click();
  await expect(page).toHaveURL("/dashboard");
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "A clearer picture." }),
  ).toBeVisible();
  await page.locator(".sidebar-brand .brand").click();
  await expect(page).toHaveURL("/");
  await page.goto("/welcome");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "You build the idea.",
  );
});

test("workspace entry buttons, project navigation and motion preference work", async ({
  page,
}) => {
  await mock(page);
  await page.goto("/dashboard");
  for (const name of [
    "Start a new test run",
    "Start a new run",
    "New test run",
    "Put your project to the test",
  ]) {
    await page.getByRole("button", { name, exact: true }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.getByRole("button", { name: "Close new run" }).click();
  }
  await page.getByRole("link", { name: "Projects", exact: true }).click();
  await page.getByRole("button", { name: "Test a repository" }).click();
  await page.keyboard.press("Escape");
  await page.getByRole("link", { name: "Open latest run" }).click();
  await expect(page).toHaveURL("/runs/run-example");
  await page.getByRole("link", { name: "Preferences", exact: true }).click();
  await page.getByLabel("Reduce decorative motion").check();
  await page.reload();
  await expect(page.getByLabel("Reduce decorative motion")).toBeChecked();
  await expect(page.locator("html")).toHaveAttribute("data-motion", "off");
  await expect(
    page.getByRole("link", { name: "Open backend API documentation" }),
  ).toHaveAttribute("href", "http://127.0.0.1:8000/docs");
  await page.getByLabel("Reduce decorative motion").uncheck();
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole("button", { name: "Open navigation", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Start a new run", exact: true })
    .click();
  await expect(page.getByLabel("GitHub repository")).toBeFocused();
  await expect(
    page.getByRole("dialog", { name: "Workspace navigation" }),
  ).not.toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "Open navigation", exact: true }),
  ).toBeFocused();
});

test("run filters, pagination and discovery-only submission work", async ({
  page,
}) => {
  await mock(page);
  await page.route("**/api/test-runs?*", (route) => {
    const offset = new URL(route.request().url()).searchParams.get("offset");
    return route.fulfill({
      json: {
        runs: [{ ...run, id: offset === "20" ? "second-page" : run.id }],
        total: 21,
      },
    });
  });
  await page.goto("/runs");
  await expect(
    page.getByRole("button", { name: "Previous page" }),
  ).toBeDisabled();
  await page.getByLabel("Search current page of runs").fill("no-match");
  await expect(
    page.getByText("Try a different filter.", { exact: false }),
  ).toBeVisible();
  await page.getByLabel("Search current page of runs").clear();
  await page.getByLabel("Filter status").selectOption("FAILED");
  await expect(
    page.getByText("Try a different filter.", { exact: false }),
  ).toBeVisible();
  await page.getByLabel("Filter status").selectOption("all");
  await page.getByRole("button", { name: "Next page" }).click();
  await expect(
    page.getByRole("link", { name: "View run second-page" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Next page" })).toBeDisabled();
  await page.getByRole("button", { name: "Previous page" }).click();
  await expect(
    page.getByRole("link", { name: "View run run-example" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "New test run", exact: true }).click();
  await page
    .getByLabel("GitHub repository")
    .fill("https://github.com/testq/storefront");
  await page.getByLabel("Branch", { exact: false }).fill("develop");
  await page
    .getByRole("radio", { name: "Discover Map pages, forms & endpoints" })
    .check();
  const request = page.waitForRequest(
    (r) => r.method() === "POST" && r.url().endsWith("/api/test-runs"),
  );
  await page.getByRole("button", { name: "Start run", exact: true }).click();
  expect((await request).postDataJSON()).toMatchObject({
    branch: "develop",
    testing_enabled: false,
    discover: true,
  });
});

test("evidence download, log filtering and remaining detail tabs work", async ({
  page,
}) => {
  await mock(page);
  await page.route("**/api/test-runs/run-example/evidence", (r) =>
    r.fulfill({
      json: {
        evidence: [
          {
            id: "artifact",
            kind: "console",
            url: "/api/test-runs/run-example/evidence/artifact",
            size_bytes: 12,
            media_type: "application/json",
          },
        ],
      },
    }),
  );
  await page.route("**/api/test-runs/run-example/evidence/artifact", (r) =>
    r.fulfill({
      body: '{"logs":[]}',
      contentType: "application/json",
      headers: { "Content-Disposition": 'attachment; filename="console.json"' },
    }),
  );
  await page.goto("/runs/run-example");
  await page.getByRole("tab", { name: "Evidence", exact: true }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download console" }).click();
  const artifact = await download;
  expect(artifact.suggestedFilename()).toMatch(/\.json$/);
  // Chromium's download fetch bypasses page.route; actual bytes are checked
  // against the backend in the opt-in live test.
  await page.getByRole("tab", { name: "Logs", exact: true }).click();
  await page.getByLabel("Filter logs").fill("missing");
  await expect(page.getByText("Server ready")).not.toBeVisible();
  await page.getByLabel("Filter logs").clear();
  await expect(page.getByText("Server ready")).toBeVisible();
  await page.getByRole("tab", { name: "Analysis", exact: true }).click();
  await expect(page.getByText("No analysis recorded.")).toBeVisible();
  await page.getByRole("tab", { name: "Overview", exact: true }).click();
  await expect(
    page.getByRole("tab", { name: "Overview", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
});
test("welcome motion controls, added content and FAQs work", async ({
  page,
}) => {
  await mock(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Pause feature animation" }).click();
  await expect(page.locator(".ribbon-track")).toHaveCSS(
    "animation-play-state",
    "paused",
  );
  await page.getByRole("button", { name: "Resume feature animation" }).click();
  await page.mouse.move(0, 0);
  await expect(page.locator(".ribbon-track")).toHaveCSS(
    "animation-play-state",
    "running",
  );
  await page.getByRole("button", { name: "Bring your repository" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await page
    .getByText("What is the difference between discovery and testing?", {
      exact: false,
    })
    .click();
  await expect(page.locator(".faq-list details").first()).toHaveAttribute(
    "open",
    "",
  );
  await page
    .getByText("What is the difference between discovery and testing?", {
      exact: false,
    })
    .click();
  await expect(page.locator(".faq-list details").first()).not.toHaveAttribute(
    "open",
    "",
  );
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(
    page.getByRole("button", { name: "Pause feature animation" }),
  ).toBeDisabled();
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.reload();
    await expect(page.locator(".welcome-faq")).toBeAttached();
    for (const section of await page
      .locator(
        ".welcome > section, .welcome-story, .welcome-process, .welcome-faq",
      )
      .all()) {
      await section.scrollIntoViewIfNeeded();
    }
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    await page.evaluate(() => {
      (document.activeElement as HTMLElement)?.blur();
      window.scrollTo(0, 0);
    });
    await page.screenshot({
      path: `test-results/welcome-expanded-${width}.png`,
      fullPage: true,
    });
  }
});

test("overview, navigation and real API contract rendering", async ({
  page,
}) => {
  await mock(page);
  await page.goto("/dashboard");
  await expect(
    page.getByRole("heading", { name: "A clearer picture." }),
  ).toBeVisible();
  await expect(page.getByText("testq/storefront")).toBeVisible();
  await expect(page.getByText("80%", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "testq/storefront" }).click();
  await expect(
    page.getByRole("heading", { name: "testq/storefront" }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Application map" }).click();
  await expect(
    page.getByRole("heading", { name: "Storefront", exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Test results" }).click();
  await page.getByText("Homepage responds").click();
  await expect(page.getByText("Expected status 200")).toBeVisible();
  await page.getByRole("tab", { name: "Strategy", exact: true }).click();
  await expect(page.getByText("Verify checkout navigation")).toBeVisible();
  await page.getByRole("tab", { name: "Test plan", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "1 test definitions" }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Logs" }).click();
  await expect(page.getByText("Server ready")).toBeVisible();
});
test("new run dialog validates input and submits chosen mode", async ({
  page,
}) => {
  await mock(page);
  await page.goto("/dashboard");
  await page.getByRole("button", { name: "New test run", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByLabel("GitHub repository").fill("https://example.com/test");
  await page.getByRole("button", { name: "Start run", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("public GitHub");
  await page
    .getByLabel("GitHub repository")
    .fill("https://github.com/testq/storefront");
  const request = page.waitForRequest(
    (r) => r.method() === "POST" && r.url().endsWith("/api/test-runs"),
  );
  await page.getByRole("button", { name: "Start run", exact: true }).click();
  expect((await request).postDataJSON()).toEqual({
    repository_url: "https://github.com/testq/storefront",
    branch: null,
    discover: true,
    testing_enabled: true,
  });
  await expect(page).toHaveURL(/runs\/run-example/);
  await expect(page.getByRole("dialog")).not.toBeVisible();
});
test("mobile navigation and layouts do not overflow", async ({ page }) => {
  await mock(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dashboard");
  await page
    .getByRole("button", { name: "Open navigation", exact: true })
    .click();
  await page.getByRole("link", { name: "Projects", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Your projects." }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.goto("/welcome");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.waitForTimeout(1400);
  for (const section of await page
    .locator(".welcome-approach .workflow-step, .welcome-cta")
    .all()) {
    await section.scrollIntoViewIfNeeded();
    await page.waitForTimeout(650);
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(400);
  await page.screenshot({ path: "test-results/mobile.png", fullPage: true });
});
test("offline errors are honest and retryable", async ({ page }) => {
  await page.route("**/api/**", (r) =>
    r.fulfill({ status: 503, json: { detail: "Backend unavailable" } }),
  );
  await page.route("**/health", (r) => r.fulfill({ status: 503 }));
  await page.goto("/dashboard");
  await expect(page.getByRole("alert")).toContainText("Backend unavailable");
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  await expect(page.getByText("Backend offline")).toBeVisible();
});
test("keyboard modal, reduced motion, accessibility and desktop capture", async ({
  page,
}) => {
  await mock(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/dashboard");
  await page.getByRole("button", { name: "New test run", exact: true }).click();
  await expect(page.getByLabel("GitHub repository")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(
    page.getByRole("button", { name: "New test run", exact: true }),
  ).toBeFocused();
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(result.violations).toEqual([]);
  await page.screenshot({ path: "test-results/desktop.png", fullPage: true });
});

test("empty workspace and missing routes are useful", async ({ page }) => {
  await mock(page);
  await page.route("**/api/test-runs?*", (r) =>
    r.fulfill({ json: { runs: [], total: 0 } }),
  );
  await page.goto("/dashboard");
  await expect(
    page.getByRole("heading", {
      name: "Your first run is a good place to start.",
    }),
  ).toBeVisible();
  await page.goto("/not-a-page");
  await expect(
    page.getByRole("heading", { name: /This page took/ }),
  ).toBeVisible();
  await page.getByRole("link", { name: /Back to your workspace/ }).click();
  await expect(page).toHaveURL("/dashboard");
});
test("API errors remain in the new run form", async ({ page }) => {
  await mock(page);
  await page.route("**/api/test-runs", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({
          status: 400,
          json: { detail: "Repository not supported" },
        })
      : route.fallback(),
  );
  await page.goto("/dashboard");
  await page.getByRole("button", { name: "New test run", exact: true }).click();
  await page
    .getByLabel("GitHub repository")
    .fill("https://github.com/example/repo");
  await page.getByRole("button", { name: "Start run", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Repository not supported",
  );
  await expect(page.getByRole("dialog")).toBeVisible();
});
test("cancellation calls API and cannot leave a stale active run", async ({
  page,
}) => {
  await mock(page);
  let cancelled = false;
  await page.route("**/api/test-runs/run-example", (route) =>
    route.fulfill({
      json: {
        ...run,
        status: cancelled ? "CANCELLED" : "BUILDING",
        finished_at: cancelled ? run.finished_at : null,
        cancellation_requested: cancelled,
      },
    }),
  );
  await page.route("**/api/test-runs/run-example/cancel", (route) => {
    cancelled = true;
    return route.fulfill({
      json: { ...run, status: "CANCELLED", cancellation_requested: true },
    });
  });
  page.on("dialog", (dialog) => dialog.accept());
  await page.goto("/runs/run-example");
  await page.getByRole("button", { name: "Cancel run", exact: true }).click();
  await expect(page.locator(".heading-actions .status")).toContainText(
    "cancelled",
  );
  await expect(
    page.getByRole("button", { name: "Cancel run", exact: true }),
  ).not.toBeVisible();
  expect(cancelled).toBeTruthy();
});
test("dialog, mobile drawer and welcome accessibility", async ({ page }) => {
  await mock(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/dashboard");
  await page.getByRole("button", { name: "New test run", exact: true }).click();
  const dialog = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(
    dialog.violations.map((v) => ({
      id: v.id,
      targets: v.nodes.map((n) => n.target),
    })),
  ).toEqual([]);
  await page.keyboard.press("Escape");
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole("button", { name: "Open navigation", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Workspace navigation" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "Open navigation", exact: true }),
  ).toBeFocused();
  await page.goto("/welcome");
  const welcome = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(
    welcome.violations.map((v) => ({
      id: v.id,
      targets: v.nodes.map((n) => n.target),
    })),
  ).toEqual([]);
});
