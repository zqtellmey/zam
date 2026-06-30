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

    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text})
    except Exception as e:
        print(f"发送 TG 文本失败: {e}")

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

    status_msg = "🏷️ [ZAMPTO] 续期任务开始...\n"
    screenshot_path = "result.png"
    is_success = False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # 【去广告/拦截操作】
        def block_ads(route):
            url = route.request.url
            ad_keywords = ["google-analytics", "doubleclick", "adservice", "analytics", "adsense"]
            if any(kw in url for kw in ad_keywords):
                route.abort()
            else:
                route.continue_()
        
        page.route("**/*", block_ads)

        try:
            # =================================================================
            # 阶段 1：登录操作与验证
            # =================================================================
            print("正在访问登录页面...")
            page.goto("https://dash.zampto.net/auth/login", wait_until="networkidle")
            
            # 处理欧洲 IP 隐私提示框
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

            print("输入账号密码...")
            page.fill("#email", EMAIL)
            page.fill("#password", PASSWORD)
            page.wait_for_timeout(1000)
            
            print("尝试点击登录按钮...")
            login_btn = page.locator("button[type='submit']:has-text('Login')").first
            if not login_btn.is_visible():
                login_btn = page.locator("button[type='submit']").first

            login_btn.wait_for(state="visible", timeout=5000)
            login_btn.click(force=True) 
            
            # 兜底回车提交
            page.wait_for_timeout(2000)
            if page.url.endswith("/auth/login"): 
                print("点击可能未触发，尝试在密码框按下 Enter 键...")
                page.press("#password", "Enter")

            # 【核心检查点】等待并判断是否成功脱离登录页
            print("等待登录结果...")
            page.wait_for_load_state("networkidle")
            
            # 如果当前 URL 仍然包含 '/auth/login'，说明登录被拦截或失败了
            if "/auth/login" in page.url:
                raise Exception("登录失败：表单提交后未能成功跳转，仍停留在登录页面。请检查账号密码、验证码或登录按钮点击是否生效。")
            
            print("✅ 登录成功，成功通过第一阶段。")
            status_msg += "✅ 成功登录控制台。\n"

            # =================================================================
            # 阶段 2：访问控制台目标服务器
            # =================================================================
            print("正在跳转到服务器续期页面...")
            page.goto("https://dash.zampto.net/server?id=6932", wait_until="networkidle")
            page.wait_for_timeout(4000) # 给内层组件充分的渲染时间

            # 【核心检查点】判断是否被踢回登录页，或者服务器页面加载失败
            if "/auth/login" in page.url:
                raise Exception("登录态失效：访问服务器页面时被重新定向到了登录页。")

            # =================================================================
            # 阶段 3：寻找并执行 Renew
            # =================================================================
            renew_btn = page.locator("button:has-text('Renew Server')").first

            if not renew_btn.is_visible(timeout=5000):
                raise Exception("未找到续期按钮：页面加载成功，但未能在当前页面上找到 'Renew Server' 按钮。可能已经处于续期最大时限，或页面结构发生变化。")
                
            print("找到 Renew 按钮，准备点击...")
            renew_btn.click(force=True)
            status_msg += "✅ 成功触发 Renew 按钮，正在等待操作框完成...\n"
            
            # 等待操作框完成（根据要求等待 12 秒）
            print("已点击续期，等待 12 秒让操作框完成...")
            page.wait_for_timeout(12000)
            
            # 检查续期后的有效时间
            try:
                expiry_locator = page.locator("div:has-text('Expiry (Next Renewal):') >> span.font-medium")
                if expiry_locator.is_visible(timeout=5000):
                    expiry_time = expiry_locator.inner_text().strip()
                    status_msg += f"⏳ 续期后有效时间: {expiry_time}\n"
                    print(f"成功获取到有效时间: {expiry_time}")
                else:
                    status_msg += "⚠️ 未找到有效时间显示元素（可能续期动作未产生界面刷新）。\n"
            except Exception as ex_time:
                status_msg += f"⚠️ 获取有效时间失败: {str(ex_time)}\n"
            
            status_msg += "🎉 续期操作完成。"
            is_success = True

        except Exception as e:
            # 捕获任何一个阶段抛出的显式异常
            status_msg += f"❌ 脚本运行中断: {str(e)}"
            print(status_msg)
        finally:
            # 无论成功还是中途失败，立刻截取当前最后一幕的现场画面
            try:
                page.screenshot(path=screenshot_path, full_page=True)
                print("当前现场截图已保存。")
            except Exception as e:
                print(f"截图失败: {e}")
                screenshot_path = None
            
            context.close()
            browser.close()

    # 将最终的（带有错误阶段原因的）文本和错误现场截图发送到 TG
    send_telegram_notification(status_msg, screenshot_path)

if __name__ == "__main__":
    run()
