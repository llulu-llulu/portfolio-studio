# 衡量 · 投资组合分析与调仓模拟

本项目是我使用 Codex 辅助完成的固定行情快照下的本地全栈原型，对应任务书 **VC-FIN-001 / V3.0**。支持组合概览、标的/行业集中度检查、顺序调仓模拟、命名保存与只读重开。后端承担全部业务计算和校验，SQLite 保存方案；无需外部行情、账号、密钥或前端构建。

## 先看交付材料

- [PLAN.md](PLAN.md)：开工方案的候选人视角整理版；[实现前原稿](attachments/plan-original.txt)按原字节归档，保留开工记录。
- [DESIGN.md](DESIGN.md)：需求、数据、接口、取舍、AI 协作记录与复盘。
- [VERIFY.md](VERIFY.md)：实际执行的检查、数值、问题修正和截图。
- [REVIEW.md](REVIEW.md)：需求理解、功能完整性、工程质量、产品体验与 AI 协作的五维复审及修复证据。
- [DELIVERY.md](DELIVERY.md)：实际投入、交付范围、已知限制及提交包说明。
- [原始任务书](attachments/requirements.pdf)、[示例数据](attachments/sample-data.json)：从测评附件压缩包按原字节提取。
- [截图目录](output/playwright/)；[测试原始输出](output/verification/tests.txt)；[浏览器及重启结果](output/verification/browser-results.json)。

## 启动（Windows PowerShell）

支持 **Python 3.11**；已验证 Windows / Python 3.11.9、Edge 156。项目文件夹内执行：

获取项目：

```powershell
git clone https://github.com/llulu-llulu/portfolio-studio.git
cd portfolio-studio
```

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe run.py
```

打开 <http://127.0.0.1:8000>。保持终端运行，按 `Ctrl+C` 停止。无需激活虚拟环境，因此不依赖 PowerShell 执行策略。首次启动会自动建立 `data/plans.db` 及表结构，原始组合直接读取 `attachments/sample-data.json`，无需手动初始化。

macOS / Linux 的等价命令（未在本次环境实测）：

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python run.py
```

有依赖的现有 Python 环境可直接执行 `python run.py`。端口冲突时使用 `python run.py --port 8001`，对应访问 `http://127.0.0.1:8001`。

## 五分钟验收

1. 打开组合概览：总资产 **100,000.00**、现金 **20,000.00**；A01 **40.00%**、科技 **60.00%**，共两项提醒。
2. 进入调仓模拟，卖出 **A01 / 100 股**：现金 **30,000.00**，A01 **30.00%**、科技 **50.00%**，提醒清零。
3. 接着买入 **A02 / 100 股**：现金 **25,000.00**，A02 **500 股 / 25,000.00 元**，科技 **55.00%**，一项行业提醒。
4. 输入名称并保存，进入只读详情。刷新页面，再停止服务并用相同命令重启，从「已保存方案」点击同一方案，结果保持一致。保存详情的网址 `/#plan/<id>` 也可直接重开。
5. 返回概览，原始现金仍为 **20,000.00**，A01/A02 均 **400 股**。清空模拟后测试买入 A01 **201**、卖出 **401**、数量 **0 / -1 / 1.5**；均应被拒绝，已接受的结果不变。

「清空重来」清空当前模拟编辑区的交易操作和计算结果，原始组合及数据库中已保存的方案不变。临时模拟只在本次页面内存中，**刷新会丢失未保存操作**；已保存方案不受影响。

## 数据存放与运行参数

- 默认数据库路径相对于项目根目录，不随启动终端的当前目录变化。
- 使用 `python run.py --db ./data/another.db` 可建立独立方案库；也可设置 `PORTFOLIO_DB`。相对自定义路径相对于启动目录。
- 停止服务后备份数据库文件即可备份方案。不要删除数据库后再期待重开旧链接。
- 示例数据中的日期是 **2026-11-02 15:00（北京时间）**，不是实时行情。修改示例数据代表更换基准，应同步更改 `snapshot_id` 并重启；历史方案使用保存时的完整快照。
- 服务只监听本机 `127.0.0.1`；这是无登录的单用户本地原型。

## 运行验证

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -v
```

35 个测试方法覆盖计算和 API，测试使用临时 SQLite，不改动默认方案库。无需 Node.js；若本机有 Node，可额外执行 `node --check frontend/app.js`。

可选的真实浏览器验收与截图：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-qa.txt
.\.venv\Scripts\python.exe scripts/verify_browser.py
```

默认使用已安装的 Edge，自动在 **8765** 端口启动/停止测试服务，使用 `tmp/qa` 独立数据库。若只有 Chrome，先设置 `$env:QA_BROWSER_CHANNEL = 'chrome'`；macOS/Linux 可使用 `QA_BROWSER_CHANNEL=chrome`。输出会更新 `output/playwright` 和浏览器结果记录，包含一次真正的服务进程重启。仅截图验证需要 Playwright，正常运行不需要。

安装上述浏览器验证依赖后，可运行五维复审新增的交互检查：

```powershell
.\.venv\Scripts\python.exe scripts/review_browser.py
```

该检查使用 **8766** 端口和独立数据库，覆盖未保存保护、慢请求导航、保存失败重试、规则文案及键盘焦点。

## 工程结构

```text
backend/domain.py         精确金额、集中度、顺序交易的纯计算
backend/app.py            FastAPI 接口、输入约束、错误映射、静态资源
backend/storage.py        SQLite 事务、快照保存、方案重开
frontend/                 请求、格式化、组件、编辑表单、路由状态 5 个 JS 模块
tests/                    35 个计算与接口测试方法
scripts/verify_browser.py 浏览器验收、真实重启、截图
scripts/review_browser.py  五维复审的交互边界验证
scripts/package.py        生成不含依赖和运行数据库的提交压缩包
attachments/              原始 PDF / JSON、文本提取、开工原稿与哈希
output/                   验证记录、截图与提交包
run.py                    本机服务入口
requirements.lock         运行依赖完整固定版本
```

接口文档在 <http://127.0.0.1:8000/docs>。API 例子及错误约定见 DESIGN.md。

## 范围与说明

我将实现范围限定为 FR-01～FR-05，核心流程均已实现并通过现有检查。未扩展登录、行情接入、真实交易、费用税收、收益预测、方案编辑删除及公网部署。实际投入时间和 AI 使用情况见 DESIGN.md；测试、截图及核查由 AI 调用工具执行，原始记录随项目保留，验证范围见 VERIFY.md。
