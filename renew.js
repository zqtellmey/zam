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

    // 发送文本
    try {
        const url = `https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage`;
        await axios.post(url, { chat_id: TG_CHAT_ID, text: text });
    } catch (e) {
        console.error(`发送 TG 文本失败: ${e.message}`);
    }

    // 发送截图
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

(async () => {
    if (!EMAIL || !PASSWORD) {
        console.error("错误: 未配置账号或密码环境变量！");
        return;
    }

    let statusMsg = "🏷️ [ZAMPTO] 续期任务开始 (JS高级版)...\n";
    const screenshotPath = "result.png";

    // 配置浏览器代理（打通 YAML 的代理设定）
    const launchOptions = { headless: true };
    if (PROXY_SOCKS5) {
        console.log(`正在应用代理服务器: ${PROXY_SOCKS5}`);
        launchOptions.proxy = { server: PROXY_SOCKS5 };
    } else {
        console.log("未检测到代理变量，将使用直连模式运行。");
    }

    const browser = await chromium.launch(launchOptions);
    const context = await browser.newContext({
        viewport: { width: 1280, height: 800 },
        userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    });
    const page = await context.newPage();

    try {
        // =================================================================
        // 阶段 1：登录操作与验证
        // =================================================================
        console.log("正在访问登录页面...");
        await page.goto("https://dash.zampto.net/auth/login", { waitUntil: "networkidle" });
        await page.waitForTimeout(4000);

        // --- 强力输入 Email 且强刷 React 框架状态 ---
        console.log("正在输入 Email 并强制同步 React 状态...");
        const emailInput = page.locator("#email");
        await emailInput.waitFor({ state: "visible", timeout: 8000 });
        await emailInput.focus();
        await emailInput.fill(EMAIL); // 先用 fill 强填
        await emailInput.type(" ", { delay: 100 }); // 敲一个空格再删掉，刺激框架监听
        await page.keyboard.press('Backspace');
        
        // 核心：利用底层 JS 派发 input 和 change 事件，攻破 Next.js 的虚拟 DOM 状态阻挡
        await emailInput.evaluate((el, val) => {
            el.value = val;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }, EMAIL);

        // --- 强力输入 Password 且强刷 React 框架状态 ---
        console.log("正在输入 Password 并强制同步 React 状态...");
        const passwordInput = page.locator("#password");
        await passwordInput.focus();
        await passwordInput.fill(PASSWORD);
        await passwordInput.type(" ", { delay: 100 });
        await page.keyboard.press('Backspace');

        await passwordInput.evaluate((el, val) => {
            el.value = val;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }, PASSWORD);

        await page.waitForTimeout(2000);

        // --- 提交登录 ---
        console.log("尝试点击登录按钮...");
        // 根据源码，登录按钮有 data-slot="button" 且属于 submit 类型
        let loginBtn = page.locator("button[type='submit']").first();
        await loginBtn.waitFor({ state: "visible", timeout: 5000 });
        
        // 真实物理点击
        await loginBtn.click({ force: true });

        // 【核心检查点】验证是否脱离登录页
        console.log("等待登录跳转结果...");
        await page.waitForTimeout(6000);
        await page.waitForLoadState("networkidle");

        if (page.url().includes("/auth/login")) {
            // 兜底策略：如果点击按钮后因为非主流原因没反应，直接在密码框敲回车提交表单
            console.log("仍停留在登录页，尝试在密码框按下 Enter 键直接提交...");
            await page.focus("#password");
            await page.keyboard.press("Enter");
            await page.waitForTimeout(6000);
            await page.waitForLoadState("networkidle");
        }

        if (page.url().includes("/auth/login")) {
            throw new Error("登录失败：仍停留在登录页面。值可能已被清空或遭防火墙拦截，请检查 TG 截图。");
        }

        console.log("✅ 登录成功，通过第一阶段。");
        statusMsg += "✅ 成功登录控制台。\n";

        // =================================================================
        // 阶段 2：访问控制台目标服务器
        // =================================================================
        console.log("正在跳转到服务器续期页面...");
        await page.goto("https://dash.zampto.net/server?id=6932", { waitUntil: "networkidle" });
        await page.waitForTimeout(6000);

        if (page.url().includes("/auth/login")) {
            throw new Error("登录态失效：访问服务器页面时被重新定向到了登录页。");
        }

        // =================================================================
        // 阶段 3：寻找并执行 Renew
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

        statusMsg += "✅ 成功触发 Renew 按钮，正在等待操作框完成...\n";
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
