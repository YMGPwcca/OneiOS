# Runs through the fixed read-only ADB command in s26-watchdog-attribution.py.
# /dev character nodes and existing /proc/PID/fd links are inspected with
# stat/readlink only. Content reads are confined to named metadata files.
PATH=/system/bin
export PATH
export LC_ALL=C

report() {
    printf '%s' "$1"
    shift
    for field do printf '\t%s' "$field"; done
    printf '\n'
}

model=$(getprop ro.product.model)
device=$(getprop ro.product.device)
soc=$(getprop ro.soc.model)
release=$(getprop ro.build.version.release)
build=$(getprop ro.build.version.incremental)
kernel=$(uname -r)
expected=SM-S948B:m3q:SM8850:17:S948BXXS4BZIG:6.12.69-android16-6-pb4d3caf-abogkiS948BXXS4BZIG-4k
if [ "$model:$device:$soc:$release:$build:$kernel" != "$expected" ]; then
    report error target-changed
    exit 2
fi
if [ "$(id -u)" != 0 ] || [ "$(getprop init.svc.zygote)" != running ] ||
   [ "$(getprop sys.boot_completed)" != 1 ]; then
    report error root-or-framework-unavailable
    exit 2
fi

unknown=unavailable
read_meta() { head -c 512 "$1" 2>/dev/null | tr '\t\r\n' ' '; }
link() { readlink -f "$1" 2>/dev/null || printf '%s' "$unknown"; }
char_id() {
    [ -c "$1" ] || return 1
    pair=$(stat -Lc '%t:%T' "$1" 2>/dev/null) || return 1
    case "$pair" in :*|*:|*:*:*|*[!0-9a-fA-F:]*) return 1 ;; *:*) ;; *) return 1 ;; esac
    a=${pair%:*} b=${pair#*:}
    printf '%d:%d' "0x$a" "0x$b"
}
process_start() {
    sed 's/^.*) //' "/proc/$1/stat" 2>/dev/null | awk '{print $20}'
}
watchdog_fds() {
    for fd in "/proc/$pid/fd/"*; do
        target=$(readlink "$fd" 2>/dev/null) || continue
        case "$target" in
            /dev/watchdog|/dev/watchdog[0-9]*|/dev/softdog|/dev/softdog[0-9]*) ;;
            *) continue ;;
        esac
        suffix=${target#/dev/}
        suffix=${suffix#watchdog}
        suffix=${suffix#softdog}
        case "$suffix" in *[!0-9]*) continue ;; esac
        rdev=$(char_id "$fd") || continue
        number=${fd##*/}
        ino=$(stat -Lc '%i' "$fd" 2>/dev/null) || continue
        flags=$(awk '$1=="flags:" && $2 ~ /^[0-7]+$/ { print $2; exit }' "/proc/$pid/fdinfo/$number" 2>/dev/null)
        [ "$(readlink "$fd" 2>/dev/null)" = "$target" ] || continue
        report fd "$number" "$rdev" "$target" "$ino" "${flags:-$unknown}"
    done
}

pid=$(pidof system_server 2>/dev/null)
case "$pid" in
    ''|*[!0-9]*) report owner "$unknown" ambiguous ;;
    *)
        start=$(process_start "$pid")
        fds=$(watchdog_fds)
        again=$(watchdog_fds)
        if [ -n "$start" ] && [ "$start" = "$(process_start "$pid")" ] &&
           [ "$pid" = "$(pidof system_server 2>/dev/null)" ] && [ "$fds" = "$again" ]; then
            report owner "$pid" stable
        else
            report owner "$pid" changed
        fi
        [ -z "$fds" ] || printf '%s\n' "$fds" ;;
esac
report framework "$(getprop init.svc.zygote)" "$(getprop sys.boot_completed)"
report selinux "$(getenforce)"
report cgroup_kill "$([ -e /sys/fs/cgroup/cgroup.kill ] && echo present || echo absent)"
boot_hash=$(sha256sum /proc/sys/kernel/random/boot_id 2>/dev/null)
report boot_id_sha256 "${boot_hash%% *}"

for node in /dev/watchdog /dev/watchdog[0-9]* /dev/softdog /dev/softdog[0-9]*; do
    id=$(char_id "$node") || continue
    report node "$node" "$id"
    for part in '' /device /device/driver /device/driver/module /driver /driver/module; do
        entry=/sys/dev/char/$id$part
        [ -e "$entry" ] || continue
        report char_link "$id" "${part:-/}" "$(link "$entry")"
    done
done

