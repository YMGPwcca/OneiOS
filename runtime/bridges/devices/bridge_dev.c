// SPDX-License-Identifier: MIT
// The "oneios,bridge" device: the host end of drivers/bridge/oneios_bridge_proto.h. Messages from the
// guest are dispatched to the haptic and Bluetooth bridges; messages for the guest wait in a backlog
// until it has posted a buffer.
#include "bridges/devices.h"
#include "bridges/quiesce.h"
#include "oneios_bridge_proto.h"
#include <stdlib.h>
#include <string.h>

#define BACKLOG 256u

typedef struct { struct ob_header header; uint8_t *payload; } pending;
typedef struct {
  xh_virtio *dev;
  br_bridge_config config;
  br_hci *hci;
  pending backlog[BACKLOG];
  unsigned head, count;
  uint64_t dropped;
  brq_gate quiesce;
  uint64_t bright_ticket;
  brq_report reports[BRQ_REPORTS];
} bridge_state;

// Writes one message into a guest buffer chain. Returns false when the chain cannot hold it.
static bool fill(xh_viov *iov, unsigned n, const struct ob_header *header, const uint8_t *payload, uint32_t *written)
{
  uint8_t message[OB_MAX_MESSAGE];
  size_t total = sizeof *header + header->length, done = 0;
  memcpy(message, header, sizeof *header);
  if (header->length) memcpy(message + sizeof *header, payload, header->length);
  for (unsigned i = 0; i < n && done < total; i++) {
    if (!iov[i].writable) continue;
    size_t part = total - done < iov[i].length ? total - done : iov[i].length;
    memcpy(iov[i].data, message + done, part);
    done += part;
  }
  *written = (uint32_t)done;
  return done == total;
}

// Called with the device's lock held.
static void drain(bridge_state *s)
{
  while (s->count) {
    xh_viov iov[4];
    uint16_t head;
    unsigned n = xh_virtio_pop(s->dev, OB_QUEUE_RX, &head, iov, 4);
    if (!n) return;
    pending *m = &s->backlog[s->head];
    uint32_t written = 0;
    if (!fill(iov, n, &m->header, m->payload, &written)) written = 0;      // too small a buffer: the message is lost
    xh_virtio_push(s->dev, OB_QUEUE_RX, head, written);
    free(m->payload);
    s->head = (s->head + 1) % BACKLOG;
    s->count--;
  }
}

// Latest-value telemetry is kept in host memory only while closed.
static const struct { uint16_t channel, type; size_t length; } report_types[BRQ_REPORTS] = {
  { OB_CH_BRIGHTNESS, OB_BRIGHT_ALS, sizeof(struct ob_bright_als) },
  { OB_CH_BATTERY, OB_BATTERY_STATE, sizeof(struct ob_battery_state) },
  { OB_CH_THERMAL, OB_THERMAL_STATE, sizeof(struct ob_thermal_state) },
};
_Static_assert(sizeof(struct ob_bright_als) <= BRQ_REPORT_BYTES &&
               sizeof(struct ob_battery_state) <= BRQ_REPORT_BYTES &&
               sizeof(struct ob_thermal_state) <= BRQ_REPORT_BYTES, "telemetry slot too small");
static void to_guest(bridge_state *s, uint16_t channel, uint16_t type, const void *payload, size_t length)
{
  xh_virtio_lock(s->dev);
  if (s->quiesce.closed) {
    for (unsigned i = 0; i < BRQ_REPORTS; i++) {
      if (channel != report_types[i].channel || type != report_types[i].type) continue;
      if (length != report_types[i].length || brq_store(s->reports, i, payload, length)) s->quiesce.fault = true;
      xh_virtio_unlock(s->dev);
      return;
    }
    s->quiesce.fault = true;
    // Preserve the existing explicitly requested return path, not an
    // automatic thermal action. It invalidates the park receipt first.
    if (channel != OB_CH_CONTROL || type != OB_CTL_SHUTDOWN || length) {
      xh_virtio_unlock(s->dev);
      return;
    }
  }
  if (length > OB_MAX_PAYLOAD) { s->dropped++; xh_virtio_unlock(s->dev); return; }
  if (s->count == BACKLOG) {                         // the oldest is lost
    free(s->backlog[s->head].payload);
    s->head = (s->head + 1) % BACKLOG;
    s->count--;
    s->dropped++;
  }
  pending *m = &s->backlog[(s->head + s->count) % BACKLOG];
  m->header = (struct ob_header){ channel, type, (uint32_t)length };
  m->payload = length ? malloc(length) : NULL;
  if (length && !m->payload) { s->dropped++; xh_virtio_unlock(s->dev); return; }
  if (length) memcpy(m->payload, payload, length);
  s->count++;
  drain(s);
  xh_virtio_unlock(s->dev);
}

