#include <libavutil/avutil.h>
#include <libavutil/channel_layout.h>
#include <libavutil/mem.h>
#include <libswresample/swresample.h>

int redrain_ffmpeg_link_smoke(void)
{
    AVChannelLayout layout;
    SwrContext *context = NULL;
    void *buffer = av_malloc(64);
    av_channel_layout_default(&layout, 2);
    int result = swr_alloc_set_opts2(&context, &layout, AV_SAMPLE_FMT_S16, 48000,
                                    &layout, AV_SAMPLE_FMT_FLT, 44100, 0, NULL);
    if (result >= 0)
        result = swr_init(context);
    if (result >= 0)
        result = swr_convert(context, NULL, 0, NULL, 0);
    swr_free(&context);
    av_channel_layout_uninit(&layout);
    av_free(buffer);
    return result + (int)(avutil_version() == 0);
}
