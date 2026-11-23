// SPDX-License-Identifier: MIT
// The Android encoder backend (encoder.h): the NDK's AMediaCodec. "video/hevc" reaches Codec2's c2.qti.hevc.encoder
// on the S24 Ultra, "video/avc" the AVC encoder; both the samsung and treble hardware backends use this same path, so
// one file serves both. ByteBuffer input (tightly packed NV12, COLOR_FormatYUV420SemiPlanar); the output is an
// Annex-B byte stream (start codes), which is what DroidVMVTHost.cpp and CMPhoto expect. Built only for Android (the
// Makefile's $(A) target); the PC host test uses backend_stub.c.
//
// [I] NV12 as COLOR_FormatYUV420SemiPlanar (21) with ByteBuffer input: c2.qti.hevc.encoder accepts it; not yet run on
// the phone. The still-image settings (one keyframe, no reordering, constant-quality) are below. encctl encodes a
// test pattern through this on the phone.
#include "encoder.h"
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <media/NdkMediaCodec.h>
#include <media/NdkMediaFormat.h>

// AMediaCodecBufferInfo flags and color format (not all NDK headers export the names).
#ifndef AMEDIACODEC_BUFFER_FLAG_CODEC_CONFIG
#define AMEDIACODEC_BUFFER_FLAG_CODEC_CONFIG 2
#endif
#ifndef AMEDIACODEC_BUFFER_FLAG_KEY_FRAME
#define AMEDIACODEC_BUFFER_FLAG_KEY_FRAME 1
#endif
#define NDK_COLOR_FORMAT_NV12 21                 // COLOR_FormatYUV420SemiPlanar
#define NDK_BITRATE_MODE_CQ 0                    // BITRATE_MODE_CQ

struct br_enc_session {
  AMediaCodec *codec;
  bool started, eos_queued, trace;
  unsigned polls, not_ready, formats, buffers_changed, outputs;
};

static br_enc_session *ndk_open(uint32_t codec, uint32_t width, uint32_t height) {
  const char *mime = codec == MEDIA_PIXFMT_HEVC ? "video/hevc" : "video/avc";
  br_enc_session *s = calloc(1, sizeof *s);
  if (!s) return NULL;
  const char *trace = getenv("ONEIOS_ENCODER_TRACE");
  s->trace = trace && !strcmp(trace, "1");
  s->codec = AMediaCodec_createEncoderByType(mime);
  if (!s->codec) { br_log(0, "encoder: MediaCodec create encoder %s failed", mime); free(s); return NULL; }
  if (s->trace) {
    char *name = NULL;
    media_status_t nr = AMediaCodec_getName(s->codec, &name);
    br_log(1, "encoder: NDK selected codec for %s: %s (name rc %d)",
           mime, name ? name : "unknown", nr);
    if (name) AMediaCodec_releaseName(s->codec, name);
  }
  AMediaFormat *fmt = AMediaFormat_new();
  AMediaFormat_setString(fmt, AMEDIAFORMAT_KEY_MIME, mime);
  AMediaFormat_setInt32(fmt, AMEDIAFORMAT_KEY_WIDTH, (int32_t)width);
  AMediaFormat_setInt32(fmt, AMEDIAFORMAT_KEY_HEIGHT, (int32_t)height);
  AMediaFormat_setInt32(fmt, AMEDIAFORMAT_KEY_COLOR_FORMAT, NDK_COLOR_FORMAT_NV12);
  AMediaFormat_setInt32(fmt, AMEDIAFORMAT_KEY_FRAME_RATE, 30);
  AMediaFormat_setInt32(fmt, "i-frame-interval", 0);               // still: every frame a keyframe
  AMediaFormat_setInt32(fmt, "bitrate-mode", NDK_BITRATE_MODE_CQ); // constant quality
  AMediaFormat_setInt32(fmt, "quality", 90);
  AMediaFormat_setInt32(fmt, AMEDIAFORMAT_KEY_BIT_RATE, (int32_t)(width * height * 4));
  media_status_t rc = AMediaCodec_configure(s->codec, fmt, NULL, NULL, AMEDIACODEC_CONFIGURE_FLAG_ENCODE);
  AMediaFormat_delete(fmt);
  if (s->trace || rc != AMEDIA_OK)
    br_log(rc == AMEDIA_OK ? 1 : 0, "encoder: %s configure status %d (%ux%u, NV12 color 21, CQ mode 0)",
           mime, rc, width, height);
  if (rc != AMEDIA_OK) { AMediaCodec_delete(s->codec); free(s); return NULL; }
  if (s->trace) {
    AMediaFormat *accepted = AMediaCodec_getInputFormat(s->codec);
    if (accepted) {
      int32_t color = -1, w = -1, h = -1;
      (void)AMediaFormat_getInt32(accepted, AMEDIAFORMAT_KEY_COLOR_FORMAT, &color);
      (void)AMediaFormat_getInt32(accepted, AMEDIAFORMAT_KEY_WIDTH, &w);
      (void)AMediaFormat_getInt32(accepted, AMEDIAFORMAT_KEY_HEIGHT, &h);
      br_log(1, "encoder: %s accepted input: %dx%d, color-format %d", mime, w, h, color);
      AMediaFormat_delete(accepted);
    }
  }
  rc = AMediaCodec_start(s->codec);
  if (s->trace || rc != AMEDIA_OK)
    br_log(rc == AMEDIA_OK ? 1 : 0, "encoder: %s start status %d", mime, rc);
  if (rc != AMEDIA_OK) { AMediaCodec_delete(s->codec); free(s); return NULL; }
  s->started = true;
  return s;
}

