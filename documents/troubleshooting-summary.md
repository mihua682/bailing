# Bailing 启动与运行问题排查记录

整理时间：2026-05-05

本文档记录本次排查中遇到的几个主要问题、根因、修复方案和验证方式，便于后续维护。

## 1. ChatTTS 加载失败

### 现象

运行 `python main.py` 后出现类似错误：

```text
ChatTTS.core - INFO - D:\workspace\tts\bailing-0.0.2\asset\Decoder.pt not exist.
ChatTTS.core - ERROR - download to local path D:\workspace\tts\bailing-0.0.2 failed.
AttributeError: 'Chat' object has no attribute 'gpt'
```

### 根因

项目中的 ChatTTS 模型文件实际存在于：

```text
models/ChatTTS/asset/
```

但代码中调用的是：

```python
self.chat.load(source="local", custom_path="...")
```

当前安装的 `chattts==0.1.1` 中，`source="local"` 会忽略 `custom_path`，默认检查当前工作目录下的：

```text
asset/
config/
```

因此它去找了空的 `asset/Decoder.pt`，加载失败。加载失败后继续调用 `sample_random_speaker()`，此时 `self.chat.gpt` 没有初始化，所以报：

```text
AttributeError: 'Chat' object has no attribute 'gpt'
```

### 修复

修改 `bailing/tts.py`：

```python
loaded = self.chat.load(
    source="custom",
    custom_path=model_path,
    compile=False
)
if not loaded:
    raise RuntimeError(f"ChatTTS failed to load models from {model_path}")
```

修改 `config/config.yaml`：

```yaml
TTS:
  CHATTTS:
    output_file: tmp/
    model_path: models/ChatTTS
```

### 验证

```powershell
.venv\Scripts\python.exe -c "from bailing.tts import CHATTTS; t=CHATTTS({'output_file':'tmp/','model_path':'models/ChatTTS'}); print('loaded', hasattr(t.chat, 'gpt'))"
```

期望输出：

```text
loaded True
```

## 2. Ctrl+C 后程序不退出

### 现象

运行 `python main.py` 后按 `Ctrl+C`，日志显示：

```text
Received KeyboardInterrupt. Exiting...
Shutting down Robot...
Shutdown complete.
```

但 Python 进程仍然没有退出。

### 根因

排查到多个会阻塞退出的点：

1. `bailing/player.py` 中播放器线程卡在 `play_queue.get()`，队列为空时无法响应退出。
2. `bailing/recorder.py` 中录音线程不是 daemon，停止时可能阻塞。
3. `bailing/robot.py` 中 VAD/TTS 队列读取使用阻塞式 `Queue.get()`。
4. `ThreadPoolExecutor.shutdown(wait=True)` 会等待正在执行的 LLM/TTS 任务结束。
5. `plugins/task_manager.py` 自己创建了线程池，但原来没有在 Robot 退出时关闭。
6. `plugins/functions/schedule_task.py` 被自动导入时立即启动了一个非 daemon 调度线程，并且线程内部是 `while True`，这是导致 `Shutdown complete` 后仍不退出的核心原因。

### 修复

主要修改：

- `bailing/player.py`
  - 播放器线程改为 `daemon=True`
  - `play_queue.get()` 改为 `get(timeout=0.2)`
  - `shutdown()` 中 `join()` 加超时
  - `PygameSoundPlayer.shutdown()` 停止并释放 `pygame.mixer`

- `bailing/recorder.py`
  - 录音线程改为 `daemon=True`
  - `join()` 加超时，避免无限等待

- `bailing/robot.py`
  - `audio_queue.get()`、`vad_queue.get()`、`tts_queue.get()` 改为带超时
  - 退出时关闭 recorder、player、task_manager
  - `executor.shutdown(wait=False, cancel_futures=True)`

- `plugins/task_manager.py`
  - 增加 `shutdown()`
  - 关闭内部 `ThreadPoolExecutor`
  - 调用 `schedule_task` 的 `scheduler.shutdown()`

- `plugins/functions/schedule_task.py`
  - 调度线程改为 `daemon=True`
  - `while True` 改为 `while not self.stop_event.is_set()`
  - 增加 `shutdown()`

- `main.py`
  - `robot.run()` 返回后执行：

```python
logging.shutdown()
os._exit(0)
```

作为第三方库残留线程的兜底退出方案。

### 验证

语法检查：

```powershell
.venv\Scripts\python.exe -m py_compile main.py bailing\robot.py bailing\recorder.py bailing\player.py plugins\task_manager.py plugins\functions\schedule_task.py
```

调度线程验证：

