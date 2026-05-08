# CosyVoice2 接入说明

## 目标

CosyVoice2 不直接放进 Gateway 主进程，而是作为独立 HTTP TTS 服务运行：

```text
Gateway /audio/chat
-> TTS_PROVIDER=cosyvoice_http
-> http://127.0.0.1:9002/synthesize
-> CosyVoice2 生成 WAV
-> Gateway 返回 audio_url
-> CoreS3 下载播放
```

这样做的好处是 Gateway 主进程保持轻量，CosyVoice 的 PyTorch、模型和 GPU/CPU 环境可以独立部署。

## 推荐模式

第一阶段先用：

```text
COSYVOICE_SERVER_MODE=placeholder
```

用于验证 HTTP 协议和 CoreS3 播放链路。

第二阶段切到：

```text
COSYVOICE_SERVER_MODE=cosyvoice2_zero_shot
```

用于 CosyVoice2-0.5B 真实 zero-shot 语音合成。

如果想先用固定音色模型，可测试：

```text
COSYVOICE_SERVER_MODE=cosyvoice_sft
COSYVOICE_MODEL=iic/CosyVoice-300M-SFT
```

## 准备官方仓库

在项目根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup_cosyvoice_repo.ps1
```

脚本默认会把官方仓库克隆到：

```text
.third_party/CosyVoice
```

然后在 `gateway/.env` 中设置：

```text
COSYVOICE_REPO=C:\my_project\DeskBot_S3\M5Stack CoreS3\.third_party\CosyVoice
```

## 安装依赖

CosyVoice 真实推理通常建议使用独立 Python 3.10 / Conda 环境。当前项目先提供 Gateway venv 的可选依赖文件：

```powershell
cd gateway
.\.venv\Scripts\python.exe -m pip install -r requirements-cosyvoice.txt
```

如果安装失败，优先按官方 CosyVoice 仓库要求创建独立环境，再让 `scripts/start_cosyvoice_real.ps1` 指向可用的 Python 环境。

也可以尝试直接安装官方仓库 requirements：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install_cosyvoice_requirements.ps1
```

## 下载模型

可通过 ModelScope 下载：

```powershell
cd gateway
.\.venv\Scripts\python.exe optional_services\download_cosyvoice_models.py `
  --model iic/CosyVoice2-0.5B `
  --output ..\.models
```

也可以先不手动下载，让 CosyVoice 首次加载时自行下载。

## 配置 zero-shot

CosyVoice2-0.5B zero-shot 需要参考音频和参考文本：

```text
COSYVOICE_SERVER_MODE=cosyvoice2_zero_shot
COSYVOICE_MODEL=iic/CosyVoice2-0.5B
COSYVOICE_PROMPT_TEXT=这是一段用于克隆音色的参考文本。
COSYVOICE_PROMPT_AUDIO=C:\path\to\prompt.wav
COSYVOICE_VOICE=default
COSYVOICE_SAMPLE_RATE=22050
```

参考音频建议：

- 清晰人声
- 无背景音乐
- 5 到 15 秒
- WAV 格式
- 文本和音频内容一致

非常重要：`COSYVOICE_PROMPT_TEXT` 必须和 `COSYVOICE_PROMPT_AUDIO` 里说的话逐字一致。
如果参考音频实际内容和参考文本不一致，CosyVoice2 zero-shot 可能会生成和输入文本完全不一致的语音。

不要随手拿一次机器人录音做参考音频，除非已经确认它的转写内容和 `PromptText` 一致。

## 启动服务

placeholder 模式：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_cosyvoice.ps1
```

真实模式：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_cosyvoice_real.ps1
```

zero-shot 启动方式示例：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_cosyvoice_real.ps1 `
  -PromptText "你好，我是桌面机器人。现在开始进行语音合成测试，请保持声音清晰自然。" `
  -PromptAudio "C:\path\to\clean_prompt.wav"
```

当前脚本默认使用本地模型目录：

```text
.models\CosyVoice2-0.5B
```

当前脚本默认禁用 CUDA，强制走 CPU，避免 RTX 5070 Ti Laptop GPU 在当前 PyTorch 版本下触发 `sm_120` 兼容性错误。如需尝试 CUDA，可显式传入：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_cosyvoice_real.ps1 -UseCuda
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:9002/health
```

## Gateway 配置

```text
TTS_PROVIDER=cosyvoice_http
COSYVOICE_URL=http://127.0.0.1:9002/synthesize
COSYVOICE_VOICE=default
COSYVOICE_SAMPLE_RATE=22050
COSYVOICE_TIMEOUT_SECONDS=300
```

## 本地测试

```powershell
$body = @{
  text = "你好，我是你的桌面机器人。"
  voice = "default"
  sample_rate = 22050
  format = "wav"
} | ConvertTo-Json

Invoke-WebRequest http://127.0.0.1:9002/synthesize `
  -Method Post `
  -ContentType "application/json" `
  -Body $body `
  -OutFile .tmp\cosyvoice_test.wav
```

## 当前状态

- Gateway 已支持 `TTS_PROVIDER=cosyvoice_http`。
- CosyVoice HTTP 服务已支持 `placeholder`、`cosyvoice2_zero_shot`、`cosyvoice_sft` 三种模式。
- `placeholder` 已通过 HTTP 级 WAV 输出测试。
- CosyVoice2-0.5B 模型已下载完整，本地模型目录约 5.6GB。
- 真实 CosyVoice2 zero-shot HTTP `/synthesize` 已通过测试，输出 `.tmp\cosyvoice_real_test.wav`。
- Gateway `/audio/chat` 已通过本地路由烟测调用 `cosyvoice_http`，返回 `tts.provider=cosyvoice_http`，生成回复音频约 1.68MB。
- 当前 CPU 推理较慢，短回复可能需要几十秒；后续如要启用 RTX 5070 Ti Laptop GPU，需要升级到支持 `sm_120` 的 PyTorch/CUDA 组合。
