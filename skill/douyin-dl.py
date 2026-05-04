#!/usr/bin/env python3
"""
Douyin Downloader — 抖音无水印视频下载器

通过 Playwright 控制浏览器，利用已登录的抖音账号，自动嗅探并下载无水印高清视频。

## 快速开始
    # 1. 安装
    pip install playwright requests
    playwright install chromium

    # 2. 先登录抖音（只做一次）
    python douyin-dl.py --login

    # 3. 下载视频
    python douyin-dl.py "https://v.douyin.com/xxxxx/"

## 工作原理
    1. 启动/连接 Chromium 浏览器（复用持久化 profile 保持登录态）
    2. 访问抖音视频页面，监听 aweme detail API 响应
    3. 从 API JSON 中提取 play_addr（无水印），playwm → play 替换
    4. 跳过含 watermark=1 的 URL，直接请求 CDN 源文件下载
    5. 下载完成后自动关闭视频页面（不刷播放量）

## 前置条件
    - Python 3.9+
    - Chromium 浏览器（自动安装）
    - 抖音账号在浏览器中登录一次即可

许可证: MIT
"""

import re
import sys
import json
import time
import argparse
import os
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from typing import Optional, Union, List

import requests
from playwright.sync_api import sync_playwright


# —— 可配置默认值 ——
DEFAULT_SAVE_DIR = os.environ.get("DOUYIN_DL_DIR", str(Path.home() / "Downloads" / "Douyin"))
DEFAULT_CDP_PORT = int(os.environ.get("DOUYIN_CDP_PORT", "9222"))
DEFAULT_PROFILE_DIR = os.environ.get(
    "DOUYIN_PROFILE_DIR",
    str(Path.home() / ".douyin-downloader" / "browser-profile"),
)
VIDEO_ID_PATTERN = re.compile(r"/video/(\d+)")


# ——————————————————————— URL 处理 ———————————————————————

def extract_url(text: str) -> str:
    """从分享文本中提取抖音链接"""
    pattern = r"https?://(?:v|www|mobile)\.douyin\.com/\S+"
    match = re.search(pattern, text)
    return match.group(0).strip("！？，。 ；") if match else text.strip()


def resolve_short(short_url: str) -> str:
    """短链 → 长链，便于提取 video_id"""
    s = requests.Session()
    s.trust_env = False
    s.proxies = {"http": None, "https": None}
    try:
        r = s.get(
            short_url,
            allow_redirects=False,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        )
        if r.status_code in (301, 302):
            return r.headers.get("Location", short_url)
    except Exception:
        pass
    return short_url


# ——————————————————————— 视频地址提取 ———————————————————————

def find_video_urls(obj, depth=0) -> Optional[List[str]]:
    """
    递归查找视频下载 URL 列表。
    优先级: play_addr_h264 > play_addr_265 > play_addr > download_addr
    """
    if depth > 20 or obj is None:
        return None

    if isinstance(obj, dict):
        video = obj.get("video", {})
        if isinstance(video, dict):
            for key in ("play_addr_h264", "play_addr_265", "play_addr", "download_addr"):
                addr = video.get(key, {})
                if isinstance(addr, dict):
                    url_list = addr.get("url_list", [])
                    if url_list:
                        return url_list
                elif isinstance(addr, str) and addr.startswith("http"):
                    return [addr]
            for br in video.get("bit_rate", []) or []:
                pa = br.get("play_addr", {})
                if isinstance(pa, dict) and pa.get("url_list"):
                    return pa["url_list"]

        for v in obj.values():
            result = find_video_urls(v, depth + 1)
            if result:
                return result

    elif isinstance(obj, list):
        for item in obj[:50]:
            result = find_video_urls(item, depth + 1)
            if result:
                return result

    return None


def dewatermark_url(url: str) -> str:
    """
    去水印: playwm → play + 剥离 query string
    去掉 watermark=1 等参数，避免 CDN 注入水印层。
    """
    url = url.replace("playwm", "play")
    parsed = urlparse(url)
    return urlunparse(parsed._replace(query=""))


def filter_valid_urls(urls: List[str]) -> List[str]:
    """过滤掉明确带水印标志的 URL"""
    valid = [u for u in urls if "watermark=1" not in u and "aweme/v1/play" not in u]
    return valid or urls


