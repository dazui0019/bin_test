# Current Verification Test Script

此脚本 (`test_current_verification.py`) 用于自动化测试设备的电流验证流程。它通过控制电阻箱、电源和示波器，验证在不同电阻设置下，设备的工作电流是否符合预期。

## 功能介绍

*   **自动化测试流程**：自动设置电阻 -> 重启电源 -> 等待稳定 -> 读取示波器电流值 -> 判定结果。
*   **灵活的测试范围**：
    *   支持指定测试某个档位 (`--level`) 或所有档位 (`--all`)。
    *   支持仅测试典型值 (默认) 或全范围测试 (最小值/典型值/最大值, `--full-range`)。
*   **硬件控制**：通过调用现有的 CLI 脚本 (`resistance_cli.py`, `power_ctrl_cli.py`, `yokogawa_pyvisa.py`) 间接控制硬件，无需直接占用设备连接。
*   **结果记录**：自动将测试结果保存为 CSV 文件至 `./results/` 目录，包含详细的测量数据和 PASS/FAIL 判定。
*   **安全清理**：测试结束或中断后，自动关闭电源并断开电阻箱。

## 依赖文件

*   `signal_res_list.txt`: 配置文件，定义了每个档位的电阻值（Min, Typ, Max）和预期电流值。
*   `res_ctrl/resistance_cli.py`: 电阻箱控制脚本。
*   `power_ctrl/power_ctrl_cli.py`: 电源控制脚本。
*   `yokogawa/yokogawa_pyvisa.py`: 示波器控制脚本。

## 使用方法

### 基本用法

1.  **测试指定档位 (例如档位 1)**
    ```bash
    uv run test_current_verification.py --level 1
    ```

2.  **测试所有档位**
    ```bash
    uv run test_current_verification.py --all
    ```

3.  **全范围测试 (Min, Typ, Max)**
    测试档位 1 的所有电阻点：
    ```bash
    uv run test_current_verification.py --level 1 --full-range
    ```

4.  **指定示波器通道**
    使用通道 2 进行测量：
    ```bash
    uv run test_current_verification.py --level 1 -c 2
    ```

5.  **不保存结果**
    仅在终端显示，不生成 CSV 文件：
    ```bash
    uv run test_current_verification.py --level 1 --no-save
    ```

### 参数说明

*   `--level ID`: 指定测试的档位 ID。
*   `--all`: 测试配置文件中的所有档位。
*   `--full-range`: 测试电阻的 Min, Typ, Max 三个值（默认仅测试 Typ）。
*   `--tolerance PCT`: 允许的误差百分比（默认 5%）。
*   `-c`, `--scope-channel`: 示波器测量通道（默认 1）。
*   `--no-save`: 不保存结果文件。
*   `--res-port`: 电阻箱串口端口（默认 `/dev/ttyUSB0`）。
*   `--scope-ip` / `--scope-serial`: 示波器连接参数。
*   `--power-addr`: 电源 VISA 地址。

## 代码执行逻辑

脚本的主要执行流程如下：

1.  **初始化**：
    *   解析命令行参数。
    *   读取 `signal_res_list.txt` 配置文件。
    *   创建 `./results/` 目录（如果不存在）并初始化 CSV 结果文件。

2.  **测试循环**：
    *   遍历配置文件中的每个条目（根据 `--level` 或 `--all` 筛选）。
    *   确定测试点（仅 Typ 或 Min/Typ/Max）。
    *   **步骤 A: 设置电阻**
        *   调用 `resistance_cli.py` 将电阻箱设置为目标值。
    *   **步骤 B: 电源重启**
        *   调用 `power_ctrl_cli.py` 关闭电源。
        *   等待 1 秒。
        *   调用 `power_ctrl_cli.py` 打开电源。
        *   等待 3 秒（让被测设备初始化并稳定电流）。
    *   **步骤 C: 测量电流**
        *   调用 `yokogawa_pyvisa.py` 读取示波器指定通道的平均值 (`mean`)。
    *   **步骤 D: 结果判定**
        *   计算测量值与预期值的误差百分比。
        *   如果误差小于 `--tolerance`，判定为 **PASS**，否则为 **FAIL**。
    *   **步骤 E: 记录**
        *   将数据写入 CSV 文件并在终端打印。

3.  **清理 (Cleanup)**：
    *   无论测试成功完成还是被用户中断 (Ctrl+C)，都会执行清理步骤。
    *   **关闭电源**：确保设备断电。
    *   **断开电阻**：将电阻箱设为 OPEN 状态。
