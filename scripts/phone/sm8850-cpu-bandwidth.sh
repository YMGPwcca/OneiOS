#!/system/bin/sh
# Candidate cgroup-v1 guest CPU bandwidth actuator. No live integration yet.
# Explicit probe creates only an empty, private group and moves its own child.
set -eu
LC_ALL=C; export LC_ALL

# BEGIN SM8850_CPU_BANDWIDTH
sm8850_cpu_quota_us() (
    [ "$#" = 1 ] || exit 2
    pct=$1
    case "$pct" in ''|*[!0-9]*|0[0-9]*) exit 2 ;; esac
    [ "${#pct}" -le 3 ] && [ "$pct" -ge 10 ] && [ "$pct" -le 100 ] || exit 2
    # 8 host cores, 20 ms period, integer quota in microseconds.
    printf '%s\n' "$((1600 * pct))"
)
sm8850_cpu_quota_write() {
    printf '%s\n' "$2" > "$1/cpu.cfs_quota_us"
}
sm8850_cpu_quota_apply() (
    [ "$#" = 2 ] || exit 2
    group=$1
    quota=$(sm8850_cpu_quota_us "$2") || exit 2
    [ -d "$group" ] && [ ! -L "$group" ] || exit 2
    for node in cpu.cfs_period_us cpu.cfs_quota_us; do
        [ -f "$group/$node" ] && [ ! -L "$group/$node" ] || exit 2
    done
    [ "$(cat "$group/cpu.cfs_period_us")" = 20000 ] || exit 2
    sm8850_cpu_quota_write "$group" "$quota" || exit 2
    [ "$(cat "$group/cpu.cfs_period_us")" = 20000 ] &&
        [ "$(cat "$group/cpu.cfs_quota_us")" = "$quota" ] || exit 2
    printf 'CPU_BUDGET_PCT=%s QUOTA_US=%s PERIOD_US=20000\n' "$2" "$quota"
)
# END SM8850_CPU_BANDWIDTH

fail() { echo "CPU_BANDWIDTH_PROBE=BLOCKED $*" >&2; exit 2; }
case "${1:-}" in
    --quota-us) shift; sm8850_cpu_quota_us "$@"; exit $? ;;
    --probe) [ "$#" = 1 ] || fail usage ;;
    *) fail usage ;;
esac

stage=/data/adb/oneios-m3q-framework
root=/dev/cpuctl
[ "$(id -u)" = 0 ] && [ "$(getenforce)" = Enforcing ] || fail root_or_selinux
[ "$(getprop ro.product.model):$(getprop ro.product.device):$(getprop ro.soc.model):$(getprop ro.build.PDA)" = SM-S948B:m3q:SM8850:S948BXXS4BZIG ] || fail device_identity
[ "$(getprop sys.boot_completed)" = 1 ] && [ "$(getprop init.svc.zygote)" = running ] && pidof system_server >/dev/null || fail framework_unavailable
[ -d "$stage" ] && [ ! -L "$stage" ] && [ "$(stat -c '%u:%a' "$stage")" = 0:700 ] || fail stage_identity
[ -f "$stage/start.lock" ] && [ ! -L "$stage/start.lock" ] || fail start_lock
exec 8<"$stage/start.lock"
flock -n 0 0<&8 || fail concurrent_stage_or_launch
case "$(cat "$stage/control/state" 2>/dev/null || :)" in
    starting|running|returning)
        [ -s "$stage/control/boot" ] && [ "$(cat "$stage/control/boot")" != "$(cat /proc/sys/kernel/random/boot_id)" ] || fail active_session ;;
esac
if pidof xnuhost xnuhost-gui-bench xnuhost-tasks OneiOSDisplay oneios-display >/dev/null 2>&1; then
    fail active_guest
fi
awk '$2=="/dev/cpuctl" && $3=="cgroup" {n=split($4,a,","); for(i=1;i<=n;i++) if(a[i]=="cpu") ok=1} END {exit !ok}' /proc/mounts || fail v1_cpu_mount
[ "$(realpath "$root")" = "$root" ] || fail cpu_root_identity
[ "$(cat /sys/devices/system/cpu/online)" = 0-7 ] || fail cpu_topology
parent_period=$(cat "$root/cpu.cfs_period_us") || fail parent_period
parent_quota=$(cat "$root/cpu.cfs_quota_us") || fail parent_quota
[ "$parent_period" = 100000 ] && [ "$parent_quota" = -1 ] || fail unexpected_parent_limits
parent_membership=$(grep -E '^[0-9]+:cpu:' /proc/$$/cgroup) || fail caller_membership

group="$root/oneios_probe.$$"
[ ! -e "$group" ] && [ ! -L "$group" ] || fail group_already_exists
mkdir "$group" || fail create_private_group
cleanup() {
    rc=$?
    trap - EXIT
    if ! rmdir "$group"; then
        echo "CPU_BANDWIDTH_PROBE_CLEANUP=FAILED:$group" >&2
        rc=2
    fi
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 2' HUP INT TERM
[ "$(realpath "$group")" = "$group" ] && [ -z "$(cat "$group/cgroup.procs")" ] || fail new_group_identity
[ "$(cat "$group/cpu.cfs_quota_us")" = -1 ] || fail unexpected_new_group_limit
printf '20000\n' > "$group/cpu.cfs_period_us" || fail set_private_period
for pct in 40 10 40 100; do
    sm8850_cpu_quota_apply "$group" "$pct" || fail private_quota_readback
done
# This is only a membership/inheritance test, not a heat-generating workload.
# The probe parent, Android services, watchdog and guest are never migrated.
/system/bin/sh -s -- "$group" <<'CHILD'
set -eu
group=$1
expected="/${group##*/}"
printf '%s\n' "$$" > "$group/cgroup.procs"
grep -qxF "$$" "$group/cgroup.procs"
awk -F: -v expected="$expected" '$2=="cpu" && $3==expected {ok=1} END {exit !ok}' /proc/$$/cgroup
# awk is a child of the migrated process: verify inherited membership too.
awk -F: -v expected="$expected" '$2=="cpu" && $3==expected {ok=1} END {exit !ok}' /proc/self/cgroup
echo CPU_BANDWIDTH_CHILD_MEMBERSHIP=PASS
CHILD
[ -z "$(cat "$group/cgroup.procs")" ] || fail unexpected_remaining_tasks
[ "$(grep -E '^[0-9]+:cpu:' /proc/$$/cgroup)" = "$parent_membership" ] || fail caller_moved
[ "$(cat "$root/cpu.cfs_period_us")" = "$parent_period" ] && [ "$(cat "$root/cpu.cfs_quota_us")" = "$parent_quota" ] || fail parent_limits_changed
cat "$group/cpu.stat"
rmdir "$group" || fail remove_private_group
trap - EXIT HUP INT TERM
printf 'CPU_BANDWIDTH_PROBE_CLEANUP=PASS\nCPU_BANDWIDTH_PROBE=PASS\nPARENT_CPU_LIMITS=UNCHANGED\nGUEST_LOAD_TEST=NO\nLIVE_TAKEOVER=NO\n'
