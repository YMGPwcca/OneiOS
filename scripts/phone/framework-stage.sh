#!/system/bin/sh
# Invoked from a new, root-owned upload directory by sm8850-takeover.py.
set -eu
umask 077
incoming=$1
operation=$2
stage=/data/adb/oneios-m3q-framework
bench=/data/local/tmp/oneios-m3q-ios27-bench
MIN_FREE=31457280

fail() { echo "STAGING REFUSED: $*" >&2; exit 2; }
root_dir() { [ ! -L "$1" ] && [ "$(stat -c '%u:%a' "$1")" = 0:700 ]; }
file_id() { stat -c '%d:%i:%s:%Y:%Z' "$1"; }
hash_of() { sha256sum "$1" | cut -d' ' -f1; }

[ "$(id -u)" = 0 ] && root_dir /data/adb && root_dir "$incoming" || fail "untrusted stage parent"
[ "$(getprop ro.product.model):$(getprop ro.product.device):$(getprop ro.soc.model)" = SM-S948B:m3q:SM8850 ] ||
    fail "device identity changed"
[ "$(getprop sys.boot_completed)" = 1 ] && [ "$(getenforce)" = Enforcing ] ||
    fail "One UI must be running and SELinux enforcing"
[ "$(getprop init.svc.zygote)" = running ] && pidof system_server >/dev/null || fail "Framework unavailable"

root_file() {
    [ -f "$1" ] && [ ! -L "$1" ] && [ "$(stat -c '%u:%a' "$1")" = 0:700 ]
}
install_stage() {
    if [ ! -d "$stage" ]; then
        mkdir -m 700 "$stage" || fail "cannot create the experimental stage"
    fi
    root_dir "$stage" || fail "untrusted experimental stage"
    [ ! -L "$stage/start.lock" ] || fail "untrusted start lock"
    # Android mksh does not inherit exec-opened FD 8 into external commands.
    # Duplicate the same open file description into flock's FD 0.
    exec 8>>"$stage/start.lock"
    flock -n 0 0<&8 || fail "a switch or stage operation is starting"
    state=$(cat "$stage/control/state" 2>/dev/null || :)
    case "$state" in
        starting|running|returning)
            [ -s "$stage/control/boot" ] &&
                [ "$(cat "$stage/control/boot")" != "$(cat /proc/sys/kernel/random/boot_id)" ] ||
                fail "experimental session still open on this boot" ;;
    esac
    # Never stage over a live XNU or iOS helper, even with stale control files.
    if pidof xnuhost xnuhost-gui-bench xnuhost-tasks OneiOSDisplay oneios-display >/dev/null 2>&1; then
        fail "guest or display helper active during stage installation"
    fi
    [ "$(getprop init.svc.zygote)" = running ] &&
        pidof system_server >/dev/null 2>&1 ||
        fail "Android Framework not healthy before staging"
    for name in oneios_switch.sh oneios_return.sh oneios-watchdog; do
        [ -f "$incoming/$name" ] && [ ! -L "$incoming/$name" ] ||
            fail "untrusted incoming $name"
        if [ -e "$stage/$name" ] || [ -L "$stage/$name" ]; then
            root_file "$stage/$name" || fail "untrusted installed $name"
        fi
    done
    # The native watchdog supervisor is not being changed by this
    # OneOS compatibility patch. Do not silently swap its binary.
    if [ -e "$stage/oneios-watchdog" ] &&
        ! cmp -s "$incoming/oneios-watchdog" "$stage/oneios-watchdog"; then
        fail "native watchdog supervisor changed; require separate qualification"
    fi
    if [ "$operation" = upgrade ]; then
        for name in oneios_switch.sh oneios_return.sh oneios-watchdog; do
            [ -f "$stage/$name" ] || fail "cannot upgrade incomplete stage $name"
        done
        if cmp -s "$incoming/oneios_switch.sh" "$stage/oneios_switch.sh" &&
           cmp -s "$incoming/oneios_return.sh" "$stage/oneios_return.sh"; then
            echo "Experimental recovery scripts are already identical"
            return 0
        fi
        [ ! -L "$stage/.rollback" ] || fail "untrusted rollback directory"
        [ -d "$stage/.rollback" ] || mkdir -m 700 "$stage/.rollback" ||
            fail "cannot create rollback archive directory"
        root_dir "$stage/.rollback" || fail "untrusted rollback archive directory"
        backup=$(mktemp -d "$stage/.rollback/oneos-compat.XXXXXXXX") ||
            fail "cannot allocate rollback archive"
        root_dir "$backup" || fail "untrusted rollback archive"
        for name in oneios_switch.sh oneios_return.sh oneios-watchdog; do
            cp -p "$stage/$name" "$backup/$name" || fail "backup failed for $name"
            cmp -s "$stage/$name" "$backup/$name" || fail "backup verification failed for $name"
            sha256sum "$backup/$name" >> "$backup/old.sha256" ||
                fail "cannot record previous file hash"
        done
        # Prepare files before replacing anything. The old scripts remain
        # in .rollback with original hashes and the live logs stay untouched.
        for name in oneios_switch.sh oneios_return.sh; do
            [ ! -e "$stage/$name.oneios-new" ] && [ ! -L "$stage/$name.oneios-new" ] ||
                fail "unexpected pending stage upgrade for $name"
            install -m 700 "$incoming/$name" "$stage/$name.oneios-new" ||
                fail "cannot stage replacement $name"
            cmp -s "$incoming/$name" "$stage/$name.oneios-new" ||
                fail "replacement verification failed for $name"
        done
        for name in oneios_switch.sh oneios_return.sh; do
            mv -f "$stage/$name.oneios-new" "$stage/$name" ||
                fail "cannot atomically install $name"
            sha256sum "$stage/$name" >> "$backup/new.sha256" ||
                fail "cannot record installed file hash"
        done
        echo "ONEOS_STAGE_UPGRADE=PASS_BACKUP_PRESERVED:$backup"
        return 0
    fi
    for name in oneios_switch.sh oneios_return.sh oneios-watchdog; do
        if [ -e "$stage/$name" ]; then
            [ ! -L "$stage/$name" ] && cmp -s "$incoming/$name" "$stage/$name" ||
                fail "existing $name differs; run the separately confirmed reboot stage-check upgrade"
        else
            install -m 700 "$incoming/$name" "$stage/$name" ||
                fail "cannot install missing stage artifact $name"
        fi
    done
}