# ——————————————————————— 下载 ———————————————————————

def download_file(url: str, out_path: Path, user_agent: str = "") -> None:
    """带终端进度条的文件下载"""
    s = requests.Session()
    s.trust_env = False
    s.proxies = {"http": None, "https": None}

    ua = user_agent or (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
    )
    headers = {"User-Agent": ua, "Referer": "https://www.douyin.com/"}

    resp = s.get(url, stream=True, headers=headers, timeout=600)
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    start = time.time()

    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
            downloaded += len(chunk)
            if total and time.time() - start > 0.2:
                pct = downloaded / total * 100
                elapsed = time.time() - start
                speed = downloaded / elapsed / 1024 if elapsed > 0 else 0
                eta = (total - downloaded) / (speed * 1024) if speed > 0 else 0
                sys.stdout.write(
                    f"\r  ⬇ {pct:.1f}% | {downloaded//1024}/{total//1024}KB "
                    f"| {speed:.0f}KB/s | ETA {eta:.0f}s  "
                )
                sys.stdout.flush()

    print(f"\n  ✅ 完成: {out_path.name}")


def download_with_retry(urls: List[str], out_path: Path, user_agent: str = "") -> bool:
    """遍历 URL 列表下载，遇 403 自动切备用地址"""
    valid = filter_valid_urls(urls)
    for i, raw_url in enumerate(valid, 1):
        clean = dewatermark_url(raw_url)
        print(f"  🔗 [{i}/{len(valid)}] {clean[:100]}...")
        try:
            download_file(clean, out_path, user_agent=user_agent)
            return True
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 403:
                print("  ⚠️ 403 Forbidden, trying next mirror...")
                continue
            raise
        except Exception as e:
            print(f"  ⚠️ {e}, trying next mirror...")
            continue
    return False


# ——————————————————————— 浏览器操作 ———————————————————————


def login_mode(profile_dir: str):
    """打开浏览器让用户手动登录抖音"""
    print("🚀 启动浏览器...")
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            profile_dir,
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-first-run"],
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True,
        )
        page = ctx.new_page()
        page.goto("https://www.douyin.com", wait_until="domcontentloaded")
        print("📱 请在浏览器中扫码或手机号登录抖音")
        print("   登录完成后按 Enter 保存登录态并退出...")
        input()
        print("✅ 登录态已保存！下次下载将自动复用。")
        ctx.close()


