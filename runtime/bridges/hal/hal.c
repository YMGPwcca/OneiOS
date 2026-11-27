// SPDX-License-Identifier: MIT
// The treble backend's HAL client and the HALs' parcels (hal.h).
#define _GNU_SOURCE
#include "hal.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct br_hal {
  ab      *b;
  uint32_t handle;
  int32_t  version;
};

void ab_put_float(ab_parcel *p, float value) { int32_t bits; memcpy(&bits, &value, 4); ab_put_i32(p, bits); }
float ab_get_float(ab_reader *r) { int32_t bits = ab_get_i32(r); float v; memcpy(&v, &bits, 4); return v; }
void ab_put_i64(ab_parcel *p, int64_t value) { ab_put_i32(p, (int32_t)(uint32_t)value); ab_put_i32(p, (int32_t)(uint32_t)((uint64_t)value >> 32)); }
int64_t ab_get_i64(ab_reader *r)
{
  uint32_t low = (uint32_t)ab_get_i32(r), high = (uint32_t)ab_get_i32(r);
  return (int64_t)((uint64_t)high << 32 | low);
}

void br_hal_parcel(ab_parcel *p, const char *descriptor) { ab_init(p); ab_put_token(p, descriptor); }

const char *br_hal_error(int rc)
{
  static _Thread_local char text[64];
  if (rc == -ENOENT) return "not registered with servicemanager, or SELinux denies the lookup";
  if (rc == -ETIMEDOUT) return "no answer in 5 s";
  if (rc == -EPIPE) return "the HAL's process died";
  if (rc == -EREMOTEIO) return "the HAL answered with an exception";
  if (rc == -EPROTO) return "a reply this client cannot read";
  snprintf(text, sizeof text, "%s", strerror(rc < 0 ? -rc : rc));
  return text;
}

struct taken { ab *b; uint32_t handle; bool have; };
static int take_handle(void *ctx, ab_reader *r)
{
  struct taken *t = ctx;
  if (!ab_get_binder(r, &t->handle, NULL)) return r->bad ? -EPROTO : -ENOENT;   // a null binder: not registered
  int rc = ab_acquire(t->b, t->handle);          // ours, before the reply's buffer goes back
  if (!rc) t->have = true;
  return rc;
}
struct named { const char *want; bool same; };
static int take_descriptor(void *ctx, ab_reader *r)
{
  struct named *n = ctx;
  char text[96];
  if (!ab_get_string(r, text, sizeof text)) return -EPROTO;
  n->same = !strcmp(text, n->want);
  return 0;
}
static int take_i32(void *ctx, ab_reader *r) { *(int32_t *)ctx = ab_get_i32(r); return r->bad ? -EPROTO : 0; }

br_hal *br_hal_open(const char *device, const char *instance, const char *descriptor, char *why, size_t size)
{
  br_hal *h = calloc(1, sizeof *h);
  if (!h) { snprintf(why, size, "no memory"); return NULL; }
  h->b = ab_open(device, NULL, NULL, NULL);
  if (!h->b) {
    snprintf(why, size, "%s: no binder device (%s: %s)", instance, device ? device : getenv("ONEIOS_BINDER") ? getenv("ONEIOS_BINDER") : "/dev/binder", strerror(errno));
    free(h);
    return NULL;
  }
  ab_parcel p;
  br_hal_parcel(&p, HAL_SERVICE_MANAGER);
  ab_put_string(&p, instance);
  struct taken t = { .b = h->b };
  int32_t specific = 0;
  int rc = ab_call(h->b, 0, HAL_SM_GET_SERVICE, &p, &specific, take_handle, &t);
  if (rc || !t.have) {
    snprintf(why, size, "%s (no service: %s)", instance, br_hal_error(rc ? rc : -ENOENT));
    ab_close(h->b);
    free(h);
    return NULL;
  }
  h->handle = t.handle;
  struct named n = { .want = descriptor };
  ab_init(&p);
  rc = ab_call(h->b, h->handle, AB_INTERFACE, &p, &specific, take_descriptor, &n);
  if (rc || !n.same) {
    snprintf(why, size, "%s (%s)", instance, rc ? br_hal_error(rc) : "it is not a service of that interface");
    br_hal_close(h);
    return NULL;
  }
  ab_init(&p);
  ab_put_token(&p, descriptor);
  if (ab_call(h->b, h->handle, AB_GET_VERSION, &p, &specific, take_i32, &h->version)) h->version = 0;
  return h;
}

int32_t br_hal_version(const br_hal *h) { return h->version; }