case "$operation" in
    install|upgrade) install_stage; exit ;;
    probe|prepare|rearm-data) ;;
    *) fail "unknown staging operation" ;;
esac
chmod 700 "$incoming/image-copy"
printf 'SM8850 reflink probe\n' > "$incoming/source"
: > "$incoming/destination"
if "$incoming/image-copy" reflink "$incoming/source" "$incoming/destination"; then
    cmp -s "$incoming/source" "$incoming/destination" || fail "errored reflink validation"
    printf 'changed clone\n' > "$incoming/destination"
    grep -qx 'SM8850 reflink probe' "$incoming/source" || fail "reflink write changed the source"
    clone=reflink
else
    [ "$?" = 3 ] || fail "unexpected failure in reflink probe"
    clone=sparse
    truncate -s 2M "$incoming/source"
    : > "$incoming/sparse"
    "$incoming/image-copy" sparse "$incoming/source" "$incoming/sparse"
    cmp -s "$incoming/source" "$incoming/sparse" || fail "sparse copy changed probe data"
    printf 'Sparse probe size=%s bytes, allocated=%s blocks\n' \
        "$(stat -c %s "$incoming/sparse")" "$(stat -c %b "$incoming/sparse")"
fi
printf 'Filesystem %s, selected clone method %s\n' "$(stat -f -c %T "$incoming")" "$clone"
[ "$operation" != probe ] || exit 0
if pidof xnuhost xnuhost-gui-bench xnuhost-tasks OneiOSDisplay oneios-display >/dev/null; then
    fail "benchmark or display process active"
fi

