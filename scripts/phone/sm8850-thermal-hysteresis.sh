# Pure candidate policy, no device access or clock writes. Source this file.
# One call per NEW validated thermal heartbeat. Output: state:pct:latch:dwell.
# pct is an independent guest CPU duty budget, NOT a shared cpufreq MAX vote.
# The separate sensor/emergency guard remains authoritative.
sm8850_thermal_hysteresis_step() (
    [ "$#" = 6 ] || exit 3
    pct=$1 latch=$2 dwell=$3 cpu=$4 gpu=$5 ddr=$6
    for n in "$pct" "$latch" "$dwell" "$cpu" "$gpu" "$ddr"; do
        case "$n" in ''|*[!0-9]*|0[0-9]*) exit 3 ;; esac
        [ "${#n}" -le 6 ] || exit 3
    done
    [ "$pct" -ge 10 ] && [ "$pct" -le 100 ] && [ "$latch" -le 1 ] &&
        [ "$dwell" -le 4 ] || exit 3
    for n in "$cpu" "$gpu" "$ddr"; do
        [ "$n" -gt 0 ] && [ "$n" -le 200000 ] || exit 3
    done
    # Use the hottest sampled junction; battery/skin and invalid sensor
    # limits are independently enforced by the existing root guard.
    peak=$cpu
    [ "$gpu" -le "$peak" ] || peak=$gpu
    [ "$ddr" -le "$peak" ] || peak=$ddr
    if [ "$peak" -ge 80000 ] || { [ "$latch" = 1 ] && [ "$peak" -gt 70000 ]; }; then
        printf 'HARD:10:1:0\n'
        exit 0
    fi
    if [ "$latch" = 1 ]; then
        # Release the hard latch at 70 C, but do not jump to full load.
        printf 'RECOVERY:10:0:0\n'
        exit 0
    fi
    if [ "$peak" -ge 70000 ]; then
        step=10
        [ "$peak" -lt 75000 ] || step=20
        pct=$((pct - step))
        [ "$pct" -ge 10 ] || pct=10
        printf 'SOFT:%s:0:0\n' "$pct"
    elif [ "$peak" -ge 65000 ]; then
        printf 'HOLD:%s:0:0\n' "$pct"
    else
        dwell=$((dwell + 1))
        if [ "$dwell" -ge 5 ]; then
            step=5
            [ "$peak" -ge 45000 ] || step=10
            pct=$((pct + step))
            [ "$pct" -le 100 ] || pct=100
            dwell=0
        fi
        printf 'COOL:%s:0:%s\n' "$pct" "$dwell"
    fi
)
