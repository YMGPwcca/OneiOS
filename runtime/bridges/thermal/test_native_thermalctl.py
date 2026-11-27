"""Host-only diagnostic fixture. No real sysfs, Binder, or ADB."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    tool = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="oneios-natm.") as d:
        root = Path(d)

        def write(path, value):
            f = root / path
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(value + "\n")

        def zone(i, name, value):
            write(f"sys/class/thermal/thermal_zone{i}/type", name)
            write(f"sys/class/thermal/thermal_zone{i}/temp", value)

        zone(0, "cpu-hw-trip-0", "105000")
        zone(1, "cpu-0-5-1", "104800")
        zone(2, "cpu-0-3-1", "65000")
        zone(3, "gpuss-7", "60200")
        zone(4, "ddr", "60100")
        zone(5, "gpuss-8", "101000junk")
        zone(6, "cpuss-1", "-273000")
        write("sys/class/power_supply/battery/temp", "406")
        write("sys/class/power_supply/battery/lrp", "426")
        write("sys/class/sec/sec-ap-thermistor/temperature", "503")
        for n, cap, hw in ((0, 1555200, 3628800), (6, 1497600, 4742400)):
            base = f"sys/devices/system/cpu/cpufreq/policy{n}/"
            write(base + "scaling_cur_freq", str(cap))
            write(base + "scaling_max_freq", str(cap))
            write(base + "cpuinfo_max_freq", str(hw))
            write(base + "scaling_min_freq", "787200")
        write("sys/devices/system/cpu/cpufreq_limit/cpufreq_max_limit", "1497600")
        write("sys/devices/system/cpu/cpufreq_limit/cpufreq_min_limit", "-1")
        write("sys/class/kgsl/kgsl-3d0/gpuclk", "422000000")
        write("sys/class/kgsl/kgsl-3d0/max_gpuclk", "422000000")
        write("sys/class/kgsl/kgsl-3d0/thermal_pwrlevel", "12")
        env = dict(os.environ, ONEIOS_THERMAL_ROOT=d)
        raw = subprocess.run([str(tool), "native-raw"], env=env,
                             text=True, capture_output=True, timeout=10, check=True).stdout
        expected = (
            "source=junction-max group=cpu unit=mc valid=1 value=104800",
            "source=junction-max group=gpu unit=mc valid=1 value=60200",
            "source=junction-max group=ddr unit=mc valid=1 value=60100",
            "group=gpu name=gpuss-8 unit=mc valid=0",
            "group=cpu name=cpuss-1 unit=mc valid=0",
            "source=battery field=temp unit=dc valid=1 value=406",
            "source=policy0 field=scaling_max_freq unit=khz valid=1 value=1555200",
            "source=policy6 field=scaling_max_freq unit=khz valid=1 value=1497600",
            "source=samsung-limit field=cpufreq_min_limit unit=khz valid=1 value=-1",
            "source=kgsl field=max_gpuclk unit=hz valid=1 value=422000000",
            "source=kgsl field=thermal_pwrlevel unit=index valid=1 value=12",
            "diagnostic_only=1",
        )
        for marker in expected:
            assert marker in raw, (marker, raw)
        assert "cpu-hw-trip" not in raw
        assert "value=101000" not in raw
        write("sys/class/power_supply/battery/temp", "-273")
        write("sys/class/thermal/thermal_zone3/temp", "bad")
        bad = subprocess.run([str(tool), "native-raw"], env=env,
                             text=True, capture_output=True, timeout=10)
        assert bad.returncode == 1, bad
        assert "source=battery field=temp unit=dc valid=0" in bad.stdout
        assert "source=junction-max group=gpu unit=mc valid=0" in bad.stdout
        print("NATIVE_THERMALCTL_RAW_FIXTURE=PASS DEVICE_ACCESS=NONE")


if __name__ == "__main__":
    main()
