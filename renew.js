const { chromium } = require('playwright');
const axios = require('axios');
const fs = require('fs');

// 从环境变量读取 Secrets
const EMAIL = process.env.ZAMPTO_EMAIL ? process.env.ZAMPTO_EMAIL.trim() : '';
const PASSWORD = process.env.ZAMPTO_PASSWORD ? process.env.ZAMPTO_PASSWORD.trim() : '';
const TG_BOT_TOKEN = process.env.TG_BOT_TOKEN ? process.env.TG_BOT_TOKEN.trim() : '';
const TG_CHAT_ID = process.env.TG_CHAT_ID ? process.env.TG_CHAT_ID.trim() : '';
const PROXY_SOCKS5 = process.env.PROXY_SOCKS5 ? process.env.PROXY_SOCKS5.trim() : '';

async function sendTelegramNotification(text, screenshotPath = null) {
    if (!TG_BOT_TOKEN || !TG_CHAT_ID) {
        console.log("Telegram 配置缺失，跳过通知。");
        return;
    }

    try {
        const url = `https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage`;
        await axios.post(url, { chat_id: TG_CHAT_ID, text: text });
    } catch (e) {
        console.error(`发送 TG 文本失败: ${e.message}`);
    }

    if (screenshotPath && fs.existsSync(screenshotPath)) {
        try {
            const url = `https://api.telegram.org/bot${TG_BOT_TOKEN}/sendPhoto`;
            const FormData = require('form-data');
            const form = new FormData();
            form.append('chat_id', TG_CHAT_ID);
            form.append('photo', fs.createReadStream(screenshotPath));
            await axios.post(url, form, { headers: form.getHeaders() });
        } catch (e) {
            console.error(`发送 TG 截图失败: ${e.message}`);
        }
    }
}

// --- 【复刻核心】老项目过 CF Turnstile 人机验证逻辑的 Playwright 版实现 ---
async function handleTurnstilePlaywright(page) {
    try {
        await page.waitForTimeout(2000);
        // 复刻老代码的检测逻辑：document.querySelector("input[name='cf-turnstile-response']")
        const hasTurnstile = await page.evaluate(() => document.querySelector("input[name='cf-turnstile-response']") !== null);
        
        if (!hasTurnstile) {
            return true; // 如果不需要验证，直接跳过
        }
        
        console.log("[INFO] 核心复刻：检测到 Cloudflare Turnstile 验证框，开始尝试穿透点击...");
        
        // 准确定位 CF 的 iframe 并进行物理模拟点击
        const cfFrame = page.frameLocator('iframe[src*="challenges.cloudflare.com"]').first();
        const checkbox = cfFrame.locator('#challenge-stage, .mark, input[type="checkbox"]').first();
        
        if (await checkbox.isVisible({ timeout: 4000 })) {
            console.log("[INFO] 找到 CF 勾选复选框，正在模拟真实物理点击...");
            await checkbox.click({ force: true });
            await page.waitForTimeout(5000);
        } else {
            console.log("[WARN] 未能在 iframe 内找到明确的勾选元素，尝试直接点击整个挑战区域...");
            const cfContainer = page.locator('div[id*="cf-v4-container"], iframe[src*="challenges.cloudflare.com"]').first();
            if (await cfContainer.isVisible()) {
                await cfContainer.click({ force: true });
                await page.waitForTimeout(5000);
            }
        }
        return true;
    } catch (e) {
        console.log(`[WARN] 尝试处理 CF 验证时跳过或失败: ${e.message}`);
        return false;
    }
}