static void hci_rx(void *ctx, uint8_t type, const uint8_t *packet, size_t length) { to_guest(ctx, OB_CH_HCI, type, packet, length); }

static void hci_state(void *ctx, int state)
{
  bridge_state *s = ctx;
  struct ob_hci_state message = { .state = (uint32_t)state };
  if (state == OB_HCI_STATE_READY)
    (void)br_bt_address(s->config.bt_address_path ? s->config.bt_address_path : "/mnt/vendor/efs/bluetooth/bt_addr", message.bd_addr);
  to_guest(s, OB_CH_HCI, OB_HCI_STATE, &message, sizeof message);
}

static void bright_state(bridge_state *s)
{
  br_bright_info info;
  br_bright_info_get(s->config.brightness, &info);
  // The lowest level's light: the floor's share of the range, of max_nits (the node is close to linear in light).
  uint64_t min_millinits = info.ceiling ? (uint64_t)info.max_nits * 1000u * info.floor / info.ceiling : 0;
  struct ob_bright_state state = { (info.panel ? OB_BRIGHT_HAS_PANEL : 0) | (info.als ? OB_BRIGHT_HAS_ALS : 0), info.max_nits, (uint32_t)min_millinits,
                                   br_bright_level(s->config.brightness) };
  to_guest(s, OB_CH_BRIGHTNESS, OB_BRIGHT_STATE, &state, sizeof state);
}

static void bright_als(void *ctx, const br_als_sample *sample)
{
  struct ob_bright_als als = { sample->millilux, sample->clear, sample->ir, sample->uv };
  to_guest(ctx, OB_CH_BRIGHTNESS, OB_BRIGHT_ALS, &als, sizeof als);
}

static void battery_send(void *ctx, const br_battery_sample *b)
{
  struct ob_battery_state state = { (b->present ? OB_BATTERY_PRESENT : 0) | (b->plugged ? OB_BATTERY_PLUGGED : 0) |
                                        (b->charging ? OB_BATTERY_CHARGING : 0) | (b->full ? OB_BATTERY_FULL : 0),
                                    b->percent, b->temp_deci_c, b->voltage_mv, b->current_ma, b->full_mah, b->design_mah, b->cycles, b->minutes };
  to_guest(ctx, OB_CH_BATTERY, OB_BATTERY_STATE, &state, sizeof state);
}

static void thermal_send(void *ctx, const br_thermal_state *t)
{
  const br_thermal_raw *r = &t->raw;
  struct ob_thermal_state state = { t->level, t->reason, t->cap, r->skin, r->soc, r->cpu, r->gpu, r->ddr, r->xo, r->ap, r->battery };
  to_guest(ctx, OB_CH_THERMAL, OB_THERMAL_STATE, &state, sizeof state);
}