# Every attempted guest takeover consumes the APFS clone before Framework
# stop. The earlier real guest subsequently WROTE to that private clone.
# Rearm only from the ORIGINAL benchmark Data seed, never from consumed
# guest Data. Keep the previous Data and data.consumed as an archived pair;
# preserve evidence even when guest Data was modified. No image rebuild.
if [ "$operation" = rearm-data ]; then
    install_stage
    # One physical failure was specifically Android BusyBox refusing a
    # single-file remount. Verify the REPLACEMENT directory-bind strategy
    # using the phone's own BusyBox, F2FS and isolated mount namespace,
    # while One UI and its Framework are healthy. No global mount changes.
    bb_probe=
    for candidate in /data/adb/ksu/bin/busybox /data/adb/ap/bin/busybox /data/adb/magisk/busybox; do
        [ ! -x "$candidate" ] || { bb_probe=$candidate; break; }
    done
    [ -n "$bb_probe" ] || fail "root manager BusyBox missing for isolated mount probe"
    mkdir -m 700 "$incoming/mount-source" "$incoming/mount-target" ||
        fail "cannot create mount namespace probe"
    mkdir -p "$incoming/mount-source/data" "$incoming/mount-source/session/tmp" "$incoming/mount-source/control"
    # BusyBox on this Samsung failed a single-operand remount even for a
    # directory bind; use SOURCE+TARGET as in the live guest --inner path.
    # The probe must run in an unshared namespace while One UI is running.
    if ! "$bb_probe" unshare -m /system/bin/sh -s -- "$incoming/mount-source" "$incoming/mount-target" "$bb_probe" <<'ONEIOS_MOUNT_PROBE'
set -eu
src=$1 dst=$2 bb=$3
"$bb" mount --make-rprivate /
"$bb" mount --bind "$src" "$dst"
for d in data session; do
    "$bb" mount --bind "$dst/$d" "$dst/$d"
done
"$bb" mount -o remount,bind,ro "$dst" "$dst"
if true 2>/dev/null > "$dst/.unexpected-write"; then exit 12; fi
if true 2>/dev/null > "$dst/control/.unexpected-write"; then exit 13; fi
for writable in "$dst/data" "$dst/session/tmp"; do
    p="$writable/.probe-write.$$"
    (set -C; true 2>/dev/null > "$p") || exit 14
    rm -f "$p" || exit 15
