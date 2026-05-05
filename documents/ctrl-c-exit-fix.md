# Ctrl+C 退出修复说明

## 修复时间
2026-05-05

## 问题描述
按 Ctrl+C 后，程序显示 "Shutdown complete." 但 Python 进程仍然没有退出。

## 根本原因
多个线程和队列阻塞导致程序无法退出：

1. **播放器线程** - 卡在 `play_queue.get()`，队列为空时无法响应退出
2. **录音线程** - 不是 daemon 线程，停止时可能阻塞
3. **VAD/TTS 队列读取** - 使用阻塞式 `Queue.get()`
4. **ThreadPoolExecutor** - `shutdown(wait=True)` 会等待正在执行的任务结束
5. **TaskManager** - 自己创建了线程池，但没有在 Robot 退出时关闭
6. **schedule_task** - 自动导入时立即启动了一个非 daemon 调度线程，这是导致不退出的核心原因

## 修复内容

### 1. bailing/player.py
- ✅ 播放器线程改为 `daemon=True`
- ✅ `play_queue.get()` 改为 `get(timeout=0.2)`
- ✅ `shutdown()` 中 `join()` 加超时 `timeout=2.0`

### 2. bailing/recorder.py
- ✅ 录音线程改为 `daemon=True`
- ✅ `join()` 加超时 `timeout=2.0`

### 3. bailing/robot.py
- ✅ `audio_queue.get()` 改为带超时 `timeout=0.5`
- ✅ `tts_queue.get()` 改为带超时 `timeout=0.5`
- ✅ 添加 `queue.Empty` 异常处理
- ✅ 退出时关闭 recorder、player、task_manager
- ✅ `executor.shutdown(wait=False, cancel_futures=True)` - 不等待正在执行的任务

### 4. plugins/task_manager.py
- ✅ 增加 `_stop_event` 用于控制线程退出
- ✅ `process_task` 中的 `while True` 改为 `while not self._stop_event.is_set()`
- ✅ 增加 `shutdown()` 方法
- ✅ 关闭内部 `ThreadPoolExecutor`
- ✅ 调用 `schedule_task` 的 `scheduler.shutdown()`

### 5. plugins/functions/schedule_task.py
- ✅ 增加 `stop_event` 用于控制调度器退出
- ✅ 调度线程改为 `daemon=True`
- ✅ `while True` 改为 `while not self.stop_event.is_set()`
- ✅ 增加 `shutdown()` 方法
- ✅ 调用 `schedule.clear()` 清除所有定时任务

### 6. main.py
- ✅ 添加 `os` 和 `sys` 导入
- ✅ 文件日志显式使用 UTF-8: `encoding='utf-8'`
- ✅ Windows GBK 控制台日志编码错误修复
- ✅ Chroma telemetry 错误日志压制
- ✅ `robot.run()` 返回后执行：
  ```python
  logging.shutdown()
  os._exit(0)
  ```
  作为第三方库残留线程的兜底退出方案

## 验证方法

### 1. 语法检查
```powershell
.venv\Scripts\python.exe -m py_compile main.py bailing\tts.py bailing\robot.py bailing\recorder.py bailing\player.py plugins\task_manager.py plugins\functions\schedule_task.py
```

### 2. 调度线程验证
```powershell
.venv\Scripts\python.exe -c "import threading; import plugins.functions.schedule_task as s; print([(t.name, t.daemon) for t in threading.enumerate() if t is not threading.main_thread()]); s.scheduler.shutdown()"
```

期望输出：
```
[('Thread-1 (run_scheduler)', True)]
```

### 3. Ctrl+C 退出验证
1. 运行 `python main.py --config_path config/config.yaml`
2. 等待日志出现 `Started recording.`
3. 按 `Ctrl+C`
4. 期望日志出现：
   ```
   Received KeyboardInterrupt. Exiting...
   Shutting down Robot...
   Shutting down TaskManager...
   Shutting down TaskScheduler...
   Shutdown complete.
   ```
5. 进程应该立即退出，不再卡住

## 注意事项

- `os._exit(0)` 是强制退出，会跳过一些清理工作，但能确保程序退出
- 所有 daemon 线程会在主线程退出时自动终止
- 队列超时机制确保线程能及时响应退出信号
- ThreadPoolExecutor 使用 `wait=False, cancel_futures=True` 避免等待长时间运行的任务

## 相关文件

```
main.py
bailing/tts.py
bailing/robot.py
bailing/player.py
bailing/recorder.py
plugins/task_manager.py
plugins/functions/schedule_task.py
config/config.yaml
```