static void from_guest(bridge_state *s, const struct ob_header *h, const uint8_t *payload)
{
  switch (h->channel) {
  case OB_CH_CONTROL:
    if (h->type == OB_CTL_HELLO) {
      struct ob_ctl_hello hello = { OB_PROTO_VERSION, 1u << OB_CH_CONTROL | (s->config.haptic ? 1u << OB_CH_HAPTIC : 0) |
                                                       (s->config.hci_factory ? 1u << OB_CH_HCI : 0) |
                                                       (s->config.brightness ? 1u << OB_CH_BRIGHTNESS : 0) |
                                                       (s->config.battery ? 1u << OB_CH_BATTERY : 0) |
                                                       (s->config.thermal ? 1u << OB_CH_THERMAL : 0) };
      if (br_haptic_impacts_available(s->config.haptic)) {
        struct ob_ctl_hello_ext ext = { hello.version, hello.channels, OB_FEAT_HAPTIC_IMPACT };
        to_guest(s, OB_CH_CONTROL, OB_CTL_HELLO, &ext, sizeof ext);
      } else {
        to_guest(s, OB_CH_CONTROL, OB_CTL_HELLO, &hello, sizeof hello);
      }
    }
    break;
  case OB_CH_HAPTIC:
    if (h->type == OB_HAPTIC_VIB && h->length >= sizeof(struct ob_haptic_vib)) {
      struct ob_haptic_vib vib;
      memcpy(&vib, payload, sizeof vib);
      br_haptic_vib(s->config.haptic, vib.on_ms, vib.intensity, vib.frequency_hz);
    } else if (h->type == OB_HAPTIC_STOP) br_haptic_stop(s->config.haptic);
    else if (h->type == OB_HAPTIC_IMPACT &&
             h->length == sizeof(struct ob_haptic_impact) &&
             br_haptic_impacts_available(s->config.haptic)) {
      struct ob_haptic_impact impact;
      memcpy(&impact, payload, sizeof impact);
      if (impact.kind >= OB_IMPACT_LIGHT && impact.kind <= OB_IMPACT_HEAVY)
        (void)br_haptic_impact(s->config.haptic, impact.kind);
      // Malformed/unsupported impacts are never silently mapped to VIB.
    }
    break;
  case OB_CH_HCI:
    if (!s->config.hci_factory) break;
    if (h->type == OB_HCI_OPEN) {
      if (!s->hci) s->hci = s->config.hci_factory(hci_rx, hci_state, s);
      // Failed after it was opened (the HAL died, or never finished initialising): a new client starts over.
      else if (br_hci_state(s->hci) == OB_HCI_STATE_FAILED) br_hci_close(s->hci);
      if (!s->hci || br_hci_open(s->hci)) hci_state(s, OB_HCI_STATE_FAILED);
      else if (br_hci_state(s->hci) == OB_HCI_STATE_READY) hci_state(s, OB_HCI_STATE_READY);   // already open: say so again
    } else if (h->type == OB_HCI_CLOSE) { if (s->hci) br_hci_close(s->hci); }
    else if (s->hci && h->type >= OB_HCI_COMMAND && h->type <= OB_HCI_ISO) (void)br_hci_send(s->hci, (uint8_t)h->type, payload, h->length);
    break;
  case OB_CH_BRIGHTNESS:
    if (!s->config.brightness) break;
    if (h->type == OB_BRIGHT_SET && h->length >= sizeof(struct ob_bright_set)) {
      struct ob_bright_set set;
      memcpy(&set, payload, sizeof set);
      br_bright_set(s->config.brightness, set.level, set.flags & OB_BRIGHT_LINEAR, set.fade_ms);
    } else if (h->type == OB_BRIGHT_POWER && h->length >= sizeof(struct ob_bright_power)) {
      struct ob_bright_power power;
      memcpy(&power, payload, sizeof power);
      br_bright_display(s->config.brightness, power.on != 0, power.source == OB_POWER_FRAMEBUFFER ? "the framebuffer's power request" : "the guest");
    } else if (h->type == OB_BRIGHT_QUERY) {
      bright_state(s);
      br_bright_listen(s->config.brightness, bright_als, s);      // light readings from now on
    }
    break;
  case OB_CH_BATTERY:
    if (s->config.battery && h->type == OB_BATTERY_QUERY) {
      br_battery_sample sample;
      (void)br_battery_query(s->config.battery, &sample);         // on a failed read: the last good sample
      battery_send(s, &sample);
      br_battery_listen(s->config.battery, battery_send, s);      // changes from now on
    }
    break;
  case OB_CH_THERMAL:
    if (s->config.thermal && h->type == OB_THERMAL_QUERY) {
      br_thermal_state state;
      br_thermal_get(s->config.thermal, &state);                  // the worker reads every 5 s from xnuhost's start
      br_thermal_on_report(s->config.thermal, thermal_send, s);   // changes from now on
      thermal_send(s, &state);
    }
    break;
  }
}

