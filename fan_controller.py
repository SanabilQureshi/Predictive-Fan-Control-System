import os
import configparser
import subprocess
import time
import logging
import signal
from datetime import datetime
import sys
from prometheus_client import start_http_server, Gauge, Counter

# =======================
# Prometheus Metrics
# =======================
CURRENT_TEMP = Gauge('pid_current_temperature_celsius', 'Current measured temperature of the target sensor')
TARGET_TEMP_GAUGE = Gauge('pid_target_temperature_celsius', 'Configured target temperature for the PID controller')
FAN_SPEED_PERCENT = Gauge('pid_fan_speed_percent', 'Calculated fan speed percentage sent to the server')
PID_INTEGRAL_TERM = Gauge('pid_integral_term', 'The current value of the integral component of the PID controller')
IPMI_ERRORS = Counter('pid_ipmi_errors_total', 'Total number of errors during IPMI command execution')

# =======================
# Config
# =======================
CONFIG_FILE = "config.ini"

config = configparser.ConfigParser()
if not config.read(CONFIG_FILE):
    print(f"[ERROR] Config file '{CONFIG_FILE}' not found. Exiting.")
    sys.exit(1)

def get_env_var(name):
    v = os.getenv(name)
    if not v:
        logging.error(f"Environment variable '{name}' is required but not set.")
        sys.exit(2)
    return v

IPMI_HOST = get_env_var("IPMI_HOST")
IPMI_USER = get_env_var("IPMI_USER")
IPMI_PASS = get_env_var("IPMI_PASS")

Kp = config.getfloat("pid", "kp", fallback=40.0)
Ki = config.getfloat("pid", "ki", fallback=5.5)
Kd = config.getfloat("pid", "kd", fallback=1.0)
TARGET_TEMP = config.getfloat("pid", "setpoint_temp", fallback=40)
MIN_FAN = config.getint("pid", "min_fan_speed", fallback=10)
MAX_FAN = config.getint("pid", "max_fan_speed", fallback=100)
LOOP_INTERVAL = config.getfloat("server", "loop_interval_seconds", fallback=2)

# =======================
# Logging
# =======================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    stream=sys.stdout,
)

# =======================
# PID Controller Class
# =======================
class PIDController:
    def __init__(self, Kp, Ki, Kd, min_out, max_out, dt):
        self.Kp, self.Ki, self.Kd = Kp, Ki, Kd
        self.min_out, self.max_out = min_out, max_out
        self.dt = dt
        self.integral = 0.0
        self.prev_error = 0.0

    def update(self, target_temp, measurement):
        error = target_temp - measurement
        self.integral += error * self.dt
        derivative = (error - self.prev_error) / self.dt
        output = (
            self.Kp * error
            + self.Ki * self.integral
            + self.Kd * derivative
        )
        self.prev_error = error
        return max(self.min_out, min(self.max_out, output))

