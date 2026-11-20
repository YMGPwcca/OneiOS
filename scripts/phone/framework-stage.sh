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

install_stage() {
    if [ ! -d "$stage" ]; then
        mkdir -m 700 "$stage" || fail "cannot create the experimental stage"
    fi
    root_dir "$stage" || fail "untrusted experimental stage"
    [ ! -L "$stage/start.lock" ] || fail "untrusted start lock"
    # mksh keeps FD 8 inside the shell, but does not pass it to external
    # commands. Duplicate that same open file description to fd 0 for flock;
    # the parent shell retains fd 8 and hence retains the lock.
    exec 8>>"$stage/start.lock"
flock -n 0 0<&8 || fail "a switch or stage operation is starting"
    case "$(cat "$stage/control/state" 2>/dev/null || :)" in
        starting|running|returning) fail "experimental session still open" ;;
    esac
    for name in oneios_switch.sh oneios_return.sh oneios-watchdog; do
        if [ -e "$stage/$name" ]; then
            [ ! -L "$stage/$name" ] && cmp -s "$incoming/$name" "$stage/$name" ||
                fail "existing $name differs. Keep the old stage for rollback and evidence."
        else
            install -m 700 "$incoming/$name" "$stage/$name"
        fi
    done
}

case "$operation" in
    install) install_stage; exit ;;
    probe|prepare) ;;
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

# The host validates the allowlist and supplies expected hashes from the
# validated bench. Runtime and image trees are assembled from listed files.
[ -s "$incoming/bench.sha256" ] || fail "empty benchmark manifest"
mkdir "$incoming/image" "$incoming/runtime" "$incoming/data"
while read -r sha path; do
    case "$path" in image/*|runtime/*|bench/xnuhost-gui-bench) ;; *) fail "unexpected artifact path" ;; esac
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
    case "$path" in
        bench/xnuhost-gui-bench) dest=runtime/bin/xnuhost-gui-bench ;;
        *) dest=$path ;;
    esac
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
chmod 700 "$incoming/runtime/bin/"*
printf 'version=sm8850-ios27-bench\nsession_abi=1\nxnuhost=bin/xnuhost-gui-bench\nimage_formats=1\nplaceholder=0\n' > "$incoming/runtime.conf"
printf 'format=1\nversion=27.0.1\nbuild=24A446\n' > "$incoming/image.conf"
[ "$(df -Pk "$stage" | awk 'NR==2 {print $4}')" -ge "$MIN_FREE" ] || fail "benchmark reserve crossed"
# Publish the completion marker last. An interrupted installation is
# incomplete and will never be admitted by the switch.
for name in data image runtime image.sha256 image.ids image.conf runtime.sha256 runtime.conf; do
    mv "$incoming/$name" "$stage/$name"
done
sync
printf 'sm8850-ios27-bench\n' > "$stage/image.ready"
echo "Validated experimental image and independent APFS Data snapshot ready at $stage"
