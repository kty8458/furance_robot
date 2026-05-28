class MockConfig:
    status_interval: float = 5.0
    step_duration_min: float = 1.0
    step_duration_max: float = 5.0
    alarm_probability: float = 0.15
    critical_alarm_ratio: float = 0.3
    error_probability: float = 0.05
    robot_id: str = "robot_001"
    port: int = 9001
