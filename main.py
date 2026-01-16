import sys
import os
import time
import subprocess
import re
import argparse
import datetime

# --- 配置 ---
DEFAULT_SEQUENCE_FILE = "test_script.txt"

# 工具路径 (相对当前脚本路径)
PATH_POWER_CTRL = os.path.join("power_ctrl", "power_ctrl_cli.py")
PATH_RES_CTRL = os.path.join("res_ctrl", "resistance_cli.py")
PATH_YOKOGAWA = os.path.join("yokogawa", "yokogawa.py")

# 解释器
PYTHON_EXE = sys.executable

# ANSI 颜色码
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    RESET = '\033[0m'

class TestRunner:
    def __init__(self):
        self.variables = {}  # 用于存储变量: {"$val_1": 0.5, ...}
        # 全局配置字典
        self.config = {
            "RES_PORT": None,     # 电阻箱串口，例如 COM3
            "POWER_ADDR": None,   # 电源地址，例如 USB0::...
            "SCOPE_IP": None      # 示波器IP (如果需要)
        }
        self.failed_tests = []
        
        # 测试报告数据结构
        # { "id": "Case_01", "title": "Title", "result": "PASS", "expected": [], "actual": [], "note": "" }
        self.test_results = []
        self.current_test_data = None
        
        self.current_test_id = "N/A"
        self.current_test_title = ""

    def log(self, msg):
        print(f"[Run] {msg}")

    def error(self, msg):
        print(f"[ERR] {msg}")
        # 记录失败
        if self.current_test_id not in self.failed_tests:
            self.failed_tests.append(f"{self.current_test_id} ({self.current_test_title})")
        
        # 更新当前测试用例状态
        if self.current_test_data:
            self.current_test_data["result"] = "FAIL"
            # 避免重复追加太多的错误信息
            if msg not in self.current_test_data["note"]:
                self.current_test_data["note"] += f"{msg}; "

    def run_external_tool(self, cmd_list, desc):
        """执行外部 Python 工具 (支持 Ctrl+C 中断)"""
        process = None
        try:
            # 使用 Popen 以便我们可以控制子进程
            process = subprocess.Popen(
                cmd_list, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
            )
            
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                self.error(f"工具执行失败 [{desc}]: {stderr.strip()}")
                return None
            return stdout.strip()

        except KeyboardInterrupt:
            # 如果在等待子进程时按下 Ctrl+C
            if process:
                print(f"\n[系统] 正在终止子进程: {desc} ...")
                process.kill() # 强制杀死子进程
            raise # 重新抛出异常，让外层的 run() 捕获并执行紧急断电

        except Exception as e:
            if process:
                process.kill()
            self.error(f"系统异常 [{desc}]: {e}")
            return None

    def parse_value(self, val_str):
        """解析数值字符串，支持变量和单位"""
        val_str = val_str.strip()
        
        # 1. 变量替换
        if val_str.startswith("$"):
            if val_str in self.variables:
                return self.variables[val_str]
            else:
                # 严格检查: 使用未定义的变量会报错
                raise ValueError(f"使用了未定义的变量: {val_str} (请先使用 DEF_VAR 定义)")

        # 2. 百分比处理
        if val_str.endswith("%"):
            return float(val_str[:-1]) / 100.0

        # 3. 电流单位处理 (转为 A)
        lower_s = val_str.lower()
        if "ma" in lower_s:
            return float(lower_s.replace("ma", "")) / 1000.0
        elif "a" in lower_s:
            return float(lower_s.replace("a", ""))
        
        return float(val_str)

    # --- 指令实现 ---

    def cmd_def_var(self, args):
        # DEF_VAR <$VAR> [InitialValue]
        # 例如: DEF_VAR $limit
        # 例如: DEF_VAR $limit 0.5
        if len(args) < 1:
            self.error("DEF_VAR指令缺少参数。格式: DEF_VAR <$VAR> [Value]")
            return
            
        var_name = args[0]
        if not var_name.startswith("$"):
            self.error(f"变量名必须以 $ 开头: {var_name}")
            return
            
        initial_value = 0.0
        if len(args) >= 2:
            try:
                initial_value = self.parse_value(args[1])
            except Exception as e:
                self.error(f"变量初始值解析失败: {e}")
                return
        
        # 定义变量 (如果已存在则覆盖，或者您可以选择报错)
        self.variables[var_name] = initial_value
        self.log(f"定义变量: {var_name} (初始值: {initial_value})")

    def cmd_config(self, args):
        # CONFIG <Key> <Value>
        if len(args) < 2:
            self.error("CONFIG 指令缺少参数")
            return
        
        key = args[0].upper()
        value = args[1]
        self.config[key] = value
        self.log(f"配置更新: {key} = {value}")

    def cmd_test(self, args):
        # 保存上一个测试用例
        if self.current_test_data:
            self.test_results.append(self.current_test_data)
            
        self.current_test_id = args[0]
        self.current_test_title = " ".join(args[1:]).strip('"')
        
        # 初始化新用例数据
        self.current_test_data = {
            "id": self.current_test_id,
            "title": self.current_test_title,
            "result": "PASS",
            "expected": [],
            "actual": [],
            "note": ""
        }
        
        print(f"\n{'='*60}")
        print(f"测试用例: {self.current_test_id} - {self.current_test_title}")
        print(f"{'='*60}")

    def cmd_power_on(self, args):
        v = args[0] if len(args) > 0 else "12.0"
        c = args[1] if len(args) > 1 else "2.0"
        
        cmd = [PYTHON_EXE, PATH_POWER_CTRL, "-v", v, "-c", c, "-o", "on"]
        # 注入配置参数
        if self.config["POWER_ADDR"]:
            cmd.extend(["-a", self.config["POWER_ADDR"]])
            
        self.run_external_tool(cmd, f"电源上电 {v}V {c}A")
        self.log(f"电源开启: {v}V, {c}A")

    def cmd_power_off(self, args):
        cmd = [PYTHON_EXE, PATH_POWER_CTRL, "-o", "off"]
        if self.config["POWER_ADDR"]:
            cmd.extend(["-a", self.config["POWER_ADDR"]])
            
        self.run_external_tool(cmd, "电源下电")
        self.log("电源关闭")

    def cmd_power_cycle(self, args):
        # POWER_CYCLE
        # 仅执行下电 -> 等待 -> 上电，不改变电压电流设定
        
        # 1. 下电
        self.cmd_power_off([])
        
        # 2. 等待
        time.sleep(1)
        
        # 3. 上电 (仅发送 -o on)
        cmd = [PYTHON_EXE, PATH_POWER_CTRL, "-o", "on"]
        if self.config["POWER_ADDR"]:
            cmd.extend(["-a", self.config["POWER_ADDR"]])
            
        self.run_external_tool(cmd, "电源上电 (恢复输出)")
        self.log("电源已恢复开启")

    def cmd_res_set(self, args):
        val = args[0]
        # 显式添加 --action connect，确保电阻箱继电器闭合，输出有效
        cmd = [PYTHON_EXE, PATH_RES_CTRL, "-v", val, "--action", "connect"]
        # 注入配置参数
        if self.config["RES_PORT"]:
            cmd.extend(["-p", self.config["RES_PORT"]])

        self.run_external_tool(cmd, f"设置电阻 {val}")
        self.log(f"电阻设置为: {val}")

    def cmd_res_open(self, args):
        # RES_OPEN
        cmd = [PYTHON_EXE, PATH_RES_CTRL, "--action", "disconnect"]
        if self.config["RES_PORT"]:
            cmd.extend(["-p", self.config["RES_PORT"]])
        
        self.run_external_tool(cmd, "断开电阻 (OPEN)")
        self.log("电阻已断开 (OPEN)")

    def cmd_res_close(self, args):
        # RES_CLOSE
        # 仅闭合继电器，不改变当前设置的阻值
        cmd = [PYTHON_EXE, PATH_RES_CTRL, "--action", "connect"]
        if self.config["RES_PORT"]:
            cmd.extend(["-p", self.config["RES_PORT"]])
        
        self.run_external_tool(cmd, "闭合电阻 (CLOSE)")
        self.log("电阻已闭合 (CLOSE)")

    def cmd_screenshot(self, args):
        # SCREENSHOT [Label]
        label = args[0] if len(args) > 0 else "snap"
        
        # 确保 result/screen_shot 目录存在
        result_dir = os.path.join("result", "screen_shot")
        if not os.path.exists(result_dir):
            os.makedirs(result_dir)
            
        # 生成文件名: CaseID_Label_时间戳.png
        timestamp = datetime.datetime.now().strftime("%H%M%S")
        filename = f"{self.current_test_id}_{label}_{timestamp}.png"
        filepath = os.path.join(result_dir, filename)
        
        cmd = [PYTHON_EXE, PATH_YOKOGAWA, "shot", "-o", filepath]
        if self.config["SCOPE_IP"]:
            cmd.extend(["--ip", self.config["SCOPE_IP"]])
            
        self.run_external_tool(cmd, f"截图 {filename}")
        self.log(f"截图已保存: {filepath}")
        
        # 记录到报告中
        if self.current_test_data:
            # 报告在 result/ 根目录，图片在 result/screen_shot/
            img_link = f"![{label}](screen_shot/{filename})"
            self.current_test_data["note"] += f"{img_link} "

    def cmd_wait(self, args):
        sec = float(args[0])
        self.log(f"等待 {sec} 秒...")
        time.sleep(sec)

    def cmd_read(self, args):
        # READ <CH> TO <$VAR>
        if len(args) != 3 or args[1].upper() != "TO":
            self.error("READ指令格式错误。正确格式: READ <CH> TO <$VAR>")
            return

        channel = args[0].replace("CH", "").replace("ch", "")
        var_name = args[2]

        if not var_name.startswith("$"):
            self.error(f"变量名必须以 $ 开头: {var_name}")
            return

        # 检查变量是否已定义
        if var_name not in self.variables:
            self.error(f"变量 {var_name} 未定义。请先使用 DEF_VAR {var_name} 进行定义。")
            return

        cmd = [PYTHON_EXE, PATH_YOKOGAWA, "mean", "-c", channel, "--clean"]
        if self.config["SCOPE_IP"]:
            cmd.extend(["--ip", self.config["SCOPE_IP"]])

        output = self.run_external_tool(cmd, f"读取通道 {channel}")

        if output:
            try:
                val = float(output)
                self.variables[var_name] = val
                self.log(f"读取成功: {var_name} = {val:.4f} A")
            except ValueError:
                self.error(f"读取失败，返回值非数字: {output}")

    def cmd_set_var(self, args):
        # SET_VAR <$VAR> <Value>
        # 例如: SET_VAR $limit 0.5
        if len(args) != 2:
            self.error("SET_VAR指令格式错误。正确格式: SET_VAR <$VAR> <Value>")
            return
            
        var_name = args[0]
        value_str = args[1]
        
        if not var_name.startswith("$"):
            self.error(f"变量名必须以 $ 开头: {var_name}")
            return

        # 检查变量是否已定义
        if var_name not in self.variables:
            self.error(f"变量 {var_name} 未定义。请先使用 DEF_VAR {var_name} 进行定义。")
            return
            
        try:
            # 使用 parse_value 以支持从其他变量赋值或带单位的数值
            val = self.parse_value(value_str)
            self.variables[var_name] = val
            self.log(f"变量设置: {var_name} = {val}")
        except Exception as e:
            self.error(f"变量设置失败: {e}")

    def cmd_check_range(self, args):
        try:
            real_val = self.parse_value(args[0])
            expect_val = self.parse_value(args[1])
            tolerance_raw = args[2]
            
            if tolerance_raw.endswith("%"):
                tol_abs = expect_val * self.parse_value(tolerance_raw)
            else:
                tol_abs = self.parse_value(tolerance_raw)

            lower = expect_val - tol_abs
            upper = expect_val + tol_abs
            
            # 记录数据
            if self.current_test_data:
                self.current_test_data["expected"].append(f"[{lower:.4f}, {upper:.4f}]")
                self.current_test_data["actual"].append(f"{real_val:.4f}")

            if lower <= real_val <= upper:
                self.log(f"{Colors.GREEN}PASS{Colors.RESET}: {args[0]}({real_val:.4f}) 在范围 [{lower:.4f}, {upper:.4f}] 内")
            else:
                self.error(f"{Colors.RED}FAIL{Colors.RESET}: {args[0]}({real_val:.4f}) 超出范围 [{lower:.4f}, {upper:.4f}] (期望: {args[1]} ±{args[2]})")

        except Exception as e:
            self.error(f"CHECK_RANGE 执行异常: {e}")

    def cmd_check_diff(self, args):
        try:
            val_a = self.parse_value(args[0])
            val_b = self.parse_value(args[1])
            max_diff = self.parse_value(args[2])

            diff = abs(val_a - val_b)
            
            # 记录数据
            if self.current_test_data:
                self.current_test_data["expected"].append(f"Diff <= {max_diff:.4f}")
                self.current_test_data["actual"].append(f"{diff:.4f}")

            if diff <= max_diff:
                self.log(f"{Colors.GREEN}PASS{Colors.RESET}: 差异 {diff:.4f} <= 允许值 {max_diff:.4f}")
            else:
                self.error(f"{Colors.RED}FAIL{Colors.RESET}: 差异 {diff:.4f} > 允许值 {max_diff:.4f}")

        except Exception as e:
            self.error(f"CHECK_DIFF 执行异常: {e}")

    def execute_line(self, line):
        parts = line.split()
        if not parts: return
        
        cmd = parts[0].upper()
        args = parts[1:]

        if cmd == "TEST": self.cmd_test(args)
        elif cmd == "DEF_VAR": self.cmd_def_var(args)
        elif cmd == "CONFIG": self.cmd_config(args)
        elif cmd == "POWER_ON": self.cmd_power_on(args)
        elif cmd == "POWER_OFF": self.cmd_power_off(args)
        elif cmd == "POWER_CYCLE": self.cmd_power_cycle(args)
        elif cmd == "RES_SET": self.cmd_res_set(args)
        elif cmd == "RES_OPEN": self.cmd_res_open(args)
        elif cmd == "RES_CLOSE": self.cmd_res_close(args)
        elif cmd == "SCREENSHOT": self.cmd_screenshot(args)
        elif cmd == "WAIT": self.cmd_wait(args)
        elif cmd == "READ": self.cmd_read(args)
        elif cmd == "SET_VAR": self.cmd_set_var(args)
        elif cmd == "CHECK_RANGE": self.cmd_check_range(args)
        elif cmd == "CHECK_DIFF": self.cmd_check_diff(args)
        else: self.error(f"未知指令: {cmd}")

    def generate_report(self, start_time):
        """生成 Markdown 测试报告"""
        # 确保最后一个用例被添加
        if self.current_test_data and self.current_test_data not in self.test_results:
            self.test_results.append(self.current_test_data)
            
        if not self.test_results:
            return

        end_time = datetime.datetime.now()
        duration = end_time - start_time
        
        timestamp_str = end_time.strftime("%Y%m%d_%H%M%S")
        
        # 创建 result 目录
        result_dir = "result"
        if not os.path.exists(result_dir):
            os.makedirs(result_dir)
            
        report_file = os.path.join(result_dir, f"test_report_{timestamp_str}.md")
        
        total = len(self.test_results)
        passed = sum(1 for t in self.test_results if t["result"] == "PASS")
        failed = total - passed
        
        overall_result = "PASS" if failed == 0 else "FAIL"
        overall_icon = "✅" if failed == 0 else "🔴"
        
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(f"# 📄 BIN 自动化测试报告\n\n")
            f.write(f"- **测试时间**: `{end_time.strftime('%Y-%m-%d %H:%M:%S')}`\n")
            f.write(f"- **总体结果**: {overall_icon} **{overall_result}**\n")
            f.write(f"- **耗时**: `{duration}`\n\n")
            
            f.write("## 1. 📊 统计\n\n")
            f.write(f"| 总用例 | ✅ 通过 | 🔴 失败 |\n")
            f.write(f"| :---: | :---: | :---: |\n")
            f.write(f"| {total} | {passed} | {failed} |\n\n")
            
            f.write("## 2. 📝 详细记录\n\n")
            f.write("| ID | 标题 | 结果 | 预期值 | 实测值 | 备注 |\n")
            f.write("| :--- | :--- | :---: | :--- | :--- | :--- |\n")
            
            for t in self.test_results:
                icon = "✅ PASS" if t["result"] == "PASS" else "🔴 FAIL"
                
                # 处理多行显示 (如果一个Case有多个Check)
                expected_str = "<br>".join(t["expected"]) if t["expected"] else "-"
                actual_str = "<br>".join(t["actual"]) if t["actual"] else "-"
                note_str = t["note"].strip().replace("|", "\\|") # 转义表格符
                
                f.write(f"| {t['id']} | {t['title']} | {icon} | {expected_str} | {actual_str} | {note_str} |\n")
                
        print(f"\n[Report] 测试报告已生成: {report_file}")

    def run(self):
        start_time = datetime.datetime.now()
        
        # 解析命令行参数
        parser = argparse.ArgumentParser(description="自动化测试执行器")
        parser.add_argument("file", nargs="?", default=DEFAULT_SEQUENCE_FILE, help="测试序列文件路径")
        args = parser.parse_args()
        
        sequence_file = args.file

        if not os.path.exists(sequence_file):
            print(f"错误: 找不到测试文件 {sequence_file}")
            return

        print(f"开始加载测试序列: {sequence_file} ...")
        
        try:
            with open(sequence_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                self.execute_line(line)

        except KeyboardInterrupt:
            print("\n\n!!! 检测到用户中断 (Ctrl+C) !!!")
            print("正在紧急关闭电源...")
            self.cmd_power_off([]) # 强制关闭电源
            self.generate_report(start_time) # 即使中断也生成报告
            sys.exit(130)
        except Exception as e:
            print(f"\n\n[FATAL] 发生未捕获异常: {e}")
            print("尝试紧急关闭电源...")
            self.cmd_power_off([])
            self.generate_report(start_time) # 异常退出也生成报告
            sys.exit(1)

        # 正常结束
        self.generate_report(start_time)

        print("\n" + "="*60)
        if self.failed_tests:
            print(f"测试完成，存在失败用例 ({len(self.failed_tests)}个):")
            for t in self.failed_tests:
                print(f" - {Colors.RED}{t}{Colors.RESET}")
            sys.exit(1)
        else:
            print(f"所有测试执行完毕，结果: {Colors.GREEN}PASS{Colors.RESET}")
            sys.exit(0)

if __name__ == "__main__":
    runner = TestRunner()
    runner.run()