for dir in /sys/class/misc/watchdog /sys/class/watchdog/watchdog[0-9]*; do
    [ -d "$dir" ] || continue
    name=${dir##*/}
    [ "$dir" != /sys/class/misc/watchdog ] || name=misc
    report class "$name" "$(read_meta "$dir/dev")" "$(link "$dir")"
    for part in device device/driver device/driver/module driver driver/module; do
        if [ -e "$dir/$part" ]; then
            report class_link "$name" "$part" "$(link "$dir/$part")"
        fi
    done
    # Only standard watchdog class metadata. Omit live counter reads and
    # vendor-specific controls.
    for field in identity state timeout nowayout pretimeout; do
        value=$(read_meta "$dir/$field")
        report attribute "$name" "$field" "${value:-$unknown}"
    done
done

if [ -r /proc/config.gz ]; then
    report config_available yes
    gzip -dc /proc/config.gz 2>/dev/null |
        awk '/^(# )?CONFIG_([A-Z0-9_]*WATCHDOG[A-Z0-9_]*|[A-Z0-9_]*SOFTDOG[A-Z0-9_]*|[A-Z0-9_]*WDT[A-Z0-9_]*|[A-Z0-9_]*MAX77775[A-Z0-9_]*|IKCONFIG(_PROC)?)(=| is not set$)/ {
            print "config\t" $0
        }'
else
    report config_available no
fi
awk '{ for (i=1;i<=NF;i++) if ($i ~ /^(softdog[.]|watchdog[.]|qcom[_-](soc[_-])?wdt[._-]|sec_qc_qcom_wdt_core[.])/)
    print "bootarg\t" $i }' /proc/cmdline /proc/bootconfig 2>/dev/null
awk '$1 ~ /^(watchdog|softdog|qcom_soc_wdt|qcom_wdt_core|sec_qc_qcom_wdt_core|[a-z0-9_]*max77775[a-z0-9_]*)$/ {
    print "module\t" $1 "\t" $5
}' /proc/modules 2>/dev/null

hexnote() { od -An -v -tx1 -N 256 "$1" 2>/dev/null | tr -d ' \n'; }
for mod in watchdog softdog qcom_soc_wdt qcom_wdt_core sec_qc_qcom_wdt_core /sys/module/*max77775*; do
    name=${mod##*/}
    case "$name" in *[!a-zA-Z0-9_]*) continue ;; esac
    base=/sys/module/$name
    [ -d "$base" ] || continue
    report module_note "$name" "$(hexnote "$base/notes/.note.gnu.build-id")"
    for field in initstate srcversion version; do
        value=$(read_meta "$base/$field")
        report module_metadata "$name" "$field" "${value:-$unknown}"
    done
    for field in nowayout soft_margin soft_panic soft_noboot soft_reboot_cmd soft_active_on_boot stop_on_reboot open_timeout; do
        value=$(read_meta "$base/parameters/$field")
        [ -z "$value" ] || report module_parameter "$name" "$field" "$value"
    done
    for directory in /vendor_dlkm/lib/modules /odm_dlkm/lib/modules /system_dlkm/lib/modules /lib/modules; do
        for ko in "$directory/$name.ko" "$directory"/*/"$name.ko" "$directory"/*/*/"$name.ko"; do
            [ -f "$ko" ] || continue
            resolved=$(link "$ko")
            case "$resolved" in /vendor_dlkm/lib/modules/*|/odm_dlkm/lib/modules/*|/system_dlkm/lib/modules/*|/lib/modules/*) ;;
                *) continue ;; esac
            [ "${resolved##*/}" = "$name.ko" ] && [ -f "$resolved" ] || continue
            digest=$(sha256sum "$resolved" 2>/dev/null) || continue
            report module_sha256 "$name" "$resolved" "${digest%% *}"
        done
    done
done
report kernel_notes_sha256 "$(sha256sum /sys/kernel/notes 2>/dev/null | awk '{print $1}')"
report kernel_notes "$(od -An -v -tx1 -N 1024 /sys/kernel/notes 2>/dev/null | tr -d ' \n')"

# Symbols without addresses establish presence and module ownership, but
# cannot identify which registered callback a file descriptor uses.
awk '$3 ~ /^(softdog_(init|ping|stop|fire|dev)|watchdog_(open|release|write|dev_register|register_device)|old_wd_data|.*msm_watchdog_data.*|.*max77775.*(wdtmr|watchdog).*|qcom_(soc_)?wdt_(probe|start|stop|ping)|msm_watchdog_(probe|init|pet))$/ {
    print "symbol\t" $3 "\t" $4
}' /proc/kallsyms 2>/dev/null

# The current kernel ring buffer is bounded. Keep the first and last
# matches per family and omit kernel addresses.
dmesg | awk '
    /softdog|Software Watchdog/ { family="softdog"; keep(family); next }
    /msm_watchdog_data|qcom[ _-].*(wdt|watchdog)|sec_qc_qcom_wdt_core/ { family="soc"; keep(family); next }
    /max77775.*(wdt|watchdog)/ { family="charger"; keep(family); next }
    /watchdog[0-9]+:.*(registered|did not stop|nowayout)/ { keep("core"); next }
    function keep(f) {
        gsub(/0x[0-9a-fA-F]{12,16}/, "<address>")
        gsub(/[[:xdigit:]]{16}/, "<hex>")
        gsub(/\t/, " ")
        n[f]++
        if (n[f] <= 8) print "log\t" f "\t" $0
        else last[f]=$0
    }
    END {
        for (f in n) {
            if (n[f]>8) print "log\t" f "\t" last[f]
            print "log_matches\t" f "\t" n[f]
        }
    }'
report complete yes