int br_hal_call(br_hal *h, uint32_t code, const ab_parcel *p, ab_reply_fn on_reply, void *ctx)
{
  int32_t specific = 0;
  return ab_call(h->b, h->handle, code, p, &specific, on_reply, ctx);
}

void br_hal_close(br_hal *h)
{
  if (!h) return;
  if (h->handle) ab_release(h->b, h->handle);
  ab_close(h->b);
  free(h);
}

// ---- health ---------------------------------------------------------------------------------------
// A parcelable array's elements: each a non-null marker and a sized body; skipped whole.
static bool skip_parcelables(ab_reader *r)
{
  int32_t n = ab_get_i32(r);
  if (r->bad || n < -1 || n > 4096) { r->bad = true; return false; }
  for (int32_t i = 0; i < n; i++) {
    size_t end = ab_get_parcelable(r);
    if (!end) return false;
    r->position = end;
  }
  return true;
}

int hal_health_decode(ab_reader *r, hal_health_info *o)
{
  memset(o, 0, sizeof *o);
  size_t end = ab_get_parcelable(r);
  if (!end) return -EPROTO;
#define MORE() (r->position + 4 <= end && !r->bad)
  o->ac = ab_get_i32(r); o->usb = ab_get_i32(r); o->wireless = ab_get_i32(r);
  o->dock = ab_get_i32(r);
  o->max_charging_ua = ab_get_i32(r); o->max_charging_uv = ab_get_i32(r);
  o->status = ab_get_i32(r); o->health = ab_get_i32(r);
  o->present = ab_get_i32(r);
  o->level = ab_get_i32(r);
  o->voltage_mv = ab_get_i32(r); o->temp_deci_c = ab_get_i32(r); o->current_ua = ab_get_i32(r);
  o->cycles = ab_get_i32(r); o->full_uah = ab_get_i32(r); o->counter_uah = ab_get_i32(r);
  if (!ab_get_string(r, o->technology, sizeof o->technology)) return -EPROTO;
  if (MORE()) o->current_average_ua = ab_get_i32(r);
  if (MORE() && !skip_parcelables(r)) return -EPROTO;           // diskStats
  if (MORE() && !skip_parcelables(r)) return -EPROTO;           // storageInfos
  if (MORE()) o->capacity_level = ab_get_i32(r);
  if (r->position + 8 <= end) o->time_to_full_s = ab_get_i64(r);
  if (MORE()) o->design_uah = ab_get_i32(r);
#undef MORE
  if (r->bad || r->position > end) return -EPROTO;
  r->position = end;                                              // what a newer HAL added (chargingState, ...)
  return 0;
}

void hal_health_encode(ab_parcel *p, const hal_health_info *in)
{
  ab_put_i32(p, 1);
  size_t at = p->size;
  ab_put_i32(p, 0);
  ab_put_i32(p, in->ac); ab_put_i32(p, in->usb); ab_put_i32(p, in->wireless); ab_put_i32(p, in->dock);
  ab_put_i32(p, in->max_charging_ua); ab_put_i32(p, in->max_charging_uv);
  ab_put_i32(p, in->status); ab_put_i32(p, in->health); ab_put_i32(p, in->present); ab_put_i32(p, in->level);
  ab_put_i32(p, in->voltage_mv); ab_put_i32(p, in->temp_deci_c); ab_put_i32(p, in->current_ua);
  ab_put_i32(p, in->cycles); ab_put_i32(p, in->full_uah); ab_put_i32(p, in->counter_uah);
  ab_put_string(p, in->technology);
  ab_put_i32(p, in->current_average_ua);
  ab_put_i32(p, 0); ab_put_i32(p, 0);                             // no diskStats, no storageInfos
  ab_put_i32(p, in->capacity_level);
  ab_put_i64(p, in->time_to_full_s);
  ab_put_i32(p, in->design_uah);
  ab_put_i32(p, 1); ab_put_i32(p, 1);                             // chargingState NORMAL, chargingPolicy DEFAULT (v2)
  int32_t size = (int32_t)(p->size - at);
  if (!p->overflow) memcpy(p->data + at, &size, 4);
}

