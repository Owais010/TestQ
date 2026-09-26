import { test, expect } from "@playwright/test";
test("live backend workspace and retained run", async ({ page, request }) => {
  test.skip(
    process.env.TESTQ_LIVE !== "1",
    "Opt-in read-only live backend check",
  );
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const response = await request.get("/api/test-runs?limit=12&offset=0");
  expect(response.ok()).toBeTruthy();
  const data = await response.json();
  await page.goto("/dashboard");
  await expect(
    page.getByRole("heading", { name: "A clearer picture." }),
  ).toBeVisible();
  await page.waitForTimeout(1800);
  await page.locator(".workflow").scrollIntoViewIfNeeded();
  await page.waitForTimeout(700);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "test-results/live-desktop.png",
    fullPage: true,
  });
  if (data.runs.length) {
    await page.goto(`/runs/${data.runs[0].id}`);
    await expect(page.getByRole("tab", { name: "Evidence" })).toBeVisible();
    await page.getByRole("tab", { name: "Evidence", exact: true }).click();
    const evidence = await request.get(
      `/api/test-runs/${data.runs[0].id}/evidence`,
    );
    expect(evidence.ok()).toBeTruthy();
    const retained = await evidence.json();
    if (retained.evidence.length) {
      const download = page.waitForEvent("download");
      await page
        .getByRole("link", { name: /^Download / })
        .first()
        .click();
      const artifact = await download;
      expect(await artifact.failure()).toBeNull();
      expect(await artifact.path()).toBeTruthy();
    }
    await page.getByRole("tab", { name: "Logs" }).click();
    await expect(
      page.getByRole("heading", { name: /Execution journal/ }),
    ).toBeVisible();
    await page.screenshot({
      path: "test-results/live-run.png",
      fullPage: true,
    });
  }
  await page.goto("/welcome");
  await page.waitForTimeout(1200);
  for (const section of await page
    .locator(".welcome-approach .workflow-step, .welcome-cta")
    .all()) {
    await section.scrollIntoViewIfNeeded();
    await page.waitForTimeout(650);
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(400);
  await page.screenshot({
    path: "test-results/live-welcome.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