done
ONEIOS_MOUNT_PROBE
    then
        fail "Android BusyBox cannot create read-only guest stage and writable Data/session mounts"
    fi
    echo "SM8850_MOUNT_NAMESPACE_PROBE=PASS_NO_FRAMEWORK_STOP"
    [ "$(cat "$stage/image.ready" 2>/dev/null)" = sm8850-ios27-3d-8cpu-600s ] &&
        [ "$(sed -n 's/^xnuhost=//p' "$stage/runtime.conf" 2>/dev/null)" = bin/xnuhost ] ||
        fail "prepared 3D image/runtime stage was not verified"
    [ -f "$stage/data.consumed" ] && [ ! -L "$stage/data.consumed" ] &&
        [ "$(stat -c '%u:%a:%h' "$stage/data.consumed")" = 0:600:1 ] ||
        fail "the one-shot APFS Data consumption record is missing or untrusted"
    [ -d "$stage/data" ] && root_dir "$stage/data" ||
        fail "consumed Data directory missing or untrusted"
    extra=$(find "$stage/data" -mindepth 1 -maxdepth 1 ! -name data.img ! -name unique-chip-id -print -quit)
    [ -z "$extra" ] || fail "consumed Data has unexpected files; preserve and inspect manually"
    [ "$(df -Pk "$stage" | awk 'NR==2 {print $4}')" -ge "$((MIN_FREE + 8388608 + 65536))" ] ||
        fail "not enough free space for one fresh APFS Data clone plus reserve"
    # The original benchmark Data is a DIFFERENT file from the guest's
    # private, already-consumed clone. The guest is allowed to modify its
    # clone, so equality with the original is NOT a valid rearm predicate.
    # Still verify each original file's fixed path, size, regular inode,
    # single link, SHA-256 and stable identity throughout cloning.
    # Historical source authenticity cannot be inferred from a newly
    # computed hash; this is the operator-selected existing benchmark seed.
    mkdir -m 700 "$incoming/data" || fail "cannot prepare isolated replacement Data"
    for name in data.img unique-chip-id; do
        old="$stage/data/$name"
        source="$bench/data/$name"
        [ -f "$old" ] && [ ! -L "$old" ] &&
            [ "$(stat -c '%u:%a:%h' "$old")" = 0:600:1 ] ||
            fail "consumed Data input is not private: $name"
        [ "$(realpath "$source")" = "$source" ] && [ -f "$source" ] &&
            [ ! -L "$source" ] || fail "original Data seed is unsafe: $name"
        expected_size=8
        [ "$name" != data.img ] || expected_size=8589934592
        [ "$(stat -c %s "$old")" = "$expected_size" ] &&
            [ "$(stat -c %s "$source")" = "$expected_size" ] ||
            fail "APFS Data size changed: $name"
        [ "$(stat -c %h "$source")" = 1 ] &&
            [ "$(stat -c '%d:%i' "$source")" != "$(stat -c '%d:%i' "$old")" ] ||
            fail "APFS original seed aliases the already-consumed guest Data: $name"
        source_id=$(file_id "$source") || fail "cannot identify Data seed: $name"
        source_sha=$(hash_of "$source") || fail "cannot hash original Data seed: $name"
        old_id=$(file_id "$old") || fail "cannot identify guest Data: $name"
        old_sha=$(hash_of "$old") || fail "cannot hash consumed guest Data: $name"
        [ "$(file_id "$old")" = "$old_id" ] ||
            fail "consumed guest Data changed during rearm inspection: $name"
        if [ "$old_sha" != "$source_sha" ]; then
            # Expected after a REAL iOS guest ran. The consumed guest's
            # writable state will be MOVED TO AN ARCHIVE, never overwritten.
            echo "APFS_CONSUMED_GUEST_DATA=MODIFIED_PRESERVE_OLD:$name"
            echo "APFS_REARM_ORIGINAL_SOURCE=EXISTING_BENCHMARK_SEED_NOT_HISTORICALLY_ATTESTED"
        else
            echo "APFS_CONSUMED_GUEST_DATA=MATCHES_SOURCE_STILL_PRESERVE_OLD:$name"
        fi
        printf '%s  %s\n' "$old_sha" "$name" >> "$incoming/consumed-data.sha256" ||
            fail "cannot record consumed guest Data digest"
        printf '%s  %s\n' "$source_sha" "$name" >> "$incoming/rearm-source.sha256" ||
            fail "cannot record benchmark seed digest"
        dest="$incoming/data/$name"
        (set -C; true > "$dest") || fail "replacement Data output already exists: $name"
        "$incoming/image-copy" "$clone" "$source" "$dest" ||
            fail "failed to clone untouched APFS source: $name"
        [ "$(stat -c '%s:%h' "$dest")" = "$expected_size:1" ] &&
            [ "$(stat -c '%d:%i' "$dest")" != "$(stat -c '%d:%i' "$source")" ] &&
            [ "$(hash_of "$dest")" = "$source_sha" ] &&
            [ "$(file_id "$source")" = "$source_id" ] ||
            fail "replacement Data clone hash or source identity changed: $name"
        echo "APFS_DATA_FRESH_CLONE_VERIFIED=$name"
    done
    [ ! -e "$stage/image.ready.rearm-pending" ] &&
        [ ! -L "$stage/image.ready.rearm-pending" ] ||
        fail "previous incomplete Data rearm; manual recovery required"
    [ ! -L "$stage/.retired-data" ] || fail "untrusted consumed Data archive"
    [ -d "$stage/.retired-data" ] ||
        mkdir -m 700 "$stage/.retired-data" || fail "cannot create consumed Data archive"
    root_dir "$stage/.retired-data" || fail "untrusted consumed Data archive"
    archive=$(mktemp -d "$stage/.retired-data/consumed.XXXXXXXX") ||
        fail "cannot allocate consumed Data archive"
    root_dir "$archive" || fail "untrusted consumed Data archive entry"
    # Fail-closed: revoke guest admission FIRST. No crash or concurrent
    # observer may see a ready marker while Data is being replaced.
    mv "$stage/image.ready" "$stage/image.ready.rearm-pending" ||
        fail "could not disarm staged image for Data rearm"
    mv "$stage/data" "$archive/data" ||
        fail "could not archive consumed APFS Data"
    mv "$stage/data.consumed" "$archive/data.consumed" ||
        fail "could not archive consumed Data record"
    # Archive both hashes for later comparison without modifying the
    # 8 GiB guest snapshot or its historical consumption marker.
    mv "$incoming/consumed-data.sha256" "$archive/consumed-data.sha256" ||
        fail "could not archive consumed guest Data digests"
    mv "$incoming/rearm-source.sha256" "$archive/rearm-source.sha256" ||
        fail "could not archive benchmark seed digests"
    mv "$incoming/data" "$stage/data" ||
        fail "could not publish new isolated APFS Data"
    sync
    mv "$stage/image.ready.rearm-pending" "$stage/image.ready" ||
        fail "could not re-arm verified image after fresh Data publish"
    echo "APFS_DATA_REARMED=YES"
    echo "PREVIOUS_DATA_ARCHIVED=$archive"
    echo "LIVE_FRAMEWORK_STOP=NO"
    exit 0
