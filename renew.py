#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zampto 自动续期脚本 - SeleniumBase 极速过 CF 横屏稳定版
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

# --- 精准设置虚拟桌面 (确保 1280x800 完美横屏截图) ---
def setup_display():
    if is_linux() and not os.environ.get("DISPLAY"):
        try:
            from pyvirtualdisplay import Display
            # 强制指定标准 1280x800 分辨率，确保截图不再是竖屏、窄图
            d = Display(visible=False, size=(1280, 800))
            d.start()
            os.environ["DISPLAY"] = d.new_display_var
            print("[INFO] 🖥️ Xvfb 虚拟标准横屏桌面已成功启动 (1280x800)")
            return d
        except Exception as e:
            print(f"[ERROR] 虚拟显示启动失败: {e}")
            sys.exit(1)
    return None

def shot(name: str) -> str:
    return str(OUTPUT_DIR / f"{cn_now().strftime('%H%M%S')}-{name}.png")

def notify(ok: bool, stage: str, msg: str = "", img: str = None):
    if not TG_BOT_TOKEN or not TG_CHAT_ID: 
        return
    try:
        text = f"🔔 Zampto: {'✅' if ok else '❌'} {stage}\n{msg}\n⏰ {cn_time_str()}"
        requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", json={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
        if img and Path(img).exists():
            with open(img, "rb") as f:
                requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto", data={"chat_id": TG_CHAT_ID}, files={"photo": f}, timeout=15)
    except: 
        pass

# --- 【核心复刻】调用 SeleniumBase UC 模式物理级过 CF Turnstile 逻辑 ---
def handle_turnstile(sb) -> bool:
    try:
        time.sleep(2)
        # 检测页面是否存在 cf-turnstile 响应框
        result = sb.execute_script('return document.querySelector("input[name=\'cf-turnstile-response\']") !== null')
        if not result: 
            return True
        
        print("[INFO] 🛡️ 发现 Cloudflare Turnstile 验证层，开始执行 GUI 级过检...")
        sb.uc_gui_click_captcha()
        time.sleep(5)
        return True
    except Exception as e: 
        print(f"[WARN] 尝试通过 CF 验证时触发异常: {e}")
        return False

# --- 完美继承自 JS 版本的隐私窗消除逻辑 ---
def handle_privacy_modal(sb):
    try:
        for selector in ["button.fc-cta-consent", "button[aria-label='Consent']", ".fc-consent-root button", "text=Accept All"]:
            if sb.is_element_visible(selector):
                sb.click(selector)
                print(f"[INFO] 成功点掉隐私遮挡弹窗: {selector}")
                time.sleep(2)
                break
    except: 
        pass

# --- 完美继承自 JS 版本的登录及虚拟 DOM 强刷逻辑 ---
def login(sb, user: str, pwd: str) -> bool:
    print(f"[INFO] 正在建立安全连接进入登录页面...")
    try:
        sb.uc_open_with_reconnect(AUTH_URL, reconnect_time=5.0)
        time.sleep(3)
        
        # 处理登录前的前置验证
        handle_turnstile(sb)
        sb.wait_for_element_present("#email", timeout=10)
        handle_privacy_modal(sb)

        # 核心：将刚才 JS 版证实最有效的 dispatchEvent 强刷策略迁移到 Python 中执行，攻破 Next.js 表单断开机制
        print("[INFO] 输入账号并触发事件气泡冒泡...")
        sb.execute_script(f'document.getElementById("email").value = "{user}"')
        sb.execute_script('document.getElementById("email").dispatchEvent(new Event("input", { bubbles: true }))')
        sb.execute_script('document.getElementById("email").dispatchEvent(new Event("change", { bubbles: true }))')
        
        print("[INFO] 输入密码并触发事件气泡冒泡...")
        sb.execute_script(f'document.getElementById("password").value = "{pwd}"')
        sb.execute_script('document.getElementById("password").dispatchEvent(new Event("input", { bubbles: true }))')
        sb.execute_script('document.getElementById("password").dispatchEvent(new Event("change", { bubbles: true }))')
        time.sleep(1.5)
        
        # 提交登录
        sb.click("button[type='submit']")
        time.sleep(6)
        
        # 处理提交表单后的可能存在的 CF 二次验证
        handle_turnstile(sb)
        time.sleep(2)
        
        # 判断是否成功脱离登录地址
        return "auth/login" not in sb.get_current_url()
    except Exception as e:
        print(f"[WARN] 登录环节发生异常: {e}")
        sb.save_screenshot(shot("login_exception"))
        return False

