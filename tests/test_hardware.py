import pytest

from carbon_tracker import hardware
from carbon_tracker.globals import _CPU_TDP_TABLE, _GPU_TDP_TABLE


@pytest.mark.parametrize("name,tdp", [
    ("11th Gen Intel(R) Core(TM) i7-1165G7 @ 2.80GHz", 28),
    ("Intel(R) Core(TM) i7-10700K CPU @ 3.80GHz", 125),
    ("12th Gen Intel(R) Core(TM) i7-12700K", 125),
    ("13th Gen Intel(R) Core(TM) i7-1360P", 28),
    ("12th Gen Intel(R) Core(TM) i5-1235U", 15),
    ("Intel(R) Core(TM) i7-10750H CPU @ 2.60GHz", 45),
    ("11th Gen Intel(R) Core(TM) i7-11370H @ 3.30GHz", 35),
    ("Intel(R) Core(TM) Ultra 9 285K", 125),
    ("Intel(R) Core(TM) Ultra 7 155H", 28),
    ("AMD Ryzen 9 8945HS w/ Radeon 780M Graphics", 45),
    ("AMD Ryzen 5 5600G with Radeon Graphics", 65),
    ("AMD Ryzen 9 7950X 16-Core Processor", 170),
    ("Intel(R) Xeon(R) CPU E5-2697 v3 @ 2.60GHz", 105),
])
def test_cpu_tdp_table(name, tdp):
    assert hardware._match_tdp(name, _CPU_TDP_TABLE) == tdp


@pytest.mark.parametrize("name,tdp", [
    ("AMD Radeon(TM) Graphics", 15),
    ("NVIDIA GeForce MX450", 25),
    ("NVIDIA GeForce RTX 4070 Laptop GPU", 115),
    ("NVIDIA GeForce RTX 5090 Laptop GPU", 175),
    ("NVIDIA GeForce RTX 4070", 200),
])
def test_gpu_tdp_table(name, tdp):
    assert hardware._match_tdp(name, _GPU_TDP_TABLE) == tdp


def _fake_nvidia_smi(output):
    def check_output(cmd, **kwargs):
        if cmd[0] == "nvidia-smi":
            return output
        raise FileNotFoundError(cmd[0])
    return check_output


def test_placeholder_gpu_tdp_is_rejected(monkeypatch):
    monkeypatch.setattr(hardware.subprocess, "check_output", _fake_nvidia_smi("5001.00\n"))
    assert hardware.detect_gpu_tdp_from_device(250.0) == 0.0


def test_plausible_gpu_tdp_is_kept(monkeypatch):
    monkeypatch.setattr(hardware.subprocess, "check_output", _fake_nvidia_smi("60.00\n"))
    assert hardware.detect_gpu_tdp_from_device(250.0) == 60.0


def test_detect_hardware_mx450_uses_table(monkeypatch):
    monkeypatch.setattr(hardware, "detect_cpu_name",
                        lambda: "11th Gen Intel(R) Core(TM) i7-1165G7 @ 2.80GHz")
    monkeypatch.setattr(hardware, "detect_gpu_name", lambda: "NVIDIA GeForce MX450")
    monkeypatch.setattr(hardware, "detect_is_laptop", lambda: True)
    monkeypatch.setattr(hardware, "detect_cpu_tdp_from_device", lambda: 0.0)
    monkeypatch.setattr(hardware.subprocess, "check_output", _fake_nvidia_smi("5001.00\n"))
    hw = hardware.detect_hardware()
    assert hw.cpu_tdp_watts == 28
    assert hw.gpu_tdp_watts == 25


def test_gpu_rank_prefers_discrete():
    names = ["Microsoft Basic Display Adapter", "AMD Radeon(TM) Graphics",
             "NVIDIA GeForce RTX 3050 Laptop GPU", "Intel(R) Iris(R) Xe Graphics"]
    assert max(names, key=hardware._gpu_rank) == "NVIDIA GeForce RTX 3050 Laptop GPU"
    assert hardware._gpu_rank("Microsoft Basic Display Adapter") == 0


@pytest.mark.parametrize("battery,laptop", [(True, True), (False, False)])
def test_wsl_laptop_asks_the_windows_host(monkeypatch, battery, laptop):
    from carbon_tracker import power

    monkeypatch.setattr(hardware.platform, "system", lambda: "Linux")
    monkeypatch.setattr(hardware, "_is_wsl", lambda: True)
    real_exists = hardware.os.path.exists
    monkeypatch.setattr(hardware.os.path, "exists",
                        lambda p: False if "chassis_type" in p else real_exists(p))
    monkeypatch.setattr(power, "read_battery_status", lambda: {"present": battery})
    assert hardware.detect_is_laptop() is laptop


def test_real_detection_runs():
    hw = hardware.detect_hardware()  # whatever this machine is: must not crash
    assert hw.cpu_tdp_watts > 0
    assert 0 < hw.gpu_tdp_watts <= 1500