static int ndk_feed(br_enc_session *s, const uint8_t *nv12, uint32_t len, int64_t pts_us, int force_key) {
  (void)force_key;
  ssize_t ix = AMediaCodec_dequeueInputBuffer(s->codec, 10000);
  if (ix < 0) {
    if (s->trace) br_log(1, "encoder: NDK feed: no input buffer (index %zd)", ix);
    return -EAGAIN;
  }
  size_t cap = 0;
  uint8_t *in = AMediaCodec_getInputBuffer(s->codec, (size_t)ix, &cap);
  if (!in || cap < len) {
    br_log(0, "encoder: NDK feed input buffer too small: wanted %u, capacity %zu", len, cap);
    AMediaCodec_queueInputBuffer(s->codec, (size_t)ix, 0, 0, 0, 0);
    return -EINVAL;
  }
  memcpy(in, nv12, len);
  media_status_t rc = AMediaCodec_queueInputBuffer(s->codec, (size_t)ix, 0, len, (uint64_t)pts_us, 0);
  if (s->trace || rc != AMEDIA_OK)
    br_log(rc == AMEDIA_OK ? 1 : 0, "encoder: NDK feed: index %zd, %u bytes, pts %lld us, queue status %d",
           ix, len, (long long)pts_us, rc);
  return rc == AMEDIA_OK ? 0 : -EIO;
}

static int ndk_drain(br_enc_session *s) {
  if (s->eos_queued) return 0;
  ssize_t ix = AMediaCodec_dequeueInputBuffer(s->codec, 10000);
  if (ix < 0) {
    if (s->trace) br_log(1, "encoder: NDK drain: no input buffer (index %zd)", ix);
    return -EAGAIN;
  }
  media_status_t rc = AMediaCodec_queueInputBuffer(s->codec, (size_t)ix, 0, 0, 0,
                                                   AMEDIACODEC_BUFFER_FLAG_END_OF_STREAM);
  s->eos_queued = rc == AMEDIA_OK;
  if (s->trace || rc != AMEDIA_OK)
    br_log(rc == AMEDIA_OK ? 1 : 0, "encoder: NDK drain: EOS input index %zd, queue status %d", ix, rc);
  return s->eos_queued ? 0 : -EIO;
}

static int ndk_poll(br_enc_session *s, uint8_t *buf, uint32_t cap, int *key, int64_t *pts_us, int *eos) {
  *key = 0; *eos = 0; *pts_us = 0;
  AMediaCodecBufferInfo info;
  ssize_t ix = AMediaCodec_dequeueOutputBuffer(s->codec, &info, 0);
  s->polls++;
  if (ix == AMEDIACODEC_INFO_TRY_AGAIN_LATER) {
    s->not_ready++;
    if (s->trace && (s->polls == 1 || s->polls % 1000 == 0))
      br_log(1, "encoder: NDK output poll %u: not-ready %u, format-changed %u, buffer-changed %u, produced %u",
             s->polls, s->not_ready, s->formats, s->buffers_changed, s->outputs);
    return 0;
  }
  if (ix == AMEDIACODEC_INFO_OUTPUT_FORMAT_CHANGED) {
    s->formats++;
    if (s->trace) {
      AMediaFormat *of = AMediaCodec_getOutputFormat(s->codec);
      br_log(1, "encoder: NDK output format changed (%u): %s",
             s->formats, of ? AMediaFormat_toString(of) : "unavailable");
      if (of) AMediaFormat_delete(of);
    }
    return 0;
  }
  if (ix == AMEDIACODEC_INFO_OUTPUT_BUFFERS_CHANGED) {
    s->buffers_changed++;
    if (s->trace) br_log(1, "encoder: NDK output buffers changed (%u)", s->buffers_changed);
    return 0;
  }
  if (ix < 0) {
    br_log(0, "encoder: NDK output dequeue failed: index %zd after %u polls", ix, s->polls);
    return -EIO;
  }
  s->outputs++;
  if (s->trace && s->outputs <= 8)
    br_log(1, "encoder: NDK output %u: buffer index %zd, size %d, flags %#x, pts %lld us",
           s->outputs, ix, info.size, info.flags, (long long)info.presentationTimeUs);
  size_t out_cap = 0;
  uint8_t *out = AMediaCodec_getOutputBuffer(s->codec, (size_t)ix, &out_cap);
  int bytes = 0;
  if (out && (uint32_t)info.size <= cap) {
    memcpy(buf, out + info.offset, (size_t)info.size);
    bytes = info.size;
    *pts_us = info.presentationTimeUs;
    if (info.flags & (AMEDIACODEC_BUFFER_FLAG_KEY_FRAME | AMEDIACODEC_BUFFER_FLAG_CODEC_CONFIG)) *key = 1;
  } else if (info.size > (int32_t)cap) {
    bytes = -ENOSPC;
  }
  if (info.flags & AMEDIACODEC_BUFFER_FLAG_END_OF_STREAM) *eos = 1;
  AMediaCodec_releaseOutputBuffer(s->codec, (size_t)ix, false);
  return bytes;
}

static void ndk_close(br_enc_session *s) {
  if (s->codec) { if (s->started) AMediaCodec_stop(s->codec); AMediaCodec_delete(s->codec); }
  free(s);
}

static const br_encoder_backend ndk = {
  .name = "mediacodec", .open = ndk_open, .feed = ndk_feed, .drain = ndk_drain, .poll = ndk_poll, .close = ndk_close,
};

const br_encoder_backend *br_encoder_backend_ndk(void) { return &ndk; }