# =======================
# Helper Functions
# =======================
def run_command(command, shell=False):
    try:
        result = subprocess.run(command, shell=shell, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {e.cmd}\nCode: {e.returncode}\nOut: {e.stdout}\nErr: {e.stderr}")
        IPMI_ERRORS.inc()
        return None

def hex_fan_speed(percent):
    percent = int(min(max(percent, 0), 100))
    return f"{percent:02X}"

def log_temperatures(temps):
    if not temps:
        logging.warning("No temperature data found.")
        return
    msg = "| ".join(f"{n}: {t}°C" for n, t in sorted(temps.items()))
    logging.info(f"Temps: {msg}")

def get_temperatures(ipmi_host, ipmi_user, ipmi_pass):
    cmd = [
        "ipmitool", "-I", "lanplus", "-H", ipmi_host,
        "-U", ipmi_user, "-P", ipmi_pass, "sdr", "list", "full"
    ]
    output = run_command(cmd)
    if output is None:
        return {}
    temps, idx = {}, 1
    for line in output.splitlines():
        if "degrees C" not in line:
            continue
        parts = line.split("|")
        name = parts[0].strip()
        try:
            value = int(parts[1].strip().split()[0])
        except (IndexError, ValueError):
            continue
        if name == "Temp":
            name = f"Temp_{idx}"
            idx += 1
        temps[name] = value
    return temps

def get_max_temp(temps):
    tmp1, tmp2 = temps.get("Temp_1"), temps.get("Temp_2")
    if tmp1 is not None and tmp2 is not None:
        return max(tmp1, tmp2)
    return tmp1 if tmp1 is not None else tmp2

def set_fan_speed(fan_speed_percent, ipmi_host, ipmi_user, ipmi_pass):
    hex_speed = hex_fan_speed(fan_speed_percent)
    command = [
        "ipmitool", "-I", "lanplus", "-H", ipmi_host,
        "-U", ipmi_user, "-P", ipmi_pass,
        "raw", "0x30", "0x30", "0x02", "0xff", f"0x{hex_speed}"
    ]
    run_command(command)

def initialize_fan_control(ipmi_host, ipmi_user, ipmi_pass):
    racadm_command = [
        "ssh", f"{ipmi_user}@{ipmi_host}",
        "racadm set system.thermalsettings.ThirdPartyPCIFanResponse 0"
    ]
    run_command(racadm_command)
    im_command = [
        "ipmitool", "-I", "lanplus", "-H", ipmi_host,
        "-U", ipmi_user, "-P", ipmi_pass,
        "raw", "0x30", "0x30", "0x01", "0x00"
    ]
    run_command(im_command)

def reset_fan_control_to_auto(ipmi_host, ipmi_user, ipmi_pass):
    command = [
        "ipmitool", "-I", "lanplus", "-H", ipmi_host,
        "-U", ipmi_user, "-P", ipmi_pass,
        "raw", "0x30", "0x30", "0x01", "0x01"
    ]
    run_command(command)
    logging.info("Fan control returned to AUTO mode.")

# =======================
# Main Control Loop & Signal Handling
# =======================
run = True
def handle_shutdown(signum, frame):
    global run
    logging.info("Shutting down... resetting fan control to AUTO mode.")
    reset_fan_control_to_auto(IPMI_HOST, IPMI_USER, IPMI_PASS)
    run = False

signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)

def main():
    logging.info("Initializing manual fan control...")
    initialize_fan_control(IPMI_HOST, IPMI_USER, IPMI_PASS)
    pid = PIDController(Kp, Ki, Kd, MIN_FAN, MAX_FAN, LOOP_INTERVAL)
    
    start_http_server(8000)
    logging.info("Prometheus metrics server started on port 8000")

    logging.info(f"Starting PID fan control (target_temp={TARGET_TEMP}°C, interval={LOOP_INTERVAL}s)...")
    logging.info("-------------------------------------------------------------------")
    global run
    while run:
        temps = get_temperatures(IPMI_HOST, IPMI_USER, IPMI_PASS)
        log_temperatures(temps)
        pv_temp = get_max_temp(temps)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if pv_temp is not None:
            fan_speed = pid.update(TARGET_TEMP, pv_temp)
            set_fan_speed(fan_speed, IPMI_HOST, IPMI_USER, IPMI_PASS)
            logging.info(f"Max(Temp_1,2): {pv_temp}°C | target_temp: {TARGET_TEMP}°C | Calculated fan: {int(fan_speed)}%")
            
            # Update Prometheus metrics
            CURRENT_TEMP.set(pv_temp)
            TARGET_TEMP_GAUGE.set(TARGET_TEMP)
            FAN_SPEED_PERCENT.set(fan_speed)
            PID_INTEGRAL_TERM.set(pid.integral)
            
            logging.info("-------------------------------------------------------------------")
        else:
            logging.warning(f"{now} | Temp_1/Temp_2 not found. Skipping fan adjustment.")
        time.sleep(LOOP_INTERVAL)
    # On exit
    logging.info("Exited cleanly.")

if __name__ == "__main__":
    main()