static int64_t bridge_handle(xh_virtio *dev, unsigned queue, uint16_t head, xh_viov *iov, unsigned n)
{
  bridge_state *s = xh_virtio_opaque(dev);
  if (brq_late(&s->quiesce)) return -1; // guest violated the upstream vCPU fence
  uint8_t message[OB_MAX_MESSAGE];
  size_t size = 0;
  (void)head;
  if (queue != OB_QUEUE_TX) return 0;
  for (unsigned i = 0; i < n; i++) {
    if (iov[i].writable) continue;
    if (iov[i].length > sizeof message - size) return 0;        // longer than any message: ignored
    memcpy(message + size, iov[i].data, iov[i].length);
    size += iov[i].length;
  }
  struct ob_header header;
  if (size < sizeof header) return 0;
  memcpy(&header, message, sizeof header);
  if (header.length > size - sizeof header) return 0;
  from_guest(s, &header, message + sizeof header);
  return 0;
}

static void bridge_kick(xh_virtio *dev, unsigned queue)
{
  (void)queue;
  bridge_state *s = xh_virtio_opaque(dev);
  if (!brq_late(&s->quiesce)) drain(s);
}

static void bridge_reset(xh_virtio *dev)
{
  bridge_state *s = xh_virtio_opaque(dev);
  (void)brq_late(&s->quiesce);
  while (s->count) { free(s->backlog[s->head].payload); s->head = (s->head + 1) % BACKLOG; s->count--; }
  br_haptic_stop(s->config.haptic);                  // a guest that resets (or panics into a reset) leaves no motor running
  if (s->hci) br_hci_close(s->hci);
  if (s->config.battery) br_battery_listen(s->config.battery, NULL, NULL);  // no reads and no backlog for a guest that is gone
  if (s->config.thermal) br_thermal_on_report(s->config.thermal, NULL, NULL);   // the reads go on: xnuhost's own step needs them
}

static uint32_t bridge_config_read(xh_virtio *dev, uint32_t offset, unsigned size)
{
  (void)dev; (void)size;
  return offset == 0 ? OB_PROTO_VERSION : 0;
}

static const xh_virtio_ops bridge_ops = { .device_id = OB_VIRTIO_DEVICE_ID, .nqueues = 2, .handle = bridge_handle, .config_read = bridge_config_read,
                                          .reset = bridge_reset, .manual = 1u << OB_QUEUE_RX, .kick = bridge_kick };

// The one bridge of a session, for br_bridge_request_shutdown (the host has at most one).
static bridge_state *g_active_bridge;

xh_virtio *br_bridge_create(uint64_t base, unsigned spi, const br_bridge_config *config)
{
  bridge_state *s = calloc(1, sizeof *s);
  if (!s) return NULL;
  s->config = *config;
  s->dev = xh_virtio_create(base, spi, &bridge_ops, s, "oneios-bridge");
  if (!s->dev) { free(s); return NULL; }
  g_active_bridge = s;
  return s->dev;
}