fi

# The host validates the allowlist and supplies expected hashes from the
# validated bench. Runtime and image trees are assembled from listed files.
[ -s "$incoming/bench.sha256" ] || fail "empty benchmark manifest"
mkdir "$incoming/image" "$incoming/runtime" "$incoming/data"
mkdir -m 700 "$incoming/runtime/bin"
while read -r sha path; do
    case "$path" in image/*) ;; *) fail "unexpected non-image artifact path" ;; esac
    canonical=$(realpath "$bench/$path") || fail "source missing: $path"
    [ "$canonical" = "$bench/$path" ] && [ -f "$canonical" ] || fail "source is not a regular benchmark file: $path"
done < "$incoming/bench.sha256"
for name in data.img unique-chip-id; do
    [ "$(realpath "$bench/data/$name")" = "$bench/data/$name" ] && [ -f "$bench/data/$name" ] ||
        fail "invalid APFS Data input $name"
done
[ "$(stat -c %s "$bench/data/data.img")" = 8589934592 ] &&
    [ "$(stat -c %s "$bench/data/unique-chip-id")" = 8 ] || fail "unexpected APFS Data input sizes"

free=$(df -Pk "$incoming" | awk 'NR==2 {print $4}')
estimated=0
if [ "$clone" = sparse ]; then
    # Reserve the source's full logical sizes. Sparse copying can use less,
    # and F2FS compression can make a destination larger than stat's blocks.
    estimated=$(
        { awk '{print $2}' "$incoming/bench.sha256"; printf '%s\n' data/data.img data/unique-chip-id; } |
            while read -r path; do stat -c %s "$bench/$path" || exit 2; done |
            awk '{ bytes += $1 } END { printf "%.0f", int((bytes + 1023)/1024) }'
    )
fi
printf 'free=%s KiB reserve=%s KiB clone_upper_bound=%s KiB\n' "$free" "$MIN_FREE" "$estimated"
[ "$free" -ge "$((MIN_FREE + estimated + 65536))" ] ||
    fail "insufficient space for an isolated snapshot and the benchmark reserve"

install_stage
# Earlier reboot-only smokes intentionally created an EMPTY $stage/data
# even though no iOS guest was ever started. Preserve any non-empty tree,
# but allow replacing this verified empty placeholder with a fresh clone.
if [ -d "$stage/data" ]; then
    root_dir "$stage/data" || fail "untrusted existing stage Data placeholder"
    [ ! -L "$stage/data" ] || fail "stage Data is a symlink"
    [ ! -e "$stage/data.consumed" ] || fail "one-shot Data was already used"
    [ -z "$(find "$stage/data" -mindepth 1 -maxdepth 1 -print -quit)" ] ||
        fail "existing Data directory has contents; preserve it"
    rmdir "$stage/data" || fail "could not retire empty smoke Data placeholder"
fi
for name in runtime image data runtime.conf image.conf runtime.sha256 image.sha256 image.ids image.ready; do
    [ ! -e "$stage/$name" ] && [ ! -L "$stage/$name" ] || fail "existing output $name needs preservation"
done

copy_one() {
    from=$1 to=$2 expected=$3
    [ "$(realpath "$from")" = "$from" ] && [ -f "$from" ] || fail "source changed: $from"
    before=$(file_id "$from") || fail "source identity unavailable: $from"
    mkdir -p "${to%/*}"
    (set -C; true > "$to") || fail "destination already exists"
    "$incoming/image-copy" "$clone" "$from" "$to" || fail "clone failed: $from"
    [ "$(stat -c '%s:%h' "$to")" = "$(stat -c %s "$from"):1" ] &&
        [ "$(stat -c '%d:%i' "$from")" != "$(stat -c '%d:%i' "$to")" ] || fail "clone identity/size mismatch: $from"
    [ "$(hash_of "$to")" = "$expected" ] && [ "$(file_id "$from")" = "$before" ] ||
        fail "clone hash or source identity changed: $from"
    printf '%s %s bytes %s\n' "$clone" "$(stat -c %s "$to")" "${to#"$incoming/"}"
}

: > "$incoming/runtime.sha256"
: > "$incoming/image.sha256"
: > "$incoming/image.ids"
while read -r sha path; do
    dest=$path
    copy_one "$bench/$path" "$incoming/$dest" "$sha"
    printf '%s  %s\n' "$sha" "${dest#*/}" >> "$incoming/${dest%%/*}.sha256"
    if [ "${dest%%/*}" = image ]; then
        printf '%s  %s\n' "$(stat -c '%d:%i:%s:%Y' "$incoming/$dest")" "${dest#*/}" >> "$incoming/image.ids"
    fi