(async () => {
    if (!EMAIL || !PASSWORD) {
        console.error("错误: 未配置账号或密码环境变量！");
        return;
    }

    let statusMsg = "🏷️ [ZAMPTO] 续期任务开始 (Playwright+CF防御版)...\n";
    const screenshotPath = "result.png";

    // 配置浏览器代理
    const launchOptions = { headless: true };
    if (PROXY_SOCKS5) {
        console.log(`正在应用代理服务器: ${PROXY_SOCKS5}`);
        launchOptions.proxy = { server: PROXY_SOCKS5 };
    }

    const browser = await chromium.launch(launchOptions);
    
    // 保持横屏 1024x768 分辨率（既保证截图清晰，又不易触发坚屏移动端UI崩溃）
    const context = await browser.newContext({
        viewport: { width: 1024, height: 768 },
        userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    });
    const page = await context.newPage();

    try {
        // =================================================================
        // 阶段 1：已搞好的登录操作与验证（保持不变）
        // =================================================================
        console.log("正在访问登录页面...");
        await page.goto("https://dash.zampto.net/auth/login", { waitUntil: "networkidle" });
        await page.waitForTimeout(4000);

        // 处理登录前的隐私提示框
        const privacySelectors = ["text=Accept All", "text=Allow", "text=Agree", "button:has-text('Accept')"];
        for (const selector of privacySelectors) {
            try {
                const element = page.locator(selector).first();
                if (await element.isVisible({ timeout: 1500 })) {
                    await element.click();
                    console.log(`已自动处理隐私弹窗: ${selector}`);
                    break;
                }
            } catch (e) {}
        }

        // 输入 Email 并强刷 React 状态
        console.log("正在输入 Email...");
        const emailInput = page.locator("#email");
        await emailInput.waitFor({ state: "visible", timeout: 8000 });
        await emailInput.focus();
        await emailInput.fill(EMAIL);
        await emailInput.type(" ", { delay: 50 });
        await page.keyboard.press('Backspace');
        await emailInput.evaluate((el, val) => {
            el.value = val;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }, EMAIL);

        // 输入 Password 并强刷 React 状态
        console.log("正在输入 Password...");
        const passwordInput = page.locator("#password");
        await passwordInput.focus();
        await passwordInput.fill(PASSWORD);
        await passwordInput.type(" ", { delay: 50 });
        await page.keyboard.press('Backspace');
        await passwordInput.evaluate((el, val) => {
            el.value = val;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }, PASSWORD);

        await page.waitForTimeout(2000);

        // 提交登录
        console.log("尝试点击登录按钮...");
        let loginBtn = page.locator("button[type='submit']").first();
        await loginBtn.waitFor({ state: "visible", timeout: 5000 });
        await loginBtn.click({ force: true });

        // 验证跳转
        console.log("等待登录跳转结果...");
        await page.waitForTimeout(6000);
        await page.waitForLoadState("networkidle");

        if (page.url().includes("/auth/login")) {
            console.log("仍停留在登录页，尝试在密码框按下 Enter 键直接提交...");
            await page.focus("#password");
            await page.keyboard.press("Enter");
            await page.waitForTimeout(6000);
            await page.waitForLoadState("networkidle");
        }

        if (page.url().includes("/auth/login")) {
            throw new Error("登录失败：仍停留在登录页面。");
        }

        console.log("✅ 登录成功，通过第一阶段。");
        statusMsg += "✅ 成功登录控制台。\n";

        // =================================================================
        // 阶段 2：已搞好的访问控制台目标服务器（保持不变）
        // =================================================================
        console.log("正在跳转到服务器续期页面...");
        await page.goto("https://dash.zampto.net/server?id=6932", { waitUntil: "networkidle" });
        await page.waitForTimeout(5000);

        // 处理内页出现的 Google 隐私同意弹窗
        console.log("检测并处理内页隐私询问框...");
        const innerPrivacySelectors = ["button.fc-cta-consent", ".fc-consent-root button"];
        for (const selector of innerPrivacySelectors) {
            try {
                const btn = page.locator(selector).first();
                if (await btn.isVisible({ timeout: 2000 })) {
                    await btn.evaluate(el => el.click());
                    await page.waitForTimeout(2000);
                    break;
                }
            } catch (e) {}
        }

        // =================================================================
        // 阶段 3：点击 Renew 按钮 并在此时【引入复刻的 CF 验证过检逻辑】
        // =================================================================
        const renewBtn = page.locator("button:has-text('Renew Server')").first();

        if (!(await renewBtn.isVisible({ timeout: 5000 }))) {
            throw new Error("未找到续期按钮：页面加载成功，但未能在当前页面上找到 'Renew Server' 按钮。");
        }

        console.log("找到 Renew 按钮，准备点击...");
        try {
            await renewBtn.scrollIntoViewIfNeeded();
            await renewBtn.click({ force: true, timeout: 3000 });
        } catch (e) {
            await renewBtn.evaluate(el => el.click());
        }

        console.log("✅ 成功触发 Renew 按钮。");
        
        // 【核心引入点】点击后立刻执行复刻老脚本的 CF 人机过检函数
        console.log("正在唤醒复刻的 Cloudflare 过检机制...");
        await handleTurnstilePlaywright(page);

        statusMsg += "✅ 已触发 Renew 按钮并处理二次验证，等待操作框完成...\n";
        await page.waitForTimeout(12000);

        // 检查续期后的有效时间
        try {
            const expiryLocator = page.locator("div:has-text('Expiry (Next Renewal):') >> span.font-medium");
            if (await expiryLocator.isVisible({ timeout: 5000 })) {
                const expiryTime = (await expiryLocator.innerText()).trim();
                statusMsg += `⏳ 续期后有效时间: ${expiryTime}\n`;
            } else {
                statusMsg += "⚠️ 未找到有效时间显示元素。\n";
            }
        } catch (exTime) {
            statusMsg += `⚠️ 获取有效时间失败: ${exTime.message}\n`;
        }

        statusMsg += "🎉 续期操作完成。";

    } catch (e) {
        statusMsg += `❌ 脚本运行中断: ${e.message}`;
        console.error(statusMsg);
    } finally {
        try {
            await page.screenshot({ path: screenshotPath, fullPage: true });
            console.log("当前现场截图已保存。");
        } catch (e) {
            console.error(`截图失败: ${e.message}`);
        }

        await context.close();
        await browser.close();
    }

    // 最终通知
    await sendTelegramNotification(statusMsg, screenshotPath);
})();
