import logging
import time
from datetime import datetime
from pathlib import Path

import environ
import requests
import tweepy
import twitter
from mastodon import Mastodon

logger = logging.getLogger(__name__)


class Twooter:

    
    def __init__(self):
        base_dir = Path(__file__).parent

        env = environ.Env()
        environ.Env.read_env()

        self.look_back_seconds = env.int("LOOKBACK_SECONDS", default=60)

        self.twitter_user = env("TWITTER_USER")
        self.tw_api = twitter.Api(
            consumer_key=env("TWITTER_API_KEY"),
            consumer_secret=env("TWITTER_API_SECRET"),
            access_token_key=env("TWITTER_ACCESS_KEY"),
            access_token_secret=env("TWITTER_ACCESS_SECRET"),
        )
        self.api = tweepy.API(tweepy.OAuth2BearerHandler(env("TWITTER_BEARER_TOKEN")))
        self.last_tweet_id = None
        self.media_dir = Path("media")
        self.media_dir.mkdir(exist_ok=True)

        self.mastodon = Mastodon(client_id=base_dir / "twooter.secret")
        self.mastodon.log_in(
            env("MASTODON_USER"),
            env("MASTODON_PW"),
        )
        self.cache_file = base_dir / ".cache"
        self.tooted_tweet_ids = self.read_from_cache()

    def read_from_cache(self):
        if not self.cache_file.exists():
            self.cache_file.touch()
            return set()
        else:
            tooted_ids = self.cache_file.read_text().split("\n")
            return set([int(tid) for tid in tooted_ids if tid])

    def get_tweets(self):
        tweets = self.tw_api.GetUserTimeline(
            screen_name=self.twitter_user,
            include_rts=False,
            exclude_replies=True,
            since_id=self.last_tweet_id,
            count=5,
        )

        def _recent(tw):
            tw_time = datetime.strptime(tw.created_at, "%a %b %d %H:%M:%S +0000 %Y")
            return (datetime.now() - tw_time).total_seconds() < self.look_back_seconds

        # only return tweets within last minute, in reverse order (so we toot the
        # earliest first)
        for i in range(len(tweets)):
            tweet = tweets.pop()
            if tweet.id not in self.tooted_tweet_ids and _recent(tweet):
                yield tweet

    def retrieve_tweet_for_tooting(self, tweet_id):
        # get the tweet and download any media
        tweet = self.api.get_status(tweet_id, tweet_mode="extended")
        has_photos = False

        text = tweet.full_text
        for media in tweet.entities.get("media", []):
            self.download_image(tweet_id, media["media_url"])
            # remove the shortened twitter url
            text = text.replace(media["url"], "")
            has_photos = True

        # replace any urls in the tweet with their expanded version
        for url in tweet.entities.get("urls", []):
            text = text.replace(url["url"], url["expanded_url"])

        return text, has_photos

    def download_image(self, tweet_id, media_url):
        filename = media_url.split("/")[-1]
        download_dir = self.media_dir / str(tweet_id)
        download_dir.mkdir(exist_ok=True)
        download_file = download_dir / filename
        # Send GET request
        response = requests.get(media_url)
        # Save the image
        if response.status_code == 200:
            with open(download_file, "wb") as f:
                f.write(response.content)
        else:
            logger.error(
                "Image download %s failed: %s", media_url, response.status_code
            )

    def toot(self, tweet_text, tweet_id, has_photos):
        # first create the media posts
        media_ids = []
        if has_photos:
            for photo_file in (self.media_dir / str(tweet_id)).iterdir():
                media_dict = self.mastodon.media_post(photo_file)
                media_ids.append(media_dict["id"])
        # now create the status update with the media ids
        self.mastodon.status_post(tweet_text, media_ids=media_ids)

    def cache(self, tweet_id):
        self.tooted_tweet_ids.add(tweet_id)
        with open(self.cache_file, "a") as out_f:
            out_f.write(f"{tweet_id}\n")

    def tweets_to_toots(self):
        tweets = self.get_tweets()
        for tweet in tweets:
            logger.info("Tweet %s found, tooting...", tweet.id)
            tweet_text, has_photos = self.retrieve_tweet_for_tooting(tweet.id)
            self.toot(tweet_text, tweet.id, has_photos)
            print(tweet_text)
            self.last_tweet_id = tweet.id
            self.cache(tweet.id)

    def run(self):
        while True:
            logger.info("Fetching tweets")
            self.tweets_to_toots()
            time.sleep(30)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s:%(levelname)s:%(message)s"
    )
    twooter = Twooter()
    twooter.run()
