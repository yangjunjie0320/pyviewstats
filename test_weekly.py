import asyncio
import logging
import sys
sys.path.insert(0, '/app')
from config import load_settings
from src.feishu_doc import FeishuDocArchiver
from src.translator import GeminiTranslator
from src.video_registry import VideoRegistry
from src.youtube import YouTubeDurationFetcher
from utils.cache import get_cache
from utils.logging import configure_logging

async def gen_weekly():
    configure_logging()
    s = load_settings()
    c = get_cache()
    t = s.duration_threshold_secs
    r = VideoRegistry(c)
    
    wk = r.get_week_key()
    entries = r.get_week_buffer(wk)
    print(f'Buffer: {len(entries)} videos for {wk}')

    yt = YouTubeDurationFetcher(c)
    entries = await yt.enrich_durations(entries)

    lv = sorted([e for e in entries if (e.duration_secs or 0) >= t], key=lambda e: e.views, reverse=True)
    sv = sorted([e for e in entries if 0 < (e.duration_secs or 0) < t], key=lambda e: e.views, reverse=True)
    print(f'Long: {len(lv)}, Short: {len(sv)}')

    tr = GeminiTranslator(s.gemini_api_key, c)
    if lv: lv = await tr.translate_entries(lv)
    if sv: sv = await tr.translate_entries(sv)

    archiver = FeishuDocArchiver(s, c)
    doc_id = await archiver.archive_weekly_report(lv, sv, category_name='Autos & Vehicles', week_key=wk, threshold_secs=t)
    print(f'Done: {doc_id}')

if __name__ == '__main__':
    asyncio.run(gen_weekly())
