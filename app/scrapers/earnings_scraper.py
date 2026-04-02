from youtube_transcript_api import YouTubeTranscriptApi
from app.scrapers.base import BaseScraper
from app.database.repository import save_market_news
from datetime import datetime

class EarningsScraper(BaseScraper):
    def __init__(self, db, video_ids: list):
        super().__init__(db)
        self.video_ids = video_ids

    def run(self):
        self.logger.info(f"Starting Earnings Scraper for {len(self.videos_ids)} videos...")
        count = 0

        for video_id in self.video_ids:
            try:
                transcript_list = YouTubeTranscriptApi.get_transcript(self.video_id)
                full_text = " ".join([t['text'] for t in transcript_list])

                news_data = {
                    "id": f"yt_earnings_{video_id}",
                    "title": f"Earnings Call Transcript: {video_id}",
                    "source": "YouTube Earnings Call",
                    "url": f"https://youtube.com/watch?v={video_id}",
                    "content": full_text,
                    "published_at": datetime.now()
                }

                if save_market_news(self.db, news_data):
                    count += 1
            
            except Exception as e:
                self.logger.error(f"Failed to fetch transcript for {video_id}. It may lack CCs or be region-blocked: {e}")
        
        self.logger.info(f"Saved {count} new earnings transcripts.")