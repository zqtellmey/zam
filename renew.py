import os
import time
import requests
from playwright.sync_api import sync_playwright

# 从 GitHub Secrets 中读取环境变量
EMAIL = os.environ.get("ZAMPTO_EMAIL")
PASSWORD = os.environ.get("ZAMPTO_PASSWORD")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

def send_telegram_notification(text, screenshot_path=None):
    """发送文字日志和截图到 Telegram"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("Telegram 配置缺失，跳过通知。")
        return

    # 发送文本
    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text})
    except Exception as e:
        print(f"发送 TG 文本失败: {e}")

    # 发送截图
    if screenshot_path and os.path.exists(screenshot_path):
        try:
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
            with open(screenshot_path, "rb") as photo:
                requests.post(url, data={"chat_id": TG_CHAT_ID}, files={"photo": photo})
        except Exception as e:
            print(f"发送 TG 截图失败: {e}")

def run():
    if not EMAIL or not PASSWORD:
        print("错误: 未配置账号或密码环境变量！")
        return

    status_msg = "🚀 Zampto 续期任务开始...\n"
    screenshot_path = "result.png"

    with sync_playwright() as p:
        # 在 GitHub 环境中必须使用 headless=True
        browser = p.chromium.launch(headless=True)
        # 模拟真实的浏览器环境，避免被识别为机器人
        context = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # 【去广告/拦截操作】拒绝常见的广告、追踪器域名，加快加载速度
        def block_ads(route):
            url = route.request.url
            ad_keywords = ["google-analytics", "doubleclick", "adservice", "analytics", "adsense"]
            if any(kw in url for kw in ad_keywords):
                route.abort()
            else:
                route.continue_()
        
        page.route("**/*", block_ads)

        try:
            # 1. 访问登录页面
            print("正在访问登录页面...")
            page.goto("https://dash.zampto.net/auth/login", wait_until="networkidle")
            
            # 【处理欧洲 IP 隐私提示框】
            # 常见的隐私合规弹窗通常带有 "Accept", "Allow", "Agree", "Consent" 或 "允许" 字样
            # 这里采用强鲁棒性的文本模糊匹配，如果检测到则点击
            privacy_selectors = [
                "text=Accept All", "text=Allow", "text=Agree", "text=Consent", 
                "text=允许", "button:has-text('Accept')", "button:has-text('Allow')"
            ]
            for selector in privacy_selectors:
                try:
                    element = page.locator(selector).first
                    if element.is_visible(timeout=2000):
                        element.click()
                        print(f"已自动处理隐私弹窗: {selector}")
                        page.wait_for_timeout(1000)
                        break
                except:
                    continue

            # 2. 登录操作 (使用 ID 定位，非常鲁棒)
            print("输入账号密码...")
            page.fill("#email", EMAIL)
            page.fill("#password", PASSWORD)
            
            # Login 按钮定位：抛弃动态 XPATH，改用按钮类型、文本内容和特征类名组合定位
            login_btn = page.locator("button[type='submit']:has-text('Login')")
            login_btn.click()
            
            # 等待登录跳转完成
            page.wait_for_load_state("networkidle")
            print("登录表单已提交。")

            # 3. 访问服务器管理页面
            print("正在访问服务器续期页面...")
            page.goto("https://dash.zampto.net/server?id=6932", wait_until="networkidle")
            page.wait_for_timeout(3000) # 额外等待 3 秒确保内层异步组件加载

            # 4. 寻找并点击 Renew 按钮
            # 鲁棒性定位方案：通过按钮内的文本 'Renew Server' 配合元素类型进行绝对匹配
            renew_btn = page.locator("button:has-text('Renew Server')").first

            if renew_btn.is_visible(timeout=5000):
                print("找到 Renew 按钮，准备点击...")
                renew_btn.click()
                status_msg += "✅ 成功触发 Renew 按钮。\n"
                
                # 5. 等待操作框完成（根据要求等待 10 来秒）
                print("已点击续期，等待 12 秒让操作框完成...")
                page.wait_for_timeout(12000)
                status_msg += "🎉 续期等待结束。"
            else:
                status_msg += "❌ 未能在页面上找到 'Renew Server' 按钮，可能已处于续期状态或登录失效。"

        except Exception as e:
            status_msg += f"💥 脚本运行发生异常: {str(e)}"
            print(status_msg)
        finally:
            # 无论成功失败，保存最终截图
            try:
                page.screenshot(path=screenshot_path, full_page=True)
                print("截图已保存。")
            except Exception as e:
                print(f"截图失败: {e}")
                screenshot_path = None
            
            # 关闭浏览器
            context.close()
            browser.close()

    # 任务结束，发送通知
    send_telegram_notification(status_msg, screenshot_path)

if __name__ == "__main__":
    run()
