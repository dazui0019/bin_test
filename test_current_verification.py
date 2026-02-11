#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
import time
import argparse
import csv
import subprocess
from datetime import datetime

# Add module paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Define paths to CLI scripts
POWER_CLI = os.path.join(BASE_DIR, 'power_ctrl', 'power_ctrl_cli.py')
RES_CLI = os.path.join(BASE_DIR, 'res_ctrl', 'resistance_cli.py')
SCOPE_CLI = os.path.join(BASE_DIR, 'yokogawa', 'yokogawa_pyvisa.py')

def run_cli_command(cmd_list, capture_output=False, verbose=False):
    """
    Run an external CLI command using subprocess.
    """
    if verbose:
        print(f"Running: {' '.join(cmd_list)}")
    
    try:
        if capture_output:
            result = subprocess.check_output(cmd_list, stderr=subprocess.STDOUT)
            return result.decode('utf-8').strip()
        else:
            subprocess.check_call(cmd_list, stdout=subprocess.DEVNULL if not verbose else None)
            return True
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        if capture_output and e.output:
            print(f"Output: {e.output.decode('utf-8')}")
        return None if capture_output else False

def read_config(file_path):
    """
    Read the resistance configuration file.
    Format: ID, Min, Typ, Max, Current
    """
    configs = []
    if not os.path.exists(file_path):
        print(f"Error: Config file not found at {file_path}")
        sys.exit(1)
        
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # Format: 1,2475,2500,2525,30
            parts = line.split(',')
            if len(parts) >= 5:
                config = {
                    'id': parts[0].strip(),
                    'min': float(parts[1]),
                    'typ': float(parts[2]),
                    'max': float(parts[3]),
                    'current': float(parts[4])
                }
                configs.append(config)
    return configs

def measure_scope_current(channel, ip=None, serial=None, verbose=False):
    """
    Measure Mean value from Oscilloscope using CLI.
    """
    cmd = [sys.executable, SCOPE_CLI]
    
    if ip:
        cmd.extend(['--ip', ip])
    if serial:
        cmd.extend(['--serial', serial])
        
    cmd.extend(['mean', '-c', str(channel)])
    
    # We want clean output (default behavior of 'mean' command without -v)
    # If verbose is True, we might see more log from the wrapper, but the CLI call itself 
    # should return just the number for parsing if we don't pass -v to it.
    # Actually, yokogawa.py logic says: is_clean = not self.args.verbose
    # So we should NOT pass -v to yokogawa.py if we want easy parsing.
    
    output = run_cli_command(cmd, capture_output=True, verbose=verbose)
    
    if output is None:
        return None
        
    try:
        # The output should be just the float number
        # But if there are connection logs (if quiet mode isn't perfect), we might need to filter.
        # yokogawa.py 'mean' command prints only the value if not verbose.
        # But ScopeController.connect might print "----------------" etc if not quiet.
        # Let's check yokogawa.py connect() again.
        # connect(quiet=quiet_mode) -> quiet_mode = not args.verbose
        # So if we don't pass -v, it is quiet.
        
        # However, let's be robust.
        lines = output.splitlines()
        # Take the last non-empty line
        last_line = lines[-1].strip() if lines else ""
        return float(last_line)
    except ValueError:
        print(f"Failed to parse scope output: '{output}'")
        return None

