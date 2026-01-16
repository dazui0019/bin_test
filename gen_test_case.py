import os

# 配置
INPUT_FILE = "res_list.txt"
OUTPUT_FILE = "full_test_script.txt"
LED_CHANNELS = 64

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found.")
        return

    with open(INPUT_FILE, "r") as f:
        lines = f.readlines()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        # --- 头部配置 ---
        out.write("# 自动生成的 BIN 电阻全遍历测试脚本\n")
        out.write(f"# 源文件: {INPUT_FILE}\n")
        out.write("# LED通道数: 44\n")
        out.write("CONFIG RES_PORT COM11\n")
        out.write("\n")
        out.write("# 定义变量\n")
        out.write("DEF_VAR $current_val\n")
        out.write("DEF_VAR $last_stable_val\n")
        out.write("\n")

        # --- 初始上电测试 ---
        out.write("# ==========================================\n")
        out.write("TEST Case_Init \"初始上电基准测试\"\n")
        out.write("    # 初始先确保电源关闭\n")
        out.write("    POWER_OFF\n")
        out.write("    # 确保电阻断开，测试默认开路电流\n")
        out.write("    RES_OPEN\n")
        out.write("    # 假设初始上电 13.5V 20A\n")
        out.write("    POWER_ON 13.5 20.0\n")
        out.write("    WAIT 3\n")
        out.write("    READ CH4 TO $last_stable_val\n")
        out.write("    WAIT 2\n")
        out.write("    SCREENSHOT Init_Baseline\n")
        out.write("    # 初始检查: 假设开路电流为 2560mA (参考您的示例)\n")
        out.write("    CHECK_RANGE $last_stable_val 2560mA 5%\n")
        out.write("    RES_CLOSE\n")
        out.write("\n")

        # --- 循环生成测试用例 ---
        case_idx = 1
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            # 解析: R1, R2, R3, I_single
            parts = line.split(",")
            if len(parts) < 4:
                continue
            
            res_values = [p.strip() for p in parts[:3]]
            current_single = float(parts[3])
            
            # 计算总电流 (mA)
            total_current_ma = current_single * LED_CHANNELS
            
            out.write(f"# === 档位 {case_idx}: 单路 {current_single}mA (总 {total_current_ma:.1f}mA) ===\n")
            
            for i, res in enumerate(res_values):
                sub_idx = i + 1
                test_id = f"Case_{case_idx:02d}_{sub_idx}"
                test_title = f"档位{case_idx} R={res}Ω 期望{total_current_ma:.1f}mA"
                
                out.write(f"TEST {test_id} \"{test_title}\"\n")
                
                # 1. 调节电阻
                out.write(f"    # 步骤1: 调节电阻至 {res}Ω，期望电流保持不变\n")
                out.write(f"    RES_SET {res}\n")
                out.write("    WAIT 2\n")
                out.write("    READ CH4 TO $current_val\n")
                out.write("    WAIT 2\n")
                out.write(f"    SCREENSHOT {test_id}_Step1\n")
                
                # 检查不变性: 与上一次稳定值相比，允许 100mA 波动 (防止测量噪声误判)
                out.write("    CHECK_DIFF $current_val $last_stable_val 200mA\n")
                
                # 2. 重启生效
                out.write(f"    # 步骤2: 重启电源，期望电流变为 {total_current_ma:.1f}mA\n")
                out.write("    POWER_CYCLE\n")
                out.write("    WAIT 3\n")
                out.write("    READ CH4 TO $current_val\n")
                out.write("    WAIT 2\n")
                out.write(f"    SCREENSHOT {test_id}_Step2\n")
                out.write(f"    CHECK_RANGE $current_val {total_current_ma:.1f}mA 5%\n")
                
                # 更新稳定值基准
                out.write("    # 更新基准值 (增加等待以确保示波器采样稳定)\n")
                out.write("    WAIT 2\n")
                out.write("    READ CH4 TO $last_stable_val\n")
                out.write("    WAIT 2\n")
                out.write(f"    SCREENSHOT {test_id}_Baseline\n")
                out.write("\n")
            
            case_idx += 1

        # --- 结束 ---
        out.write("# 测试结束\n")
        out.write("POWER_OFF\n")

    print(f"生成完成: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()