#include <libavcodec/avcodec.h>
#include <libavutil/hwcontext.h>
#include <libswresample/swresample.h>

#include <stdio.h>
#include <string.h>

static int has_d3d11va(const AVCodec *codec) {
    for (int i = 0;; ++i) {
        const AVCodecHWConfig *config = avcodec_get_hw_config(codec, i);
        if (!config) {
            return 0;
        }
        if (config->device_type == AV_HWDEVICE_TYPE_D3D11VA &&
            (config->methods & AV_CODEC_HW_CONFIG_METHOD_HW_DEVICE_CTX)) {
            return 1;
        }
    }
}

int main(void) {
    const char *names[] = {"h264", "hevc", "aac", "opus"};
    for (size_t i = 0; i < sizeof(names) / sizeof(names[0]); ++i) {
        const AVCodec *codec = avcodec_find_decoder_by_name(names[i]);
        if (!codec) {
            fprintf(stderr, "Missing decoder: %s\n", names[i]);
            return 1;
        }
        if (i < 2 && !has_d3d11va(codec)) {
            fprintf(stderr, "Missing D3D11VA configuration: %s\n", names[i]);
            return 1;
        }
    }
    SwrContext *resampler = swr_alloc();
    if (!resampler) {
        fputs("Unable to allocate swresample context\n", stderr);
        return 1;
    }
    swr_free(&resampler);
    if ((avcodec_version() >> 16) != 61 ||
        (avutil_version() >> 16) != 59 ||
        (swresample_version() >> 16) != 5) {
        fputs("Unexpected FFmpeg ABI version\n", stderr);
        return 1;
    }
    puts("Minimal FFmpeg decoder smoke test passed.");
    return 0;
}
