# SM8850 native haptics — preserved 2026-11-16 evidence

**Galaxy S26 Ultra · SM-S948B / m3q / SM8850 · historical evidence, not full guest acceptance**

[← Hardware guide](hardware.md) · [Documentation hub](README.md) · [Physical status](SM8850_LIVE_STATUS_2026-11-20.md) · [Original technical record](https://github.com/YMGPwcca/OneiOS/blob/19820844368766aa6e8f8c90cf8021241c802123/docs/hardware.md#L2803-L2849)

> [!IMPORTANT]
> This reconstructs the SM8850-specific haptic observations from the technical hardware guide **before its editorial shortening**. Dates, test levels and open questions are preserved. It does **not** certify end-to-end iOS-to-HAL haptic output during the later 600-second `bench/bridges=0` Framework takeover.

## Evidence matrix

| Observation or test | Status in the 2026-11-16 record | Scope |
| :--- | :--- | :--- |
| Standalone Samsung HAL native click | **Physically felt**, one `HEAVY_CLICK` with `STRONG` strength; HAL reported ~110 ms | **Standalone phone HAL**, not hosted iOS |
| Native capability preflight | **PASS** in the staged/native check | Proves the requested host HAL capability under the test conditions |
| PCM-to-native impact classifier | **Host regression coverage** | Linux fake vibrator, not a real iOS guest-to-HAL path |
| Native impact counters | **Implemented and host-tested** | Host counts impacts among guest haptic requests; guest logs successful impact sends |
| iOS guest-to-host native impact delivery | **NOT PHYSICALLY VERIFIED** | Requires a separate safety-qualified guest session |
| 600-second Framework session | Guest booted/first frame observed later | The actual `bench/bridges=0` profile does **not** qualify haptic bridge functionality |

## PCM-to-native impact regression

The source record states that `runtime/bridges/tests/test_bridges.c` exercised the same `oa_period` Actuator waveform classifier used by the guest, passing requests through the host VirtIO model to a **fake vibrator backend**. Its coverage was:

- Isolated heavy, medium and light taps.
- Native-impact opt-in **disabled**.
- Sustained vibration followed by `VIB/STOP`.
- Malformed impact payloads and reset cancellation.
- Refusal by `oneios_haptic_impact` unless guest boot accepted `oneios_native_impacts=1`.

`scripts/ci-local.sh` was updated to include driver and userland suites, including the standalone native PCM classifier in `drivers/haptics/test_actuator.c`. These are **host tests**, not evidence of tactile iOS guest output.

## Session opt-in contract (historical)

An earlier OneOS switch did not forward the host environment setting `ONEIOS_HAPTIC_NATIVE_IMPACTS` automatically. The 2026-11-16 change introduced `haptics-native-impacts=1` in a staged image's `xnuhost.conf`, which requests the host native-preset capability check and adds `oneios_native_impacts=1` to guest boot arguments.

The opt-in was designed to **fail closed** on non-Treble haptics or `hw-backend-fallback=1`, and to default off. Host configuration regressions covered this path. **Do not assume that this historical ordinary-switch opt-in is available or safe in the current SM8850 root-only Framework profile**: that profile explicitly disables normal bridges.

## What remains open

- [ ] Revalidate current code/config against the historical `haptics-native-impacts` and `oneios_native_impacts` contract offline.
- [ ] Demonstrate native guest impact → host VirtIO → vendor HAL tactile effect in a separate, short, authorized session **after** P0 thermal and recovery gates are met.
- [ ] Correlate one guest impact with one host dispatch and one physical click; prove no repeats, no unwanted fallback and deterministic shutdown.

**Provenance:** [original 2026-11-16 source paragraphs](https://github.com/YMGPwcca/OneiOS/blob/19820844368766aa6e8f8c90cf8021241c802123/docs/hardware.md#L2803-L2849). The historical source remains readable; no older device's hardware numbers have been imported into this page.