```powershell
.venv\Scripts\python.exe -c "import threading; import plugins.functions.schedule_task as s; print([(t.name, t.daemon) for t in threading.enumerate() if t is not threading.main_thread()]); s.scheduler.shutdown()"
```

期望调度线程是 daemon：

```text
[('Thread-1 (run_scheduler)', True)]
```

## 3. Chroma telemetry 错误日志

### 现象

启动时出现：

```text
chromadb.telemetry.product.posthog - INFO - Anonymized telemetry enabled.
chromadb.telemetry.product.posthog - ERROR - Failed to send telemetry event ClientStartEvent: capture() takes 1 positional argument but 3 were given
chromadb.telemetry.product.posthog - ERROR - Failed to send telemetry event ClientCreateCollectionEvent: capture() takes 1 positional argument but 3 were given
```

### 根因

`bailing/rag.py` 使用 `langchain_chroma.Chroma`，Chroma 默认启用匿名 telemetry。当前依赖版本中的 `posthog.capture()` 调用与已安装的 PostHog SDK 参数不兼容，因此启动时刷错误日志。

这个问题不是主程序不退出的直接原因，但会干扰日志。

### 修复

在 `main.py` 和 `bailing/rag.py` 中设置：

```python
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
```

在 Chroma 初始化时传入：

```python
client_settings=Settings(anonymized_telemetry=False)
```

同时在 `main.py` 中压制该 logger：

```python
logging.getLogger('chromadb.telemetry.product.posthog').setLevel(logging.CRITICAL)
```

## 4. Windows GBK 控制台日志编码错误

### 现象

运行过程中出现：

```text
--- Logging error ---
UnicodeEncodeError: 'gbk' codec can't encode character '\U0001f60a'
...
ChatTTS\norm.py", line 148, in __call__
self.logger.warning(f"found invalid characters: {invalid_characters}")
```

### 根因

LLM 返回内容中包含 emoji，例如：

```text
😊
```

ChatTTS 的 normalizer 发现不支持字符后会写 warning 日志。Windows 控制台默认编码常是 GBK，GBK 无法输出 emoji，于是 Python logging 自己报 `UnicodeEncodeError`。

这不是模型加载失败，也不是 TTS 核心异常，而是日志输出编码问题。

### 修复

在 `main.py` 中将标准输出和错误输出改为 UTF-8：

```python
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
```

文件日志显式使用 UTF-8：

```python
logging.FileHandler('tmp/bailing.log', encoding='utf-8')
```

同时在 `bailing/tts.py` 中增加 ChatTTS 文本清洗，过滤 emoji 等不适合 TTS 的字符：

```python
_CHAT_TTS_UNSUPPORTED_CHARS = re.compile(
    r"[^\u4e00-\u9fffA-Za-z0-9\s，。！？、；：,.!?;:'\"“”‘’（）()《》<>【】\[\]\-—…]"
)

def _clean_chattts_text(text):
    return _CHAT_TTS_UNSUPPORTED_CHARS.sub(" ", str(text)).strip()
```

在 `CHATTTS.to_tts()` 开始处调用：

```python
text = _clean_chattts_text(text)
if not text:
    logger.info("ChatTTS text is empty after cleaning.")
    return None
```

### 验证

```powershell
.venv\Scripts\python.exe -c "from bailing.tts import _clean_chattts_text; print(_clean_chattts_text('你好😊，测试🚀abc!'))"
```

输出：

```text
你好 ，测试 abc!
```

## 5. 本次涉及的主要文件

```text
main.py
bailing/tts.py
bailing/robot.py
bailing/player.py
bailing/recorder.py
bailing/rag.py
plugins/task_manager.py
plugins/functions/schedule_task.py
config/config.yaml
```

## 6. 推荐启动与测试命令

启动：

```powershell
python main.py
```

或显式指定配置：

```powershell
python main.py --config_path config/config.yaml
```

语法检查：

```powershell
.venv\Scripts\python.exe -m py_compile main.py bailing\tts.py bailing\robot.py bailing\recorder.py bailing\player.py bailing\rag.py plugins\task_manager.py plugins\functions\schedule_task.py
```

ChatTTS 加载验证：

```powershell
.venv\Scripts\python.exe -c "from bailing.tts import CHATTTS; t=CHATTTS({'output_file':'tmp/','model_path':'models/ChatTTS'}); print('loaded', hasattr(t.chat, 'gpt'))"
```

Ctrl+C 退出验证：

1. 运行 `python main.py`
2. 等待日志出现 `Started recording.`
3. 按 `Ctrl+C`
4. 期望日志出现 `Shutdown complete.` 后进程直接退出

