# Trae Agent 沙箱功能

Trae Agent 的沙箱功能允许您在隔离的环境中配置开源项目的依赖环境，避免与 trae-agent 自身环境产生冲突。

## 功能特性

- **环境隔离**: 使用 Docker 容器或虚拟环境隔离项目依赖
- **自动检测**: 自动检测需要沙箱的命令（如 pip install, npm install 等）
- **多种沙箱类型**: 支持 Docker 和虚拟环境两种沙箱类型
- **优雅降级**: 沙箱启动失败时自动回退到常规执行模式

## 使用方法

### 启用沙箱模式

使用 `--sandbox` 或 `-s` 选项启用沙箱模式：

```bash
# 使用 Docker 沙箱（默认）
trae-cli run "配置这个项目的依赖环境" --sandbox --working-dir /path/to/project

# 使用虚拟环境沙箱
trae-cli run "安装项目依赖" --sandbox --sandbox-type venv --working-dir /path/to/project

# 指定项目路径和任务
trae-cli run "分析并安装这个 Python 项目的所有依赖" --sandbox -w /path/to/python-project
```

### 命令行选项

- `--sandbox`, `-s`: 启用沙箱模式
- `--sandbox-type`: 指定沙箱类型，可选值：
  - `docker`: 使用 Docker 容器（默认，推荐）
  - `venv`: 使用 Python 虚拟环境

## 沙箱类型

### Docker 沙箱（推荐）

Docker 沙箱提供最完整的环境隔离：

**优点:**
- 完全的环境隔离
- 支持所有编程语言和工具
- 不会污染主机环境
- 提供一致的基础环境

**要求:**
- 系统安装 Docker
- Docker 服务正在运行
- 具有 Docker 执行权限

**基础镜像:** `python:3.12-slim`（自动安装 git, curl, build-essential）

### 虚拟环境沙箱

适用于 Python 项目的轻量级隔离：

**优点:**
- 启动速度快
- 资源占用少
- 适合 Python 项目

**限制:**
- 仅支持 Python 环境隔离
- 无法隔离系统级依赖

## 自动沙箱触发

以下命令会自动触发沙箱模式（即使未指定 `--sandbox`）：

### 包管理命令
- `pip install`, `pip3 install`
- `npm install`, `npm i`, `yarn install`, `yarn add`
- `conda install`, `poetry install`, `poetry add`
- `gem install`, `bundle install`
- `go get`, `go mod`
- `cargo install`, `cargo add`
- `apt-get install`, `apt install`, `yum install`, `dnf install`
- `brew install`

### 虚拟环境命令
- `python -m venv`, `virtualenv`
- `conda create`, `poetry env`
- `pipenv install`

## 使用示例

### 示例 1: 配置 Python 项目依赖

```bash
trae-cli run "这是一个 Django 项目，请分析并安装所有依赖" \
    --sandbox \
    --working-dir ./my-django-project
```

Agent 会：
1. 启动 Docker 沙箱
2. 复制项目文件到沙箱
3. 分析 `requirements.txt` 或 `pyproject.toml`
4. 在沙箱中安装依赖
5. 验证安装结果

### 示例 2: 配置 Node.js 项目

```bash
trae-cli run "安装这个 React 项目的所有依赖并运行测试" \
    --sandbox \
    --working-dir ./my-react-app
```

### 示例 3: 使用虚拟环境沙箱

```bash
trae-cli run "创建虚拟环境并安装项目依赖" \
    --sandbox --sandbox-type venv \
    --working-dir ./python-project
```

## 工作流程

1. **沙箱初始化**
   - 检测沙箱类型和可用性
   - 创建隔离环境
   - 复制工作区文件

2. **依赖分析**
   - 扫描项目配置文件
   - 识别依赖管理工具
   - 分析依赖关系

3. **环境配置**
   - 在沙箱中安装依赖
   - 配置环境变量
   - 验证安装结果

4. **结果同步**
   - 将配置结果同步回主机
   - 生成环境配置报告

## 注意事项

### Docker 沙箱
- 确保 Docker 已安装并运行
- 首次使用会下载基础镜像
- 容器会在任务完成后自动清理

### 虚拟环境沙箱
- 仅适用于 Python 项目
- 需要系统 Python 环境支持
- 临时文件会在任务完成后清理

### 网络访问
- 沙箱环境可以访问互联网
- 支持从 PyPI、npm 等源安装包
- 遵循主机网络配置

## 故障排除

### Docker 相关问题

```bash
# 检查 Docker 状态
docker --version
docker ps

# 检查 Docker 权限
docker run hello-world
```

### 虚拟环境问题

```bash
# 检查 Python 版本
python --version

# 检查 venv 模块
python -m venv --help
```

### 常见错误

1. **Docker 未安装**: 安装 Docker 或使用 `--sandbox-type venv`
2. **权限不足**: 确保用户具有 Docker 执行权限
3. **磁盘空间不足**: 清理 Docker 镜像和容器
4. **网络问题**: 检查网络连接和代理设置

## 配置选项

可以通过环境变量自定义沙箱行为：

```bash
# 设置 Docker 镜像
export TRAE_SANDBOX_DOCKER_IMAGE="python:3.11-slim"

# 设置临时目录
export TRAE_SANDBOX_TEMP_DIR="/tmp/trae_sandbox"

# 启用详细日志
export TRAE_SANDBOX_VERBOSE=1
```

## 最佳实践

1. **选择合适的沙箱类型**
   - 多语言项目: 使用 Docker
   - 纯 Python 项目: 可选择虚拟环境

2. **项目准备**
   - 确保项目有完整的依赖配置文件
   - 清理不必要的临时文件

3. **任务描述**
   - 明确指定要配置的环境类型
   - 提供具体的配置要求

4. **监控资源**
   - 大型项目可能需要更多时间
   - 监控磁盘空间使用