def sniff_and_download(
    short_url: str,
    cdp_port: int,
    save_dir: Path,
    headless: bool = False,
    profile_dir: str = "",
):
    """核心流程：浏览器嗅探 → 提取视频地址 → 下载"""
    full_url = resolve_short(short_url)

    m = VIDEO_ID_PATTERN.search(full_url)
    video_id = m.group(1) if m else None
    if not video_id:
        print("❌ 无法从链接提取 video_id")
        return False

    video_page = f"https://www.douyin.com/video/{video_id}"

    # 判断是连接已有浏览器还是自动启动
    with sync_playwright() as pw:
        if cdp_port:
            # 模式 A: 连接已有 CDP 浏览器
            print(f"🔗 连接浏览器 CDP (127.0.0.1:{cdp_port})...")
            try:
                browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
                ctx = browser.contexts[0]
            except Exception as e:
                if "Browser context management" in str(e):
                    # 某些浏览器（如 openclaw 受控浏览器）不支持 context 管理
                    # 降级：用 launch 模式，但需要 --profile-dir
                    print(f"⚠️ 当前 CDP 浏览器不支持 context 管理，请用 --profile-dir 模式")
                    if profile_dir:
                        print("🔄 降级到 launch 模式...")
                        ctx = pw.chromium.launch_persistent_context(
                            profile_dir,
                            headless=headless,
                            args=["--disable-blink-features=AutomationControlled"],
                            viewport={"width": 1920, "height": 1080},
                            ignore_https_errors=True,
                        )
                    else:
                        raise
                else:
                    raise
        elif profile_dir:
            # 模式 B: 自动启动持久化浏览器
            print("🚀 启动浏览器...")
            ctx = pw.chromium.launch_persistent_context(
                profile_dir,
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
                viewport={"width": 1920, "height": 1080},
                ignore_https_errors=True,
            )
            pages_before = set()
        else:
            print("❌ 需要指定 --cdp-port 或 --profile-dir")
            return False

        # 查找或创建页面
        page = None
        for pg in ctx.pages:
            if "douyin.com" in pg.url and "/video/" in pg.url and video_id in pg.url:
                page = pg
                break

        if not page:
            page = ctx.new_page()
            page.goto(video_page, wait_until="domcontentloaded", timeout=30000)

        captured_responses = []

        def on_response(response):
            if "aweme/v1/web/aweme/detail" in response.url:
                try:
                    captured_responses.append(response.json())
                except Exception:
                    pass

        page.on("response", on_response)

        # 触发 API 请求
        if "douyin.com" in page.url:
            page.reload(wait_until="domcontentloaded")
        else:
            page.goto(video_page, wait_until="domcontentloaded", timeout=30000)

        # 等待 API 响应
        video_url = None
        title = None
        wait_start = time.time()

        while time.time() - wait_start < 15:
            for body in captured_responses:
                result = find_video_urls(body)
                if result:
                    video_url = result
                    aweme = body.get("aweme_detail", {})
                    title = aweme.get("desc", "") or aweme.get("preview_title", "")
                    break

            if video_url:
                break

            # 备选: <video> 标签
            try:
                src = page.evaluate(
                    "() => document.querySelector('video')?.src || ''"
                )
                if src and src.startswith("http"):
                    video_url = [src]
                    title = page.title()
                    break
            except Exception:
                pass

            page.wait_for_timeout(1000)

        # 获取浏览器 UA
        browser_ua = page.evaluate("() => navigator.userAgent") or ""

        # 关视频页面（不刷播放量）
        try:
            page.close()
        except Exception:
            pass

    if not video_url:
        print("❌ 未能获取视频地址。请确认浏览器中已登录抖音。")
        print("   首次使用请运行: python douyin-dl.py --login")
        return False

    # 下载
    save_dir.mkdir(parents=True, exist_ok=True)
    safe_title = re.sub(r'[<>:"/\\|?*]', "_", title or f"douyin_{video_id}")[:80]
    out_path = save_dir / f"{safe_title}.mp4"

    if isinstance(video_url, list):
        return download_with_retry(video_url, out_path, user_agent=browser_ua)
    else:
        clean = dewatermark_url(video_url)
        download_file(clean, out_path, user_agent=browser_ua)
        return True


# ——————————————————————— CLI ———————————————————————

def main():
    parser = argparse.ArgumentParser(
        description="抖音无水印视频下载器 — 基于 Playwright 浏览器嗅探",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 首次使用：登录抖音
  python douyin-dl.py --login

  # 下载视频（自动启动浏览器）
  python douyin-dl.py "https://v.douyin.com/xxxxx/"

  # 连接到已运行的浏览器
  python douyin-dl.py --cdp-port 9222 "https://v.douyin.com/xxxxx/"

  # 指定保存目录
  python douyin-dl.py -o ./my-videos "https://v.douyin.com/xxxxx/"
        """,
    )
    parser.add_argument("url", nargs="?", help="抖音分享文本或链接")
    parser.add_argument("-o", "--output", default=DEFAULT_SAVE_DIR, help="视频保存目录")
    parser.add_argument("--cdp-port", type=int, default=None, help="已有浏览器的 CDP 端口")
    parser.add_argument("--profile-dir", default=DEFAULT_PROFILE_DIR, help="浏览器 profile 目录")
    parser.add_argument("--login", action="store_true", help="打开浏览器登录抖音")
    parser.add_argument("--headless", action="store_true", help="无头模式（可能被抖音检测）")

    args = parser.parse_args()

    if args.login:
        login_mode(args.profile_dir)
        return

    if not args.url:
        args.url = input("📎 请粘贴抖音分享链接: ")

    if not args.url.strip():
        print("❌ 没有提供链接")
        sys.exit(1)

    success = sniff_and_download(
        args.url,
        cdp_port=args.cdp_port,
        save_dir=Path(args.output),
        headless=args.headless,
        profile_dir=args.profile_dir,
    )

    if success:
        print(f"\n📁 保存至 {args.output}")
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
