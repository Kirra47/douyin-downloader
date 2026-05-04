---
name: douyin-downloader
description: "抖音无水印视频下载器。当用户发送抖音分享链接（v.douyin.com 或 www.douyin.com/video/）并要求下载视频时使用此 skill。核心原理：通过 Playwright 控制 Chromium 浏览器，复用用户的抖音登录态，从网络请求中嗅探 aweme detail API 响应，提取无水印视频地址后直连 CDN 下载。无需解析抖音 X-Bogus 签名。支持 playwm→play 去水印、多 CDN 重试、嗅探后自动关闭页面避免刷播放量。"
---

# Douyin Downloader — 抖音无水印视频下载器

通过 Playwright 浏览器嗅探，复用用户已登录的抖音账号，自动提取并下载无水印视频。

## 安装（仅首次）

当用户首次要求下载抖音视频时，执行以下安装步骤：

```bash
# 1. 克隆仓库
REPO_DIR="$HOME/.douyin-downloader"
if [ ! -d "$REPO_DIR" ]; then
    git clone https://github.com/Kirra47/douyin-downloader.git "$REPO_DIR"
fi

# 2. 安装依赖
cd "$REPO_DIR"
pip install playwright requests
python3 -m playwright install chromium

echo "✅ 安装完成。运行 python3 douyin-dl.py --login 登录抖音。"
```

如果仓库已存在，执行 `git pull` 更新：

```bash
cd "$HOME/.douyin-downloader" && git pull
```

## 首次使用 — 登录抖音

安装完成后，需要用户在浏览器中登录一次抖音：

```bash
cd "$HOME/.douyin-downloader"
python3 douyin-dl.py --login
```

浏览器会自动打开抖音首页。用户在浏览器中扫码或手机号登录。
登录完成后，在终端按 Enter。登录态会保存在 `~/.douyin-downloader/browser-profile` 中，之后下载无需重复登录。

⚠️ **告诉我用户**："请在打开的浏览器中登录抖音，完成后回到这里告诉我。"

## 下载视频

登录完成后，使用以下命令下载视频：

```bash
cd "$HOME/.douyin-downloader"
python3 douyin-dl.py "<抖音分享文本或链接>" -o "<用户指定的下载目录>"
```

**参数说明：**
- `<链接>` — 完整分享文本或纯链接均可。脚本会自动提取 v.douyin.com 链接
- `-o <目录>` — 视频保存目录。如果用户没有指定，默认为 `~/Downloads/Douyin`
- `--profile-dir` — 浏览器 profile 路径。默认 `~/.douyin-downloader/browser-profile`
- `--cdp-port <端口>` — 如果用户已有运行中的 Chrome（需开启远程调试），可指定端口连接

## 批量下载

如果用户发来多个链接，逐个下载即可，浏览器的登录态是持久化的。

```bash
cd "$HOME/.douyin-downloader"
python3 douyin-dl.py "链接1"
python3 douyin-dl.py "链接2"
# ...
```

## 工作原理

```
用户发送抖音链接
    │
    ▼
┌──────────────────────┐
│  Playwright 浏览器    │  ← 复用已登录的抖音 cookie
│  (chromium, CDP)     │
└──────┬───────────────┘
       │ 访问视频页
       ▼
┌──────────────────────┐
│  拦截 API 响应        │  aweme/v1/web/aweme/detail
│  ──────────────────  │
│  play_addr_h264      │  ← 优先无水印源
│  play_addr_265       │
│  play_addr           │
│  download_addr       │  ← 最后兜底
└──────┬───────────────┘
       │ playwm → play
       │ 过滤 watermark=1
       ▼
┌──────────────────────┐
│  直连 CDN 下载        │  多地址重试，403 自动切换
└──────────────────────┘
```

## 故障排查

### "playwright not found"
运行安装命令重新安装依赖。

### "未能获取视频地址"
说明浏览器未登录抖音。运行 `python3 douyin-dl.py --login` 重新登录。

### "Profile is already in use"
另一个 Chromium 实例正在使用同一 profile。关闭所有 Chromium 窗口后重试，或指定不同的 `--profile-dir`。

### 视频有水印
确认使用的是最新版脚本（`git pull`）。如果仍有水印，可能是抖音更新了视频分发策略。

## 隐私说明

- 所有登录 cookie 保存在本地 `~/.douyin-downloader/browser-profile/`
- 不上传任何数据到第三方
- 不请求任何外部 API 服务（直连抖音 CDN）
- 下载完成后自动关闭视频页面，不产生额外播放量