def main():
    parser = argparse.ArgumentParser(description="Current Verification Test Script")
    parser.add_argument("--config", default=os.path.join(BASE_DIR, "signal_res_list.txt"), help="Path to configuration file")
    
    # Selection arguments
    sel_group = parser.add_mutually_exclusive_group(required=True)
    sel_group.add_argument("--level", type=str, help="Specify a single level ID to test (e.g., 1)")
    sel_group.add_argument("--all", action="store_true", help="Test all levels in the configuration file")
    
    # Test coverage arguments
    parser.add_argument("--full-range", action="store_true", help="Test all resistance points (Min, Typ, Max). Default is Typ only.")
    
    parser.add_argument("--tolerance", type=float, default=5.0, help="Acceptable current tolerance in percentage (default 5%%)")
    parser.add_argument("--res-port", default="/dev/ttyUSB0", help="Serial port for Resistance Box (default: /dev/ttyUSB0)")
    parser.add_argument("--scope-ip", help="IP address for Oscilloscope (VXI-11)")
    parser.add_argument("--scope-serial", help="USB Serial for Oscilloscope")
    parser.add_argument("-c", "--scope-channel", dest="scope_ch", type=int, default=1, help="Oscilloscope Channel to measure (default: 1)")
    parser.add_argument("--power-addr", help="VISA Address for Power Supply (optional)")
    parser.add_argument("--no-save", action="store_true", help="Do not save test results to CSV file")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    # 1. Load Config
    print(f"Loading config from {args.config}...")
    configs = read_config(args.config)
    print(f"Loaded {len(configs)} configurations.")

    # 3. Prepare Result File
    csvfile = None
    writer = None
    result_file = "Not Saved"

    if not args.no_save:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_dir = os.path.join(BASE_DIR, "results")
        if not os.path.exists(results_dir):
            os.makedirs(results_dir)
        result_file = os.path.join(results_dir, f"test_result_{timestamp}.csv")
        
        print(f"\nStarting Test. Results will be saved to {result_file}")
        
        try:
            csvfile = open(result_file, 'w', newline='')
            fieldnames = ['Level_ID', 'Test_Point', 'Set_Resistance', 'Expected_Current', 'Measured_Current', 'Error_Pct', 'Result', 'Timestamp']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
        except IOError as e:
            print(f"Error creating result file: {e}")
            sys.exit(1)
    else:
        print(f"\nStarting Test. Results will NOT be saved.")
    
    results = []
    
    try:
        for cfg in configs:
            # Filter based on arguments
            if args.level and cfg['id'] != args.level:
                continue
                
            points_to_test = ['typ']
            if args.full_range:
                points_to_test = ['min', 'typ', 'max']
            
            for point in points_to_test:
                res_val = cfg[point]
                expected_current = cfg['current']
                
                print(f"\nTesting Level {cfg['id']} - {point.upper()} (Res: {res_val}, Exp Current: {expected_current})")
                
                # a. Set Resistance
                print(f"  Setting resistance to {res_val}...")
                # Command: python resistance_cli.py -p <port> -v <val>
                res_cmd = [sys.executable, RES_CLI, '-p', args.res_port, '-v', str(res_val)]
                if args.verbose:
                    res_cmd.append('--verbose')
                    
                if not run_cli_command(res_cmd, verbose=args.verbose):
                    print("  Failed to set resistance! Stopping test.")
                    break
                
                # b. Power Cycle
                print("  Restarting Power Supply...")
                
                # Turn OFF
                # Command: python power_ctrl_cli.py [-a addr] -o off
                off_cmd = [sys.executable, POWER_CLI, '-o', 'off']
                if args.power_addr:
                    off_cmd.extend(['-a', args.power_addr])
                
                run_cli_command(off_cmd, verbose=args.verbose)
                
                time.sleep(1) # Wait for power down
                
                # Turn ON
                # Command: python power_ctrl_cli.py [-a addr] -o on
                on_cmd = [sys.executable, POWER_CLI, '-o', 'on']
                if args.power_addr:
                    on_cmd.extend(['-a', args.power_addr])
                    
                if not run_cli_command(on_cmd, verbose=args.verbose):
                        print("  Failed to turn on power! Stopping test.")
                        break

                time.sleep(3) # Wait for DUT initialization and stable current
                
                # c. Measure Current
                print(f"  Measuring Current on CH{args.scope_ch}...")
                measured_val = measure_scope_current(
                    args.scope_ch, 
                    ip=args.scope_ip, 
                    serial=args.scope_serial, 
                    verbose=args.verbose
                )
                
                if measured_val is None:
                    print("  Failed to measure current (NaN or Error).")
                    measured_val = 0.0
                
                print(f"  Measured: {measured_val:.4f}")
                
                # d. Validate
                error_pct = 0.0
                if expected_current != 0:
                    error_pct = abs(measured_val - expected_current) / expected_current * 100
                
                result_status = "PASS" if error_pct <= args.tolerance else "FAIL"
                
                print(f"  Error: {error_pct:.2f}% -> {result_status}")
                
                row = {
                    'Level_ID': cfg['id'],
                    'Test_Point': point,
                    'Set_Resistance': res_val,
                    'Expected_Current': expected_current,
                    'Measured_Current': measured_val,
                    'Error_Pct': f"{error_pct:.2f}",
                    'Result': result_status,
                    'Timestamp': datetime.now().strftime("%H:%M:%S")
                }
                
                if writer:
                    writer.writerow(row)
                    csvfile.flush() # Ensure write
                
                results.append(row)

    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
    finally:
        if csvfile:
            csvfile.close()
            
        # Cleanup
        print("\nCleaning up...")
        # Try to turn off power
        try:
            cleanup_cmd = [sys.executable, POWER_CLI, '-o', 'off']
            if args.power_addr:
                cleanup_cmd.extend(['-a', args.power_addr])
            run_cli_command(cleanup_cmd, verbose=args.verbose)
        except:
            pass
            
        # Try to disconnect resistance (optional, maybe set to OPEN?)
        try:
                # Just set to OPEN if needed, or do nothing. 
                # resistance_cli has --action disconnect or -v OPEN
                cleanup_res = [sys.executable, RES_CLI, '-p', args.res_port, '-v', 'OPEN']
                run_cli_command(cleanup_res, verbose=args.verbose)
        except:
            pass

    if not args.no_save:
        print(f"\nTest Complete. Results saved to {result_file}")
    else:
        print(f"\nTest Complete. No result file generated.")

if __name__ == "__main__":
    main()
