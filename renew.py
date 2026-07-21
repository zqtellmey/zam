#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zampto 自动续期脚本 - 初始登录页截图通知 + 双重 CF 穿透机制 + 登录页 CF 验证接入焊死版
"""

import os
import sys
import time
import platform
import requests
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from seleniumbase import SB

# --- 全局配置 ---
TARGET_SIDS = ["6932"]
AUTH_URL = "https://dash.zampto.net/auth/login"
SERVER_URL = "https://dash.zampto.net/server?id={}"
OUTPUT_DIR = Path("output/screenshots")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CN_TZ = timezone(timedelta(hours=8))

# --- 从环境读取变量 ---
EMAIL = os.environ.get("ZAMPTO_EMAIL", "").strip()
PASSWORD = os.environ.get("ZAMPTO_PASSWORD", "").strip()
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "").strip()
PROXY_SOCKS5 = os.environ.get("PROXY_SOCKS5", "").strip()

# --- 看门狗安全中断 ---
def watchdog(timeout_seconds: int):
    time.sleep(timeout_seconds)
    print(f"\n[WATCHDOG] 脚本执行超过 {timeout_seconds}s，正在执行暴力中断...")
    os._exit(0)

def cn_now() -> datetime:
    return datetime.now(CN_TZ)

def cn_time_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return cn_now().strftime(fmt)

def is_linux(): 
    return platform.system().lower() == "linux"

# --- 设置纵向超长虚拟桌面 (焊死不变) ---
def setup_display():
    if is_linux() and not os.environ.get("DISPLAY"):
        try:
            from pyvirtualdisplay import Display
            d = Display(visible=False, size=(1280, 2400))
            d.start()
            os.environ["DISPLAY"] = d.new_display_var
            print("[INFO] 🖥️ Xvfb 虚拟纵向长屏桌面已成功启动 (1280x2400)")
            return d
        except Exception as e:
            print(f"[ERROR] 虚拟显示启动失败: {e}")
            sys.exit(1)
    return None

def shot(name: str) -> str:
    return str(OUTPUT_DIR / f"{cn_now().strftime('%H%M%S')}-{name}.png")

def notify(ok: bool, stage: str, msg: str = "", img: str = None):
    if not TG_BOT_TOKEN or not TG_CHAT_ID: 
        print("[WARN] TG 配置缺失，跳过通知。")
        return
    try:
        text = f"🔔 Zampto: {'✅' if ok else '❌'} {stage}\n{msg}\n⏰ {cn_time_str()}"
        requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", json={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
        if img and Path(img).exists():
            with open(img, "rb") as f:
                requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto", data={"chat_id": TG_CHAT_ID}, files={"photo": f}, timeout=15)
    except Exception as e: 
        print(f"[ERROR] 发送 TG 通知失败: {e}")

# --- 双重循环过检机制 (焊死不变) ---
def handle_turnstile_exact_replica(sb) -> bool:
    try:
        # 进行 2 轮循环检测与调度穿透，确保拦截层加载彻底，防止漏检
        for attempt in range(1, 3):
            print(f"[INFO] ⏱️ [第 {attempt} 轮检测] 预留 5 秒等待 Cloudflare 拦截层加载...")
            sb.sleep(5)
            
            has_turnstile = sb.execute_script('return document.querySelector("input[name=\'cf-turnstile-response\']") !== null')
            
            if has_turnstile: 
                print(f"[INFO] 🛡️ [第 {attempt} 轮] 发现 Cloudflare Turnstile 人机验证框！")
                sb.save_screenshot(shot(f"cf_detected_attempt_{attempt}"))
                
                print(f"[INFO] ⚡ [第 {attempt} 轮] 正在启动物理级 uc_gui_click_captcha() 穿透点击...")
                sb.uc_gui_click_captcha()
                
                print(f"[INFO] ⏳ [第 {attempt} 轮] 物理点击完成，等待 5 秒让状态同步...")
                sb.sleep(5)
            else:
                print(f"[INFO] 🟢 [第 {attempt} 轮] 当前节点未检测到 CF 拦截框。")
        
        return True
    except Exception as e: 
        print(f"[WARN] 穿透 CF 验证时发生非致命异常: {e}")
        return False

# --- 完美移植自 JS 版本的隐私窗消除逻辑 (焊死不变) ---
def handle_privacy_modal(sb):
    try:
        for selector in ["button.fc-cta-consent", "button[aria-label='Consent']", ".fc-consent-root button", "text=Accept All", "button:has-text('Accept')"]:
            if sb.is_element_visible(selector):
                sb.click(selector)
                print(f"[INFO] 成功点掉隐私遮挡弹窗: {selector}")
                time.sleep(2)
                break
    except: 
        pass

# --- 基于 JS 成功经验的登录流程 (仅增加登录页 CF 穿透调用，其余一字未动) ---
def login(sb, user: str, pwd: str) -> bool:
    print(f"[INFO] 正在建立安全连接进入登录页面...")
    try:
        sb.open(AUTH_URL)
        time.sleep(4)
        
        init_login_shot = shot("init_opened_login_page")
        sb.save_screenshot(init_login_shot)
        print("[INFO] 📸 已捕获刚进入登录页的初始画面，正在发送 TG 通报...")
        notify(True, "登录页初始加载成功", "已成功打开登录页面，正在准备处理表单。", init_login_shot)
        
        handle_privacy_modal(sb)

        # 【新增】：在输入表单前，优先调度双重 CF 穿透检测
        print("[INFO] 🛡️ 正在对登录页面执行 Cloudflare 穿透检测...")
        handle_turnstile_exact_replica(sb)

        sb.wait_for_element_present("#email", timeout=15)

        print("[INFO] 输入账号并刷新表单状态...")
        sb.click("#email")
        sb.type("#email", user)
        sb.execute_script('''
            var emailInput = document.getElementById("email");
            emailInput.dispatchEvent(new Event("input", { bubbles: true }));
            emailInput.dispatchEvent(new Event("change", { bubbles: true }));
        ''')
        
        print("[INFO] 输入密码并刷新表单状态...")
        sb.click("#password")
        sb.type("#password", pwd)
        sb.execute_script('''
            var pwdInput = document.getElementById("password");
            pwdInput.dispatchEvent(new Event("input", { bubbles: true }));
            pwdInput.dispatchEvent(new Event("change", { bubbles: true }));
        ''')
        time.sleep(2)
        
        sb.save_screenshot(shot("before_login_click"))

        print("[INFO] 正在触发登录提交...")
        sb.click("button[type='submit']")
        time.sleep(6)
        
        # 【新增】：点击提交后，防止页面二次弹窗拦截，再次调度 CF 检测
        print("[INFO] 🛡️ 提交后二次对登录页面执行 Cloudflare 穿透检测...")
        handle_turnstile_exact_replica(sb)

        current_url = sb.get_current_url()
        if "auth/login" in current_url:
            print("[INFO] 仍停留在登录页，尝试在密码框模拟 Enter 键直接提交...")
            sb.click("#password")
            sb.send_keys("#password", "\n")
            time.sleep(6)
            current_url = sb.get_current_url()
        
        print(f"[INFO] 登录判定完成，当前 URL: {current_url}")
        return "auth/login" not in current_url
    except Exception as e:
        print(f"[WARN] 登录环节发生异常: {e}")
        try:
            sb.save_screenshot(shot("login_exception"))
        except:
            pass
        return False

# --- 续期逻辑 (焊死不变) ---
def renew_server(sb, sid: str) -> bool:
    try:
        print(f"[INFO] 正在访问服务器续期中心 ID: {sid}...")
        sb.open(SERVER_URL.format(sid))
        time.sleep(5)
        
        handle_privacy_modal(sb)
        
        # 【对齐老脚本选择器】
        renew_selector = 'button:contains("Renew Server")'
        
        if sb.is_element_visible(renew_selector):
            print("[INFO] 🎯 成功捕获到真正的 'Renew Server' 按钮，进行点击！")
            sb.click(renew_selector)
        else:
            print("[WARN] 正常选择器不可见，尝试执行底层 A 标签跳转函数...")
            sb.execute_script(f'var link = document.querySelector(\'a[onclick*="handleServerRenewal"][onclick*="{sid}"]\'); if (link) link.click();')
            
        # 点击 Renew 后交由【双重循环调度机制】进行复刻过检
        print("[INFO] 🚀 已经触发续期点击，正在调度复刻的双重 CF 穿透机制...")
        handle_turnstile_exact_replica(sb)
        
        print("[INFO] 处理完毕，正在重新加载页面刷新续期视图...")
        sb.open(SERVER_URL.format(sid))
        time.sleep(5)
        
        msg_detail = f"服务器 ID: `{sid}`\n续期指令及双重 CF 验证已处理完毕，请查看最新截图确认时间。"
        
        final_shot = shot("renew_final_status")
        sb.save_screenshot(final_shot)
        
        notify(True, "续期流程执行完毕", msg_detail, final_shot)
        return True
    except Exception as e:
        print(f"[ERROR] 续期环节异常: {e}")
        return False

def main():
    dog = threading.Thread(target=watchdog, args=(400,), daemon=True)
    dog.start()

    if not EMAIL or not PASSWORD:
        print("[ERROR] 必须在 Secrets 中配置 ZAMPTO_EMAIL 和 ZAMPTO_PASSWORD")
        sys.exit(1)
    
    display = setup_display()

    try:
        # 启用 uc 模式
        opts = {"uc": True, "test": True, "locale": "zh", "headed": True, "timeout_multiplier": 0.5}
        if PROXY_SOCKS5: 
            opts["proxy"] = PROXY_SOCKS5
            print(f"[INFO] 代理通道已接入: {PROXY_SOCKS5}")
        
        with SB(**opts) as sb:
            # 维持纵向超长视窗 (1280x2400) 焊死不变
            sb.driver.set_window_size(1280, 2400)
            sb.driver.set_page_load_timeout(40)
            
            if login(sb, EMAIL, PASSWORD):
                print("✅ 成功突围至后台。")
                for sid in TARGET_SIDS:
                    renew_server(sb, sid)
            else:
                raise Exception("未通过第一阶段的登录检查，地址仍为登录页。")

    except Exception as e:
        print(f"[FATAL] 全局中断异常: {e}")
        err_shot = shot("fatal_error")
        try:
            sb.save_screenshot(err_shot)
        except:
            pass
        notify(False, "脚本中断", f"运行异常错误: {str(e)}", err_shot)
    finally:
        if display: 
            display.stop()
            print("[INFO] 虚拟显示服务已释放")

    print("[INFO] 续期任务正常退出。")
    os._exit(0)

if __name__ == "__main__":
    main()
