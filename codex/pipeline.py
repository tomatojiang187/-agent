from __future__ import annotations

import logging
import base64
import re

from codex.adapters.registry import AdapterRegistry
from codex.aggregator import ResultAggregator
from codex.analyzer import ComplexityAnalyzer
from codex.config import AppConfig
from codex.decomposer import TaskDecomposer
from codex.executor import DAGExecutor
from codex.tools import read_file, list_dir, execute_command
from codex.models import (
    TaskState,
    ExecuteRequest,
    ExecuteResponse,
    ComplexityAssessment,
    TaskDAG,
    SubtaskResult,
    AggregatedResult,
    SubTask,
    ComplexityLevel,
    TaskType
)
from codex.router import ModelRouter

logger = logging.getLogger(__name__)


class Pipeline:
    """Orchestrates the full 5-stage pipeline: analyze → decompose → route → execute → aggregate."""

    def __init__(self, config: AppConfig, registry: AdapterRegistry):
        self._config = config
        self._registry = registry
        self._tasks: dict[str, TaskState] = {}

    async def execute(self, request: ExecuteRequest) -> ExecuteResponse:
        state = TaskState(requirement=request.requirement, context=request.context)
        self._tasks[state.task_id] = state

        try:
            # ==========================================
            # 🌟 附件与多模态文件处理（完全解耦防崩溃）
            # ==========================================
            image_contents = []

            # 兼容性检查：确保 request.files 存在
            if hasattr(request, 'files') and request.files:
                for f in request.files:
                    if f.mime_type.startswith("text/") or f.mime_type == "application/json" or f.filename.endswith(('.py', '.yaml', '.md', '.html', '.js', '.txt')):
                        try:
                            text_content = base64.b64decode(f.data).decode('utf-8')
                            request.context += f"\n\n【用户上传了文本文件：{f.filename}】\n```\n{text_content}\n```"
                            logger.info(f"📎 成功加载文本文件: {f.filename}")
                        except UnicodeDecodeError:
                            request.context += f"\n\n【提示：文件 {f.filename} 无法读取为纯文本。】"
                            logger.warning(f"⚠️ 文件 {f.filename} 无法用 utf-8 解码。")
                    elif f.mime_type.startswith("image/"):
                        # 收集图片数据
                        image_contents.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:{f.mime_type};base64,{f.data}"}
                        })
                        logger.info(f"🖼️ 成功加载图片文件: {f.filename}")
                    else:
                        request.context += f"\n\n【提示：不支持直接读取的文件类型 {f.filename}。】"
                        logger.warning(f"⚠️ 文件 {f.filename} 格式不支持读取。")
            # ==========================================

            # ==========================================
            # 🌟 OpenClaw 极速管家模式（带人工确认）
            # ==========================================
            if hasattr(request, 'mode') and request.mode == "openclaw":
                logger.info("🦞 触发 OpenClaw 管家模式：启用本地物理抓手（带人工确认）")

                # 伪造评估结果和 DAG（适配前端格式）
                assessment = ComplexityAssessment(
                    level=ComplexityLevel.SIMPLE, task_type=TaskType.OTHER,
                    estimated_subtasks=1, reasoning="OpenClaw 本地管家接管，启用工具箱动态执行。"
                )
                dag = TaskDAG(tasks=[SubTask(id="1", description="OpenClaw 智能体自主决策循环")])
                state.complexity = assessment
                state.dag = dag
                state.status = "openclaw_running"

                # 提取底层的聊天适配器（默认用配置里的第一个模型）
                adapter = self._registry.get(self._config.models[0].name)

                # 核心：注入强大的 Tool Calling 系统提示词
                sys_prompt = """你是一个极速、全能的本地 AI 管家。为了完成任务，你可以调用用户的本地电脑资源。

【可用工具】
1. read_file|文件路径  (用途：读取文件内容)
2. list_dir|目录路径   (用途：查看某目录下有哪些文件)
3. execute_command|终端命令 (用途：执行任何 cmd/shell 命令，如运行脚本、创建文件夹等)

【重要规则】
- 如果你需要调用工具，请输出严格的 XML 标签，格式为：<TOOL>工具名|参数</TOOL>。
- 每次发言【最多只能调用一个工具】，不要附加任何解释废话，等待系统返回工具执行结果。
- 🌟 如果你需要运行多行 Python 代码，请务必分两步：第一步先使用 execute_command 执行 `echo "代码内容" > temp_script.py` 将其写入文件；第二步再调用 execute_command 执行 `python temp_script.py`。
- 当你收集完足够的信息，或者已经通过命令完成了用户的需求时，请直接用正常的 Markdown 输出最终回答，不要再包含 <TOOL> 标签。
"""
                
                # 🌟 核心修复：只在即将发送给大模型的那一刻，才把图片包装进消息里
                user_content = request.requirement
                if image_contents:
                    user_content = [{"type": "text", "text": request.requirement}] + image_contents
                    if request.context:
                        user_content[0]["text"] += f"\n\n附加上下文：\n{request.context}"
                else:
                    if request.context:
                        user_content += f"\n\n附加上下文：\n{request.context}"

                messages = [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_content}
                ]

                final_output = ""
                # 开启智能体循环
                for step in range(5):
                    logger.info(f"🔄 OpenClaw 正在思考 (第 {step + 1} 轮)...")
                    raw_response = await adapter.chat(messages, temperature=0.1)

                    # re.DOTALL 允许跨行匹配
                    tool_match = re.search(r'<TOOL>(.*?)\|(.*?)</TOOL>', raw_response, re.DOTALL)

                    if tool_match:
                        tool_name, tool_arg = tool_match.groups()
                        tool_name = tool_name.strip()
                        tool_arg = tool_arg.strip()
                        logger.info(f"🔧 大模型决定使用工具: {tool_name}，参数: {tool_arg}")

                        # 把它的决定存入历史对话
                        messages.append({"role": "assistant", "content": raw_response})

                        # 在本地执行真实操作！
                        tool_result = ""
                        if tool_name == "read_file":
                            tool_result = read_file(tool_arg)
                        elif tool_name == "list_dir":
                            tool_result = list_dir(tool_arg)
                        elif tool_name == "execute_command":
                            # 🌟 唯一改动：加了 await，会等待你在终端输入 yes 确认
                            tool_result = await execute_command(tool_arg)
                        else:
                            tool_result = f"系统错误：找不到名为 {tool_name} 的工具。"

                        # 把执行结果作为 User 喂回给它
                        logger.info(f"📥 工具执行完毕，结果长度: {len(tool_result)} 字符，送回给模型分析。")
                        messages.append({"role": "user", "content": f"【系统自动返回的工具执行结果】\n{tool_result}"})
                    else:
                        # 如果没有输出 <TOOL> 标签，说明它认为任务完成了，给出了最终答案
                        final_output = raw_response
                        break

                if not final_output:
                    final_output = "任务执行超过 5 轮最大限制，已被系统强制终止。最后一次结果：\n" + str(messages[-1].get("content", ""))

                # 封装最终结果
                result = AggregatedResult(
                    summary="OpenClaw 执行完毕",
                    subtask_results=[],
                    final_output=final_output
                )

                state.result = result
                state.status = "completed"
                logger.info("🦞 OpenClaw 任务圆满完成！")

                return ExecuteResponse(
                    task_id=state.task_id, complexity=assessment,
                    dag=dag, result=result, status="completed",
                )
            # ==========================================
            # 🌟 OpenClaw 模式结束
            # ==========================================

            # ==========================================
            # 默认 Codex 模式 & Hermes 模式
            # ==========================================
            if image_contents:
                request.context += "\n\n【提示：用户上传了图片，但当前所选模式暂未接入视觉处理引擎，请忽略图片仅根据文本作答。】"

            # Stage 1: Analyze complexity
            analyzer = self._get_analyzer()
            assessment = await analyzer.analyze(request.requirement, request.context)
            state.complexity = assessment
            state.status = "analyzed"
            logger.info("Task %s complexity: %s (%s subtasks)", state.task_id, assessment.level.value, assessment.estimated_subtasks)

            # Stage 2: Decompose into DAG
            decomposer = self._get_decomposer()
            dag = await decomposer.decompose(request.requirement, assessment, request.context)
            state.dag = dag
            state.status = "decomposed"
            logger.info("Task %s decomposed into %d subtasks", state.task_id, len(dag.tasks))

            # Stage 3: Route to models
            router = ModelRouter(self._config)
            dag = router.route(dag, assessment.level)
            state.status = "routed"
            logger.info("Task %s routed: %s", state.task_id, [(t.id, t.assigned_model) for t in dag.tasks])

            # Stage 4: Execute DAG
            executor = DAGExecutor(
                self._registry,
                max_retries=self._config.routing.max_retries,
                timeout_seconds=self._config.routing.timeout_seconds,
            )
            subtask_results = await executor.execute(dag, request.requirement)
            state.status = "executed"
            succeeded = sum(1 for r in subtask_results if r.output)
            logger.info("Task %s executed: %d/%d succeeded", state.task_id, succeeded, len(subtask_results))

            # Stage 5: Aggregate results
            aggregator = self._get_aggregator()
            result = await aggregator.aggregate(request.requirement, subtask_results)
            state.result = result
            state.status = "completed"
            logger.info("Task %s completed", state.task_id)

            return ExecuteResponse(
                task_id=state.task_id,
                complexity=assessment,
                dag=dag,
                result=result,
                status="completed",
            )

        except Exception as e:
            state.status = "failed"
            state.error = str(e)
            logger.exception("Task %s failed", state.task_id)
            return ExecuteResponse(
                task_id=state.task_id,
                complexity=state.complexity,
                dag=state.dag,
                status="failed",
                error=str(e),
            )

    async def analyze_only(self, requirement: str, context: str = "") -> ComplexityAssessment:
        analyzer = self._get_analyzer()
        return await analyzer.analyze(requirement, context)

    async def decompose_only(self, requirement: str, context: str = "") -> tuple[ComplexityAssessment, TaskDAG]:
        analyzer = self._get_analyzer()
        assessment = await analyzer.analyze(requirement, context)
        decomposer = self._get_decomposer()
        dag = await decomposer.decompose(requirement, assessment, context)
        return assessment, dag

    def get_task(self, task_id: str) -> TaskState | None:
        return self._tasks.get(task_id)

    def _get_analyzer(self) -> ComplexityAnalyzer:
        model = self._config.routing.analyzer_model or self._config.models[0].name
        return ComplexityAnalyzer(self._registry.get(model))

    def _get_decomposer(self) -> TaskDecomposer:
        model = self._config.routing.decomposer_model or self._config.models[0].name
        return TaskDecomposer(self._registry.get(model))

    def _get_aggregator(self) -> ResultAggregator:
        model = self._config.routing.default_executor or self._config.models[0].name
        return ResultAggregator(self._registry.get(model))