# --- 续期逻辑：点击并触发复刻的 CF 防御 ---
def renew_server(sb, sid: str) -> bool:
    try:
        print(f"[INFO] 正在访问服务器续期中心 ID: {sid}...")
        sb.open(SERVER_URL.format(sid))
        time.sleep(4)
        
        handle_privacy_modal(sb)
        
        # 获取旧时间状态
        old_val = sb.execute_script('return document.getElementById("lastRenewalTime")?.textContent.strip() || "";')
        
        renew_selector = "button:has-text('Renew Server')"
        if sb.is_element_visible(renew_selector):
            print("[INFO] 成功捕获到 'Renew Server' 按钮，进行点击...")
            sb.click(renew_selector)
        else:
            print("[WARN] 正常选择器不可见，尝试执行底层 A 标签跳转函数...")
            sb.execute_script(f'var link = document.querySelector(\'a[onclick*="handleServerRenewal"][onclick*="{sid}"]\'); if (link) link.click();')
            
        # 核心：一点击续期，立即调用 SeleniumBase 特有的过 CF GUI 方案进行处理
        print("[INFO] 触发续期点击，开始接管可能被拦截的二次 CF 验证...")
        time.sleep(2)
        handle_turnstile(sb)
        time.sleep(8)
        
        # 重新刷新当前页面来捞取最新的到期数据
        sb.open(SERVER_URL.format(sid))
        time.sleep(4)
        
        new_val = sb.execute_script('return document.getElementById("lastRenewalTime")?.textContent.strip() || "";')
        expiry_time = sb.execute_script('return document.getElementById("nextRenewalTime")?.textContent.strip() || "获取失败";')
        
        is_ok = (new_val != old_val and new_val != "")
        
        status_msg = "续期成功" if is_ok else "状态未发生明显变动"
        msg_detail = f"服务器 ID: `{sid}`\n有效剩余到期时间: `{expiry_time}`"
        
        final_shot = shot("renew_final_status")
        sb.save_screenshot(final_shot)
        
        notify(is_ok, status_msg, msg_detail, final_shot)
        return is_ok
    except Exception as e:
        print(f"[ERROR] 续期环节异常: {e}")
        return False

def main():
    # 设定 400 秒看门狗强退，防止在 Actions 挂死
    dog = threading.Thread(target=watchdog, args=(400,), daemon=True)
    dog.start()

    if not EMAIL or not PASSWORD:
        print("[ERROR] 必须在 Secrets 中配置 ZAMPTO_EMAIL 和 ZAMPTO_PASSWORD")
        sys.exit(1)
    
    display = setup_display()

    try:
        # 启用 uc (Undetected Mode)，headed 模式配合虚拟横屏桌面
        opts = {"uc": True, "test": True, "locale": "zh", "headed": True, "timeout_multiplier": 0.5}
        if PROXY_SOCKS5: 
            opts["proxy"] = PROXY_SOCKS5
            print(f"[INFO] 代理通道已接入: {PROXY_SOCKS5}")
        
        with SB(**opts) as sb:
            # 强制设定浏览器视窗大小，确保导出的图片是完美横屏
            sb.driver.set_window_size(1280, 800)
            sb.driver.set_page_load_timeout(30)
            
            if login(sb, EMAIL, PASSWORD):
                print("✅ 成功突围至后台。")
                for sid in TARGET_SIDS:
                    renew_server(sb, sid)
            else:
                raise Exception("未通过第一阶段的登录检查，地址仍为登录页。")

    except Exception as e:
        print(f"[FATAL] 全局中断异常: {e}")
        notify(False, "脚本中断", f"运行异常错误: {str(e)}", shot("fatal_error"))
    finally:
        if display: 
            display.stop()
            print("[INFO] 虚拟显示服务已释放")

    print("[INFO] 续期任务正常退出。")
    os._exit(0)

if __name__ == "__main__":
    main()
