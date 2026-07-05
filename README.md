Codex Clone — 任务编排引擎
https://img.shields.io/badge/python-3.9%252B-blue.svg
https://img.shields.io/badge/FastAPI-0.115.0-green.svg
https://img.shields.io/badge/License-MIT-yellow.svg
一个模仿 GitHub Copilot / OpenAI Codex 思路的智能任务编排引擎。用户只需输入自然语言需求，系统便会自动完成 分析复杂度 → 拆解子任务 → 分配模型 → 并行执行 → 聚合结果 五个阶段，最终输出高质量答案。
核心设计哲学：不是所有问题都需要“大模型深思熟虑”。简单翻译用便宜模型，复杂重构才调度强模型和多模型协作，在效果与成本之间取得平衡。

✨ 功能特色
    🧠 智能复杂度分析：自动判断任务难度（简单/中等/复杂），并预估子任务数量

    📋 自动任务拆解：将复杂需求拆分为带依赖关系的 DAG 子任务图

    🚀 灵活模型路由：根据复杂度级别自动选择最合适的 LLM（便宜模型处理简单任务，强大模型处理复杂任务）

    ⚡ 并行执行：DAG 中无依赖的子任务并发执行，大幅缩短总耗时

    🔗 结果聚合：多个子任务输出自动合并、去重、逻辑排序，生成最终答案

    🌐 Web 交互界面：开箱即用的中文前端，支持输入需求、查看复杂度评估、DAG 可视化与最终结果

    🔌 多模型适配：支持任意 OpenAI 兼容协议模型（DeepSeek、Qwen、GLM、文心等），通过配置文件轻松扩展
    
🏗️ 架构概览

    分析器：调用 LLM 评估任务复杂度（simple / medium / complex）、类型及预估子任务数

    拆解器：对中/复杂任务生成 DAG（每个节点为子任务，边表示依赖关系）

    路由器：根据复杂度选择模型（simple 用低成本模型，complex 可轮询多个模型）

    执行器：按拓扑顺序并行执行子任务，自动注入依赖上下文，支持重试与超时

    聚合器：合并多子任务输出，生成最终结构化结果
    <img width="727" height="773" alt="图片" src="https://github.com/user-attachments/assets/b7aa8965-b5b1-4dd1-8ff8-ec965ea2124d" />
    
📁 项目结构
text
codex-clone/
├── server.py                  # 启动入口
├── main.py                    # FastAPI 应用及全部 API 路由
├── config.yaml                # 模型配置 + 路由策略
├── requirements.txt           # Python 依赖
├── .env                       # API Key(需自己添加）
├── test_client.py             # 测试脚本
├── frontend/
│   └── index.html             # Web 前端（中文）
└── codex/                     # 核心引擎模块
    ├── models.py              # Pydantic 数据模型
    ├── config.py              # 配置加载（支持环境变量）
    ├── analyzer.py            # 第1阶段：复杂度分析
    ├── decomposer.py          # 第2阶段：任务拆解（DAG）
    ├── router.py              # 第3阶段：模型路由
    ├── executor.py            # 第4阶段：并行执行器
    ├── aggregator.py          # 第5阶段：结果聚合
    ├── pipeline.py            # 流水线编排器
    └── adapters/              # LLM 适配器
        ├── base.py            # 抽象基类
        ├── openai_compat.py   # OpenAI 兼容协议适配器
        └── registry.py        # 适配器注册中心
        
🚀 快速开始
1. 克隆仓库
git clone https://github.com/yourusername/codex-clone.git
cd codex-clone

3. 安装依赖
pip install -r requirements.txt

3. 配置 API Key（在项目根目录创建 .env 文件（或复制 .env.example），填入你的 DeepSeek API Key（其他模型可后续扩展）：
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

4. 启动服务
python server.py
服务将在 http://localhost:8000 启动，并自动打开浏览器（若未自动打开请手动访问）。

⚙️ 配置说明
config.yaml 是核心配置文件，分为两部分：
模型注册（models 段）
每个模型需指定：
    name：唯一标识
    provider：提供商（如 deepseek, qwen）
    endpoint：API 地址（支持 OpenAI 兼容协议）
    api_key_env：从 .env 读取的变量名
    capabilities：标签（如 fast, reasoning, code）
    cost_per_1k_tokens：用于成本估算（单位：美元）
    max_tokens：最大生成长度
    💡 当前已配置 DeepSeek、Qwen、GLM、文心等模型，如需启用其他模型请自行添加对应环境变量。

路由策略（routing 段）
    analysis_model / decomposer_model / executor_default_model：各阶段使用的默认模型
    parallel_threshold：当独立子任务数量 ≥ 此值时启用并行（默认 3）
    redundant_execution：复杂任务是否启用多模型冗余执行（默认 false）
    max_retries / timeout_seconds：重试与超时参数

📊 示例流程
输入：“帮我写一个用户登录系统，包含注册、登录、JWT鉴权”
    分析 → 复杂度：complex，类型：code_generation，预估子任务数：5
    拆解 → 生成 DAG：
        任务 1：设计数据库模型（无依赖）
        任务 2：实现注册接口（依赖 1）
        任务 3：实现登录接口（依赖 1）
        任务 4：实 JWT 中间件（依赖 3）
        任务 5：聚合所有代码并写测试（依赖 1,2,3,4）
    路由 → complex 任务分配多个模型（deepseek-chat, qwen-plus, glm-4）
    执行 → 按依赖层级并行：
        第 1 层：任务 1（单节点）
        第 2 层：任务 2、3（并行）
        第 3 层：任务 4（单节点）
        第 4 层：任务 5（单节点）
    聚合 → 合并所有子任务输出，返回完整代码与说明文档

🛠️ 后续优化方向
本项目是 MVP 版本，旨在展示核心编排能力。以下为待完善方向（欢迎 PR）：
    图形化 DAG 展示：在前端使用 D3.js 或 vis.js 绘制依赖图
    异步任务队列：长时间任务返回 task_id，前端轮询结果
    流式输出：实时显示执行进度与中间结果
    结果对比：多模型执行时展示不同模型输出差异
    历史记录：持久化任务状态到 SQLite / PostgreSQL
    示例模板库：内置常见任务模板（翻译、代码生成、数据分析等）
    混合判断：在 LLM 分析基础上增加规则引擎，提升稳定性
    多 API Key 支持：同一模型可配置多个 Key 实现负载均衡

🤝 贡献
欢迎提交 Issue 或 Pull Request，帮助改进这个项目！
    Fork 本仓库
    创建你的特性分支 (git checkout -b feature/AmazingFeature)
    提交修改 (git commit -m 'Add some AmazingFeature')
    推送到分支 (git push origin feature/AmazingFeature)
    打开 Pull Request

📄 许可证
本项目采用 MIT 许可证，详情请见 LICENSE 文件。
🙏 致谢
    OpenAI 与 DeepSeek 提供强大的 LLM 能力
    FastAPI 提供高性能 Web 框架
    所有开源社区贡献者
Enjoy building your intelligent task orchestrator! 🚀
