# Predictive Fan Control System

## Overview

This is my containerized Python service that automatically controls server fan speeds for my Dell R730/R720 using PID (Proportional-Integral-Derivative) feedback control. The system monitors temperature sensors via IPMI and adjusts fan speeds in real-time to maintain target temperatures, with full observability through Prometheus metrics and Grafana dashboards.

Originally built to solve noise issues in my homelab, this project combines control theory with modern commercial DevOps practices - implementing custom Prometheus instrumentation, automated Grafana provisioning, and multi-container orchestration to create a complete thermal management solution.

<img src="https://github.com/SanabilQureshi/Predictive-Fan-Control-System/blob/main/example_screenshots/Grafana.png?raw=true" height="320em" align="center" alt="Grafana Dashboard" title="Grafana Dashboard"/>

<img src="https://github.com/SanabilQureshi/Predictive-Fan-Control-System/blob/main/example_screenshots/Prometheus.png?raw=true" height="220em" align="center" alt="Prometheus" title="Prometheus Connection"/>

<img src="https://github.com/SanabilQureshi/Predictive-Fan-Control-System/blob/main/example_screenshots/PID-Log.png?raw=true" height="360em" align="center" alt="PID-Logging" title="(backend) PID logging"/>


---

## Key Features

### Core Functionality
- **PID Control Loop**: Implements a tunable PID algorithm that continuously adjusts fan speeds based on temperature feedback
- **IPMI Integration**: Communicates directly with server hardware using industry-standard IPMI protocol
- **Graceful Shutdown**: Automatically returns fans to auto mode on service termination
- **Error Handling**: Tracks and recovers from IPMI communication failures

### Infrastructure & Monitoring
- **Docker Compose Stack**: Multi-container setup with networking and service dependencies
- **Prometheus Metrics**: Custom instrumentation exposing temperature, fan speed, and error metrics via HTTP endpoint
- **Grafana Dashboards**: Pre-configured visualizations that auto-provision on deployment using Infrastructure-as-Code (IaC)
- **Environment-Based Config**: Separates sensitive credentials from code using `.env` files
- **Service Discovery**: Automated metric scraping configuration between containers

---

## Technology Stack

- **Python 3.11** with prometheus-client for metrics instrumentation
- **Docker & Docker Compose** for containerization and orchestration
- **Prometheus** for time-series metrics storage
- **Grafana** for data visualization
- **IPMI** for hardware-level server control

---

## Architecture

The system runs as three interconnected Docker containers on an isolated bridge network:

```
Fan Controller (Python) → Exposes metrics on :8000
         ↓
Prometheus → Scrapes metrics every 15 seconds → storage
         ↓
Grafana → Queries Prometheus → Real-time dashboards
```

The PID controller reads temperatures via IPMI, calculates the appropriate fan speed using the PID algorithm (with configurable Kp, Ki, Kd gains), and sends hexadecimal commands back through IPMI. All metrics are exposed via HTTP for Prometheus to collect, with Grafana providing real-time visualization through auto-provisioned dashboards.

---

## Quick Start

```bash
# 1. Clone and navigate to project
git clone [<repository-url>](https://github.com/SanabilQureshi/Predictive-Fan-Control-System) && cd Predictive-Fan-Control-System

# 2. Configure IPMI credentials

Either rename the example.env to .env or use the below bash command

cat > .env << EOF
IPMI_HOST=your-server-ip
IPMI_USER=admin
IPMI_PASS=your-password
EOF

# 3. Deploy the stack
docker-compose up --build -d

# 4. Access services
# Prometheus: http://localhost:9090
# Grafana: http://localhost:3000 (admin/admin)
```

The Grafana dashboard is automatically provisioned with panels for temperature monitoring, fan speed tracking, and error rates.

## Accessing Services

- Prometheus UI: `http://localhost:9090`
- Grafana UI: `http://localhost:3000` (default login: admin/admin)

## Monitoring Dashboard

The Grafana dashboard is **automatically provisioned** when you start the containers. No manual setup is required (but recommended if you wish to view other metrics reported by 'sdr list full')

When you access Grafana at `http://localhost:3000`:

1. Login with `admin/admin` (you'll be prompted to change the password)
2. The **PID Fan Controller Dashboard** is already available with:
   - Real-time temperature monitoring (current vs target)
   - Fan speed gauge and historical trends
   - PID integral term for tuning visibility
   - IPMI error tracking
   - Service health status

The Prometheus data source is also pre-configured, so everything should work of the box.

---

## Configuration

### PID Tuning
Edit `config.ini` to adjust the PID parameters:
```ini
[pid]
kp = 40.0          # Proportional gain (responsiveness)
ki = 5.5           # Integral gain (eliminate steady-state error)  
kd = 1.0           # Derivative gain (reduce overshoot)
target_temp = 40   # Target temperature in Celsius
```

### Monitoring Metrics

The application exposes these Prometheus metrics:
- `pid_current_temperature_celsius` - Current sensor reading
- `pid_target_temperature_celsius` - Configured target temperature
- `pid_fan_speed_percent` - Calculated fan speed (0-100%)
- `pid_integral_term` - PID integral accumulator
- `pid_ipmi_errors_total` - Count of IPMI failures

---

## Implementation Strengths

- **Security**: Non-root container execution, credentials isolated in environment variables
- **Reliability**: Container restart policies, SIGTERM/SIGINT signal handling for graceful shutdown
- **Performance**: Lightweight footprint (~50MB RAM per container), efficient 2-second control loop
- **Networking**: Isolated Docker bridge network for inter-service communication
- **Monitoring**: 100% instrumented with custom Prometheus collectors tracking all critical paths
- **Automation**: Zero-touch dashboard deployment through Grafana provisioning configs

---

## Future Improvements

- Add AlertManager for temperature threshold notifications
- Implement Kubernetes deployment with Helm charts
- Support for multiple temperature zones
- Integration with other monitoring stacks (ELK, Datadog)

