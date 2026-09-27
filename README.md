# VisionGuard — 园区事件研判 Agent

个人实习作品：以视频事件为入口，让本地语言模型选择取证工具，检索制度，提出有依据的处置建议，再经人工批准通过 MQTT 控制模拟警灯。

项目目录：`D:\VisionGuard`。Python/Ollama 环境继续复用 `C:\Users\22081\Documents\Codex\tools\visionguard`，避免重复安装。代码、前端构建、数据库、关键帧和样例视频位于项目目录。模型权重目前位于工具目录，YOLO11n 位于项目的 `models`。

## 快速启动

双击 `Run.cmd`：启动后端和必要的本地模型服务，设备使用进程内模拟。

双击 `Run-MQTT.cmd`：额外启动本地 MQTT Broker 和模拟警灯，实际收发 MQTT 消息，无需 Docker。若端口8000已有本项目实例，直接打开网页；不要重复启动。

打开 http://127.0.0.1:8000 。审批令牌显示在启动终端的 `VisionGuard local approval token:` 后。令牌仅用于此本地演示，默认每次启动更换，不写入前端。

在启动窗口按 Ctrl+C 关闭后端，启动器会停止由它启动的辅助进程；不会停止原本已存在的 Ollama/Broker。辅助日志在 `data/`。

## 五分钟演示

1. 点击“生成演示事件”，创建三条明确标识为合成数据的事件。
2. 选择持续6秒的闯入事件。先用“演示模式”体验流程，再选另一条未处理事件使用“真实 Agent”。演示模式不调用LLM，真实模式调用本地Qwen，失败不静默伪装为成功。
3. 在“工具调用”查看模型选择的工具、参数、结果和耗时；在“制度与证据”查看检索到的条款。
4. 输入启动终端里的审批令牌，批准或拒绝。MQTT模式只有收到匹配 command_id 的设备ACK才标记成功；发布成功但无ACK会标记结果未知。
5. 选择低置信度、持续1秒的事件，验证它进入人工复核而不是直接操作设备。
6. 导出JSON报告，包含事件、证据、条款、工具轨迹、审批与设备结果。

自然语言检索例句：“找出待审批、持续3秒以上的闯入事件”。模型生成受约束的类型/状态/时长过滤条件，后端执行过滤，不生成任意SQL。当前仅查询最近200条，尚不支持日期表达式和跨镜头人员身份。

## 视频输入

- 上传MP4等可解码视频，最大100MiB，处理前120秒。
- 多边形为归一化 `[x,y]` 坐标。人员检测框底部中心进入区域并连续停留3秒后生成事件；同一视频的同一track ID只告警一次。
- YOLO11n默认COCO权重支持人员检测，不包含安全帽类别。“未佩戴安全帽”当前只有合成演示事件；不能声称训练了安全帽检测器。
- 真实检测事件保存关键帧、轨迹ID、视频秒数和区域信息。上传的临时视频在处理完后清理，不实现完整录像归档。
- `samples/pipeline-test.mp4` 是 Ultralytics 自带 `bus.jpg` 的6秒重复帧，仅用于检测/追踪/入库链路验证，不是真实监控视频或识别准确率测试集。全画面区域 `[[0,0],[1,0],[1,1],[0,1]]` 可用于演示。可运行 `tools/make_sample.py` 重新生成。
- RTSP适配脚本 `tools/ingest_rtsp.py --url rtsp://... --seconds 10` 使用FFmpeg采集有限片段再送入相同链路；需要你有权限的摄像头。未做真实设备联调，也不是全天候断流重连服务。

## Agent 的实际角色

LangGraph组织“收集证据 → 规则裁决”节点。本地Qwen在最多5轮内，根据事件和已获得的工具结果，从允许的工具中选择下一步：

- `get_event_context`：事件位置、来源、置信度、时长。
- `get_track_evidence`：单镜头轨迹和观测限制。
- `search_safety_rules`：制度检索。
- `inspect_keyframe`：调用本地Qwen2.5-VL复核图片（有图片时可选）。

选择通过JSON Schema约束的结构化输出实现，再由Python执行工具。不是依赖不稳定的自由文本解析，也不将模型“我已调用工具”的文字当作执行成功。模型没有设备控制工具；审批后由确定性后端发送指令。

风险阈值、可执行设备列表、审批令牌与幂等性由代码控制。LangGraph本身不等于Agent：真正由模型决定的是工具选择和检索参数，审计记录可以区分模型选择与演示规则。

状态与工具轨迹存入SQLite。服务重启后未完成分析标为可重试错误，未知执行状态不自动重发。当前不是逐token断点恢复，也没有实现跨流程的长期用户记忆。

## 检索与模型

真实模式：Ollama BGE-M3 embedding → FAISS余弦相似度 + BM25 → RRF融合 → 事件类型过滤 → 返回可追溯条款。嵌入服务不可用时明确记录 `BM25 fallback`；演示模式直接用BM25。

知识库在 `knowledge/sop.json`，是自拟演示制度，非大华内部资料、非法律法规。文档带ID、版本和来源。模型生成检索词，最终报告引用真实工具返回的条款，而不是模型编造引用。

Qwen3 4B用于规划与查询，Qwen2.5-VL 3B用于视觉复核。Ollama只允许单模型常驻，调用结束设置 `keep_alive=0`；这样减少8GB显存压力，但模型切换和冷启动会增加延迟。模型返回不确定时转人工复核。

## 技术栈与部署边界

实际主链路：Python 3.11、FastAPI、Pydantic、LangGraph、Qwen/Ollama、YOLO11n、ByteTrack、OpenCV、FFmpeg、BGE-M3、FAISS、BM25、SQLite、MQTT/Paho、React19、TypeScript、Vite。

提供两种设备适配：进程内模拟和MQTT模拟设备。后者可用本地AMQTT，也可通过 `docker compose up -d mqtt` 使用Mosquitto。发布端口1884，仅绑定本机，与旧项目分离。

`compose.yaml` 中 Redis/PostgreSQL 为 `extensions` profile 的扩展基础设施，不在当前应用主链路中；不能在简历中写成已接入。当前不依赖Kafka、MinIO、Grafana、真实门禁或人脸识别。Docker Engine 在受控执行环境中连接被拒绝，因此容器配置仅校验文件，不声明已部署成功。

## 开发与测试

```powershell
cd D:\VisionGuard
$python='C:\Users\22081\Documents\Codex\tools\visionguard\.venv\Scripts\python.exe'
& $python -m pytest -q
& $python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

前端修改后在 `frontend` 执行 `npm ci`、`npm run build`，刷新页面。已附构建产物，正常演示无需重新安装Node依赖。Vite使用native配置加载，兼容本机Node24并避免受限环境的esbuild配置扫描问题。

API文档：http://127.0.0.1:8000/docs 。配置项见 `backend/config.py`。

## 面试中可以如实介绍

“实现基于LangGraph的园区事件研判Agent，本地Qwen通过受约束的结构化输出选择取证和知识检索工具；将YOLO/ByteTrack事件、制度引用、人工审批和MQTT设备ACK组织为可审计闭环。通过指令ID、事务状态和设备端去重防止重复操作，并设计证据不足和模型失败时的明确降级。”

参见 `TEST_REPORT.md` 了解哪些能力经过实测。尚无独立标注测试集，不应填写误报率下降、F1或生产规模吞吐等未测指标。

`INTERVIEW.md` 提供五分钟演示顺序、常见面试追问与简历参考。三个本地模型均已下载，视频事件完整Agent链路已实测；视觉不确定时正确转人工复核。详见测试记录。