done < "$incoming/bench.sha256"
for name in data.img unique-chip-id; do
    from="$bench/data/$name"
    data_before=$(file_id "$from")
    data_sha=$(hash_of "$from")
    copy_one "$from" "$incoming/data/$name" "$data_sha"
    [ "$(file_id "$from")" = "$data_before" ] || fail "APFS source changed while hashing"
done
# Import the exact 3D/touch-capable binaries from the same local build as
# the validated non-takeover SHM demo. Never accept old 2D bench binaries
# as the active takeover runtime. Validate on device after the ADB tar upload.
[ -f "$incoming/native.sha256" ] && [ ! -L "$incoming/native.sha256" ] ||
    fail "signed 3D runtime artifact checksum list missing"
[ "$(wc -l < "$incoming/native.sha256")" -eq 4 ] ||
    fail "the GPU-3D artifact list must have exactly four expected files"
for name in xnuhost oneios-display oneios-display.dex liboneios-display.so; do
    path="$incoming/native/$name"
    [ -f "$path" ] && [ ! -L "$path" ] || fail "native 3D artifact missing: $name"
    expected=$(awk -v n="$name" '$2 == n && length($1) == 64 {print $1}' "$incoming/native.sha256")
    case "$expected" in ''|*[!0-9a-f]*) fail "bad GPU artifact hash for $name" ;; esac
    [ "${#expected}" = 64 ] || fail "invalid GPU hash length for $name"
    [ "$(hash_of "$path")" = "$expected" ] ||
        fail "GPU artifact was modified while uploading: $name"
    [ "$(stat -c %s "$path")" -ge 256 ] || fail "empty GPU artifact: $name"
    [ ! -L "$incoming/runtime/bin/$name" ] || fail "symlinked runtime target: $name"
    install -m 700 "$path" "$incoming/runtime/bin/$name" ||
        fail "could not stage GPU artifact $name"
    [ "$(hash_of "$incoming/runtime/bin/$name")" = "$expected" ] ||
        fail "GPU runtime staging hash mismatch: $name"
    awk -v n="bin/$name" '$2 != n {print}' "$incoming/runtime.sha256" > "$incoming/runtime.sha256.new" ||
        fail "cannot update staged runtime hash list"
    mv "$incoming/runtime.sha256.new" "$incoming/runtime.sha256"
    printf '%s  bin/%s\n' "$expected" "$name" >> "$incoming/runtime.sha256"
done
chmod 700 "$incoming/runtime/bin/xnuhost" "$incoming/runtime/bin/oneios-display"
chmod 400 "$incoming/runtime/bin/liboneios-display.so" "$incoming/runtime/bin/oneios-display.dex"
printf 'version=sm8850-ios27-3d-8cpu-600s\nsession_abi=1\nxnuhost=bin/xnuhost\nimage_formats=1\nplaceholder=0\n' > "$incoming/runtime.conf"
printf 'format=1\nversion=27.0.1\nbuild=24A446\n' > "$incoming/image.conf"
[ "$(df -Pk "$stage" | awk 'NR==2 {print $4}')" -ge "$MIN_FREE" ] || fail "benchmark reserve crossed"
# Publish the completion marker last. An interrupted installation is
# incomplete and will never be admitted by the switch.
for name in data image runtime image.sha256 image.ids image.conf runtime.sha256 runtime.conf; do
    mv "$incoming/$name" "$stage/$name"
done
sync
printf 'sm8850-ios27-3d-8cpu-600s\n' > "$stage/image.ready"
echo "Verified GPU-3D xnuhost/display, 8-vCPU configuration and independent one-shot APFS Data snapshot staged at $stage"
echo "GUEST_TAKEOVER_LIVE_AUTHORIZED=NO (requires separate watchdog and unassisted-recovery qualification)"
