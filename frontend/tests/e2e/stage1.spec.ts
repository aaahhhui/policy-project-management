import { expect, test, type Page } from "@playwright/test";

const owner = {
  login: process.env.E2E_OWNER_LOGIN ?? "owner",
  password: process.env.E2E_OWNER_PASSWORD ?? "change-owner-password",
};
const reader = {
  login: process.env.E2E_READER_LOGIN ?? "reader",
  password: process.env.E2E_READER_PASSWORD ?? "change-reader-password",
};

async function login(page: Page, credentials = owner): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("账号").fill(credentials.login);
  await page.getByLabel("密码").fill(credentials.password);
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page.getByRole("link", { name: "政策中心" })).toBeVisible();
}

async function expectNoDocumentOverflow(page: Page): Promise<void> {
  const hasOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(hasOverflow).toBe(false);
}

test("owner sees source navigation and reader does not", async ({ browser }) => {
  const ownerPage = await browser.newPage();
  await login(ownerPage);
  await expect(ownerPage.getByRole("link", { name: "政策来源" })).toBeVisible();
  await ownerPage.close();

  const readerPage = await browser.newPage();
  await login(readerPage, reader);
  await expect(readerPage.getByRole("link", { name: "政策来源" })).toHaveCount(0);
  await readerPage.close();
});

test("policy filters update the URL and result set", async ({ page }) => {
  await login(page);
  await page.goto("/policies");
  await expect(page.getByRole("heading", { name: "政策中心" })).toBeVisible();
  const initialPolicyLinks = page.locator(".policy-name a");
  expect(await initialPolicyLinks.count()).toBeGreaterThan(0);

  await page.getByLabel("搜索政策").fill("__stage1_no_matching_policy__");
  await page.getByRole("button", { name: "筛选" }).click();

  await expect(page).toHaveURL(/q=__stage1_no_matching_policy__/);
  await expect(page.getByText("没有符合条件的政策。")).toBeVisible();
  await expect(initialPolicyLinks).toHaveCount(0);
});

test("policy detail exposes traceability and three entity evaluations", async ({ page }) => {
  await login(page);
  await page.goto("/policies");
  const firstPolicy = page.locator(".policy-name a").first();
  await expect(firstPolicy).toBeVisible();
  await firstPolicy.click();

  await expect(page.getByRole("link", { name: "查看官方原文" }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "原始网页快照" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "附件" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "版本历史" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "北京适创科技有限公司" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "苏州数算软云科技有限公司" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "深圳适创腾扬科技有限公司" })).toBeVisible();
});

test("login, enterprise profile, and policy detail do not overflow at 390x844", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "登录工作台" })).toBeVisible();
  await expectNoDocumentOverflow(page);

  await login(page);
  await page.goto("/profile");
  await expect(page.getByRole("heading", { name: "企业档案" })).toBeVisible();
  await expect(page.getByText("北京适创科技有限公司")).toBeVisible();
  await expectNoDocumentOverflow(page);

  await page.goto("/policies");
  const firstPolicy = page.locator(".policy-name a").first();
  await expect(firstPolicy).toBeVisible();
  await firstPolicy.click();
  await expect(page.getByRole("heading", { name: "政策正文" })).toBeVisible();
  await expectNoDocumentOverflow(page);
});
