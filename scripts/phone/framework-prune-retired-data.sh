# Sourced by framework-stage.sh only for explicitly confirmed pruning.
# Caller holds the same start.lock as the Framework launcher and rearm.
# Never delete current Data, original seed, rollback, or session evidence.
retired_private_file() {
    [ -f "$1" ] && [ ! -L "$1" ] &&
        [ "$(stat -c '%u:%a:%h' "$1")" = 0:600:1 ]
}
retired_digest_table() {
    retired_private_file "$1" && awk '
        NF != 2 || length($1) != 64 || $1 !~ /^[0-9a-f]+$/ { bad=1 }
        $2 == "data.img" { data++ }
        $2 == "unique-chip-id" { chip++ }
        END { exit !(NR == 2 && data == 1 && chip == 1 && !bad) }
    ' "$1"
}
retired_free_kib() {
    df -Pk "$stage" | awk 'NR==2 {print $4}'
}
prune_retired_data_locked() {
    [ -d "$stage" ] && root_dir "$stage" &&
        [ "$(realpath "$stage")" = "$stage" ] || fail "untrusted retired Data stage"
    [ "$(getprop sys.boot_completed)" = 1 ] && [ "$(getenforce)" = Enforcing ] &&
        [ "$(getprop init.svc.zygote)" = running ] && pidof system_server >/dev/null ||
        fail "Android Framework unavailable for retired Data prune"
    prune_state=$(cat "$stage/control/state" 2>/dev/null || :)
    case "$prune_state" in
        starting|running|returning)
            [ -s "$stage/control/boot" ] &&
                [ "$(cat "$stage/control/boot")" != "$(cat /proc/sys/kernel/random/boot_id)" ] ||
                fail "experimental session active during retired Data prune" ;;
    esac
    if pidof xnuhost xnuhost-gui-bench xnuhost-tasks OneiOSDisplay oneios-display >/dev/null 2>&1; then
        fail "guest or display helper active during retired Data prune"
    fi
    retired_private_file "$stage/image.ready" &&
        [ "$(cat "$stage/image.ready")" = sm8850-ios27-3d-8cpu-600s ] ||
        fail "retired Data prune requires finalized image"
    for prune_pending in "$stage"/image.ready.*-pending; do
        [ ! -e "$prune_pending" ] && [ ! -L "$prune_pending" ] || fail "pending stage transaction"
    done
    # Refuse stage mounts in both init's and our own namespace.
    awk -v p="$stage" '$5 == p || index($5,p "/") == 1 {bad=1} END {exit bad}' \
        /proc/1/mountinfo /proc/self/mountinfo || fail "mounted stage during retired Data prune"
    prune_root="$stage/.retired-data"
    [ ! -L "$prune_root" ] || fail "untrusted retired Data directory"
    prune_before=$(retired_free_kib)
    case "$prune_before" in ''|*[!0-9]*) fail "unreadable free storage" ;; esac
    prune_files=0
    prune_bytes=0
    if [ -e "$prune_root" ]; then
        [ -d "$prune_root" ] && root_dir "$prune_root" &&
            [ "$(realpath "$prune_root")" = "$prune_root" ] || fail "untrusted retired Data directory"
        [ -d "$stage/data" ] && root_dir "$stage/data" || fail "untrusted current Data directory"
        # Validate every archive before deleting any payload. On interruption,
        # remaining payloads can be pruned later; receipts are always retained.
        for prune_pass in validate remove; do
            for prune_archive in "$prune_root"/consumed.*; do
                [ -e "$prune_archive" ] || [ -L "$prune_archive" ] || continue
                prune_suffix=${prune_archive##*/consumed.}
                case "$prune_suffix" in ''|*[!a-zA-Z0-9]*) fail "unrecognized retired Data archive name" ;; esac
                [ "${#prune_suffix}" = 8 ] && [ -d "$prune_archive" ] && root_dir "$prune_archive" &&
                    [ "$(realpath "$prune_archive")" = "$prune_archive" ] || fail "untrusted retired Data archive"
                retired_private_file "$prune_archive/data.consumed" && awk '
                    NR == 1 && NF == 2 && length($1) == 36 && $1 ~ /^[0-9a-f-]+$/ &&
                    length($2) == 32 && $2 ~ /^[0-9a-f]+$/ { ok=1 }
                    END {exit !(NR == 1 && ok)}
                ' "$prune_archive/data.consumed" &&
                    retired_digest_table "$prune_archive/consumed-data.sha256" &&
                    retired_digest_table "$prune_archive/rearm-source.sha256" ||
                    fail "missing or invalid retired Data receipt: $prune_archive"
                [ -d "$prune_archive/data" ] && root_dir "$prune_archive/data" &&
                    [ "$(realpath "$prune_archive/data")" = "$prune_archive/data" ] ||
                    fail "untrusted retired Data payload directory"
                for prune_name in data.img unique-chip-id; do
                    prune_path="$prune_archive/data/$prune_name"
                    [ -e "$prune_path" ] || [ -L "$prune_path" ] || continue
                    prune_size=8
                    [ "$prune_name" != data.img ] || prune_size=8589934592
                    retired_private_file "$prune_path" &&
                        [ "$(realpath "$prune_path")" = "$prune_path" ] &&
                        [ "$(stat -c %s "$prune_path")" = "$prune_size" ] ||
                        fail "untrusted retired Data payload: $prune_path"
                    prune_id=$(stat -c '%d:%i' "$prune_path") || fail "unreadable retired Data identity"
                    for prune_keep in "$stage/data/$prune_name" "$bench/data/$prune_name"; do
                        prune_keep_id=$(stat -c '%d:%i' "$prune_keep") || fail "missing current or seed Data"
                        [ "$prune_id" != "$prune_keep_id" ] || fail "retired Data aliases current or seed Data"
                    done
                    if [ "$prune_pass" = remove ]; then
                        prune_blocks=$(stat -c %b "$prune_path") || fail "unreadable allocated blocks"
                        case "$prune_blocks" in ''|*[!0-9]*) fail "invalid allocated blocks" ;; esac
                        rm -f "$prune_path" || fail "cannot remove retired payload: $prune_path"
                        [ ! -e "$prune_path" ] && [ ! -L "$prune_path" ] || fail "retired payload still present"
                        prune_files=$((prune_files + 1))
                        # Android mksh may use signed 32-bit shell arithmetic.
                        # Accumulate decimal bytes in awk (exact at phone-scale
                        # sizes), not in a shell arithmetic expansion.
                        prune_bytes=$(awk -v total="$prune_bytes" -v blocks="$prune_blocks" \
                            'BEGIN {printf "%.0f\n", total + blocks * 512}') ||
                            fail "cannot sum retired Data allocated bytes"
                        printf 'RETIRED_DATA_PAYLOAD_PRUNED=%s\n' "$prune_path"
                    fi
                done
            done
        done
    fi
    sync
    prune_after=$(retired_free_kib)
    case "$prune_after" in ''|*[!0-9]*) fail "unreadable free storage after prune" ;; esac
    echo "RETIRED_DATA_FILES_PRUNED=$prune_files"
    echo "RETIRED_DATA_ALLOCATED_BYTES_ESTIMATE=$prune_bytes"
    echo "FREE_KIB_BEFORE=$prune_before"
    echo "FREE_KIB_AFTER=$prune_after"
    echo "FREE_KIB_DELTA=$((prune_after - prune_before))"
    echo "RETIRED_DATA_RECEIPTS=PRESERVED"
    echo "RETIRED_DATA_PRUNE=PASS"
}
