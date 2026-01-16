# BIN 电流档位自动化测试

本项目包含用于 BIN 电流档位自动化测试的脚本工具，主要由测试执行器 (`main.py`) 和用例生成器 (`gen_test_case.py`) 组成。

## 目录结构

- `main.py`: **核心测试执行器**，负责解析测试指令并控制硬件。
- `gen_test_case.py`: **测试用例生成器**，根据电阻列表生成全遍历测试脚本。
- `test_script.txt` / `full_test_script.txt`: 测试脚本文件（指令集）。
- `res_list.txt`: 生成器的输入文件，定义了电阻组合和期望电流。
- `power_ctrl/`: 电源控制工具（子模块）。
- `res_ctrl/`: 电阻箱控制工具（子模块）。
- `yokogawa/`: 示波器读取工具（子模块）。

## 1. 测试执行器 (main.py)

`main.py` 是自动化测试的核心引擎，它读取文本格式的测试脚本，解析指令并调用底层的 Python 工具来控制硬件（电源、电阻箱、示波器）。

### 用法

```bash
# 执行默认测试脚本 (test_script.txt)
python main.py

# 执行指定测试脚本
python main.py full_test_script.txt
```

### 核心特性

- **指令驱动**：支持易读的文本指令（如 `POWER_ON`, `RES_SET`, `CHECK_RANGE`）。
- **安全保护**：支持 `Ctrl+C` 中断，中断时会自动执行紧急断电操作。
- **结果可视化**：终端输出支持颜色高亮（绿色 PASS，红色 FAIL）。
- **变量支持**：支持定义变量 (`DEF_VAR`)、读取存储 (`READ ... TO ...`) 和数值运算。
- **全局配置**：支持通过 `CONFIG` 指令动态配置串口号和设备地址。

### 常用指令示例

```text
CONFIG RES_PORT COM3        # 配置电阻箱串口
DEF_VAR $limit 0.5          # 定义变量
POWER_ON 12.0 2.0           # 电源上电 12V 2A
RES_SET 100                 # 设置电阻 100Ω
WAIT 2                      # 等待 2 秒
READ CH4 TO $val            # 读取示波器 CH4 到变量 $val
CHECK_RANGE $val 0.5 10%    # 检查 $val 是否在 0.5±10% 范围内
POWER_OFF                   # 电源下电
```

## 2. 测试用例生成器 (gen_test_case.py)

`gen_test_case.py` 用于批量生成测试用例。它读取 `res_list.txt` 中的电阻组合，生成包含完整控制逻辑的测试脚本文件 `full_test_script.txt`。

### 用法

1.  编辑 `res_list.txt`，每行格式为：`R1, R2, R3, 单路电流(mA)`。
2.  运行生成脚本：
    ```bash
    python gen_test_case.py
    ```
3.  生成的脚本 `full_test_script.txt` 可直接由 `main.py` 执行。

### 生成逻辑

- **初始状态**：生成 `Case_Init`，确保初始先执行 `POWER_OFF` 和 `RES_OPEN`，确立安全基准。
- **循环测试**：针对每一行配置，生成设置电阻、检查稳定性、重启电源、检查目标电流的完整流程。
- **变量追踪**：自动使用变量 (`$last_stable_val`) 追踪上一次的稳定值，用于 `CHECK_DIFF` 校验，防止异常跳变。

## 快速开始

1.  确认硬件连接（电源、电阻箱、示波器）。
2.  在脚本中或通过 `CONFIG` 指令配置正确的串口号 (COM口)。
3.  运行 `python gen_test_case.py` 生成最新测试用例。
4.  运行 `python main.py full_test_script.txt` 开始测试。