// ---- thermal --------------------------------------------------------------------------------------
static int temperatures_decode(ab_reader *r, hal_temperature *out, unsigned max, bool complete)
{
  int32_t n = ab_get_i32(r);
  if (r->bad || n < -1 || n > 4096 ||
      (complete && (n <= 0 || (unsigned)n > max))) return -EPROTO;
  unsigned kept = 0;
  for (int32_t i = 0; i < n; i++) {
    size_t end = ab_get_parcelable(r);
    if (!end) return -EPROTO;
    hal_temperature t = { 0 };
    t.type = ab_get_i32(r);
    if (complete) {
      ab_reader name = *r;
      int32_t units = ab_get_i32(&name);
      if (name.bad || units <= 0 || (unsigned)units >= sizeof t.name) return -EPROTO;
    }
    if (!ab_get_string(r, t.name, sizeof t.name)) return -EPROTO;
    t.celsius = ab_get_float(r);
    if (r->position + 4 <= end) t.throttling = ab_get_i32(r);
    else if (complete) return -EPROTO;
    if (r->bad || r->position > end ||
        (complete && (t.throttling < 0 || t.throttling > 6))) return -EPROTO;
    r->position = end;
    if (kept < max) out[kept++] = t;
  }
  if (complete && r->position != r->size) return -EPROTO;
  return (int)kept;
}
int hal_temperatures_decode(ab_reader *r, hal_temperature *out, unsigned max)
{
  return temperatures_decode(r, out, max, false);
}
int hal_thermal_snapshot_decode(ab_reader *r, hal_thermal_snapshot *out)
{
  out->count = 0;
  int n = temperatures_decode(r, out->temps, HAL_TEMPS_MAX, true);
  if (n < 0) return n;
  out->count = (unsigned)n;
  return 0;
}
bool hal_thermal_value_valid(const hal_temperature *t)
{
  return t->name[0] && memchr(t->name, 0, sizeof t->name) &&
      t->celsius >= -40.0f && t->celsius <= 200.0f &&
      (strcmp(t->name, "SUBBAT") || t->celsius != 0.0f) &&
      t->throttling >= 0 && t->throttling <= 6;
}
int hal_thermal_snapshot_severity(const hal_thermal_snapshot *s)
{
  static const struct { const char *name; int32_t type; } qualified[] = {
    {"AP", HAL_TEMP_CPU}, {"BAT", HAL_TEMP_BATTERY}, {"SKIN", HAL_TEMP_SKIN},
    {"PA", 5}, {"USB", 4}
  };
  if (!s || s->version != 3 || !s->count || s->count > HAL_TEMPS_MAX) return -1;
  unsigned seen = 0;
  int severity = 0;
  for (unsigned i = 0; i < s->count; i++) {
    const hal_temperature *t = &s->temps[i];
    if (!memchr(t->name, 0, sizeof t->name)) return -1;
    bool matched = false;
    for (unsigned k = 0; k < sizeof qualified / sizeof qualified[0]; k++) {
      if (strcmp(t->name, qualified[k].name)) continue;
      if ((seen & (1u << k)) || t->type != qualified[k].type ||
          !hal_thermal_value_valid(t) || t->celsius <= 0.0f) return -1;
      seen |= 1u << k;
      matched = true;
      if (severity < t->throttling) severity = t->throttling;
      break;
    }
    // An unqualified sensor is not a source of an actionable severity.
    // A nonzero status on it must not authorize recovery at severity 0.
    if (!matched && t->throttling != 0) return -1;
  }
  return (seen & 7u) == 7u ? severity : -1;
}
static int take_thermal_snapshot(void *ctx, ab_reader *r)
{
  return hal_thermal_snapshot_decode(r, ctx);
}
int br_hal_thermal_snapshot_read(const char *device, hal_thermal_snapshot *s,
                                 char *why, size_t size)
{
  memset(s, 0, sizeof *s);
  br_hal *h = br_hal_open(device, HAL_THERMAL_INSTANCE, HAL_THERMAL, why, size);
  if (!h) return -ENODEV;
  s->version = br_hal_version(h);
  int rc;
  if (s->version != 3) {
    rc = -EPROTONOSUPPORT;
    snprintf(why, size, "native thermal: expected AIDL v3, got %d", s->version);
  } else {
    ab_parcel p;
    br_hal_parcel(&p, HAL_THERMAL);
    rc = br_hal_call(h, HAL_THERMAL_GET_TEMPERATURES, &p, take_thermal_snapshot, s);
    if (rc) snprintf(why, size, "native thermal: getTemperatures: %s", br_hal_error(rc));
  }
  br_hal_close(h);
  if (rc) s->count = 0;
  return rc;
}

void hal_temperatures_encode(ab_parcel *p, const hal_temperature *in, unsigned n)
{
  ab_put_i32(p, (int32_t)n);
  for (unsigned i = 0; i < n; i++) {
    ab_put_i32(p, 1);
    size_t at = p->size;
    ab_put_i32(p, 0);
    ab_put_i32(p, in[i].type);
    ab_put_string(p, in[i].name);
    ab_put_float(p, in[i].celsius);
    ab_put_i32(p, in[i].throttling);
    int32_t size = (int32_t)(p->size - at);
    if (!p->overflow) memcpy(p->data + at, &size, 4);
  }
}