// The sealed board and session owner must pin the single real bridge
// and its backends. HCI and haptic actuators do not have drain receipts.
static int bridge_gate_lock(xh_virtio *dev, bridge_state **out)
{
  bridge_state *s = g_active_bridge;
  if (!dev || !s || s->dev != dev) return -ESTALE;
  if (!xh_virtio_trylock(dev)) return -EAGAIN;
  *out = s;
  return 0;
}
int br_bridge_quiesce_close(xh_virtio *dev, uint64_t *ticket)
{
  if (!ticket) return -EINVAL;
  bridge_state *s;
  int r = bridge_gate_lock(dev, &s);
  if (r) return r;
  if (s->config.haptic || s->config.hci_factory || s->hci) r = -ENOTSUP;
  else if (s->quiesce.fault) r = -ESTALE;
  else if (s->quiesce.closed) r = -EBUSY;
  else if (s->quiesce.generation == UINT64_MAX) r = -EOVERFLOW;
  // Preserve all pre-park backlog, reserving one slot per telemetry type.
  else if (s->count > BACKLOG - BRQ_REPORTS) r = -EAGAIN;
  else {
    uint64_t bright = 0;
    if (s->config.brightness) r = br_bright_quiesce_close(s->config.brightness, &bright);
    if (!r) {
      s->bright_ticket = bright;
      memset(s->reports, 0, sizeof s->reports);
      r = brq_close(&s->quiesce, false, ticket);
    }
  }
  xh_virtio_unlock(dev);
  return r;
}
int br_bridge_quiesce_poll(xh_virtio *dev, uint64_t ticket, unsigned *deferred_mask)
{
  bridge_state *s;
  int r = bridge_gate_lock(dev, &s);
  if (r) return r;
  r = brq_check(&s->quiesce, ticket, false);
  if (!r && s->config.brightness) r = br_bright_quiesce_poll(s->config.brightness, s->bright_ticket);
  if (!r) {
    r = brq_poll(&s->quiesce, ticket, false);
    if (deferred_mask) *deferred_mask = brq_report_mask(s->reports);
  }
  xh_virtio_unlock(dev);
  return r;
}
int br_bridge_quiesce_resume(xh_virtio *dev, uint64_t ticket)
{
  bridge_state *s;
  int r = bridge_gate_lock(dev, &s);
  if (r) return r;
  r = brq_can_resume(&s->quiesce, ticket, false);
  uint8_t *copies[BRQ_REPORTS] = {0};
  // Allocate everything before reopening either gate. No eviction of
  // the existing backlog to make space for reports on this path.
  if (!r && s->count > BACKLOG - BRQ_REPORTS) r = -EPROTO;
  for (unsigned i = 0; !r && i < BRQ_REPORTS; i++) {
    size_t n = s->reports[i].length;
    if (!n) continue;
    if (n != report_types[i].length) { r = -EPROTO; break; }
    copies[i] = malloc(n);
    if (!copies[i]) r = -ENOMEM;
    else memcpy(copies[i], s->reports[i].bytes, n);
  }
  if (!r && s->config.brightness) r = br_bright_quiesce_resume(s->config.brightness, s->bright_ticket);
  if (!r) {
    // Gate was checked under this same lock; no competing close/resume.
    r = brq_resume(&s->quiesce, ticket, false);
    if (!r) {
      for (unsigned i = 0; i < BRQ_REPORTS; i++) {
        if (!copies[i]) continue;
        pending *p = &s->backlog[(s->head + s->count++) % BACKLOG];
        p->header = (struct ob_header){ report_types[i].channel, report_types[i].type, (uint32_t)s->reports[i].length };
        p->payload = copies[i]; copies[i] = NULL;
      }
      memset(s->reports, 0, sizeof s->reports);
      s->bright_ticket = 0;
      drain(s);
    }
  }
  if (r == -ENOMEM || r == -EPROTO) s->quiesce.fault = true;
  for (unsigned i = 0; i < BRQ_REPORTS; i++) free(copies[i]);
  xh_virtio_unlock(dev);
  return r;
}

// The return's graceful-shutdown ask (OB_CTL_SHUTDOWN on the control channel). Queued like any host->guest message
// (it waits in the backlog until the guest's driver reads it); false when there is no bridge to ask through. The
// caller does not depend on the guest acting: it kills at return-graceful-ms regardless.
bool br_bridge_request_shutdown(void)
{
  if (!g_active_bridge) return false;
  to_guest(g_active_bridge, OB_CH_CONTROL, OB_CTL_SHUTDOWN, NULL, 0);
  return true;
}
