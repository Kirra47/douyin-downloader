# Douyin Downloader 🎬

> 抖音无水印视频下载器 — 基于 Playwright 浏览器嗅探

不依赖第三方 API，不解析抖音签名。直接用你自己的浏览器登录态，从页面网络请求中嗅探到真正的无水印视频地址，然后直连 CDN 下载。

## ✨ 特性

- 🚫 **真正无水印** — `play_addr` > `download_addr`，`playwm` → `play` 替换，跳过 `watermark=1`
- 🔐 **不泄露隐私** — 所有 cookie 保留在本地浏览器 profile 中，不上传
- 🧠 **智能嗅探** — 拦截 `aweme/v1/web/aweme/detail` API 响应，提取完整视频元数据
- ⚡ **多 CDN 重试** — CDN URL 可能 403，自动切换备用地址
- 📺 **不刷播放量** — 嗅探到地址后立即关闭视频页面
- 🌐 **复用登录态** — 登录一次，永久生效（浏览器 profile 持久化）

## 📦 安装

### 方式一：OpenClaw Skill（推荐）

如果你正在使用 OpenClaw，直接让 AI 助手安装：

> "帮我安装 douyin-downloader skill"

OpenClaw 会自动克隆仓库、安装依赖，之后发抖音链接就能直接下载。

### 方式二：手动安装

```bash
git clone https://github.com/Kirra47/douyin-downloader.git
cd douyin-downloader

pip install -r requirements.txt
playwright install chromium
```

## 🚀 快速开始

### 第一步：登录抖音（仅首次）

```bash
python douyin-dl.py --login
```

浏览器会自动打开。在浏览器中访问 `https://www.douyin.com`，扫码或手机号登录一次。登录信息会保存在本地 profile 中，之后无需重复登录。

### 第二步：下载视频

```bash
# 直接粘贴分享链接（支持完整分享文本）
python douyin-dl.py "7.41 复制打开抖音，看看【xxx】... https://v.douyin.com/xxxx/"

# 也可以只给短链接
python douyin-dl.py "https://v.douyin.com/xxxx/"

# 指定保存目录
python douyin-dl.py -o ~/Videos "https://v.douyin.com/xxxx/"
```

## ⚙️ 高级用法

### 连接到已有的浏览器

如果你已经有了一个开启远程调试的 Chrome：

```bash
# 启动浏览器时加 --remote-debugging-port=9222
python douyin-dl.py --cdp-port 9222 "https://v.douyin.com/xxxx/"
```

### 自定义浏览器 profile

```bash
python douyin-dl.py --profile-dir /path/to/chrome-profile "https://v.douyin.com/xxxx/"
```

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DOUYIN_DL_DIR` | `~/Downloads/Douyin` | 视频保存目录 |
| `DOUYIN_CDP_PORT` | `9222` | CDP 端口 |
| `DOUYIN_PROFILE_DIR` | `~/.douyin-downloader/browser-profile` | 浏览器 profile |

## 🔧 工作原理

```
抖音分享链接
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

## 📄 许可证

MIT License

## ⚠️ 免责声明

本项目仅供学习和研究使用。请尊重视频创作者的版权，下载的视频请勿用于商业用途或二次分发。
