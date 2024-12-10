import json
import requests
from datetime import datetime, timedelta

class PodcastCache:
    def __init__(self, cache_file='podcast_cache.json', cache_duration=timedelta(days=7)):
        self.cache_file = cache_file
        self.cache_duration = cache_duration
        self.load_cache()

    def load_cache(self):
        try:
            with open(self.cache_file, 'r') as f:
                self.cache = json.load(f)
                print('Cache loaded successfully.')
        except (FileNotFoundError, json.JSONDecodeError):
            self.cache = {}
            print('Cache file not found or is empty. Starting with an empty cache.')

    def save_cache(self):
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache, f)
            print('Cache saved successfully.')

    def fetch_podcast(self, url):
        current_time = datetime.now()
        if url in self.cache:
            cached_time = datetime.fromisoformat(self.cache[url]['timestamp'])
            if current_time - cached_time < self.cache_duration:
                print('Cache hit for URL:', url)
                return self.cache[url]['data']

        print('Fetching new data for URL:', url)
        # Fetch from the source
        start_time = datetime.now()  # Start timing
        response = requests.get(url)
        elapsed_time = datetime.now() - start_time  # Calculate elapsed time
        print(f'Fetching took: {elapsed_time.total_seconds()} seconds')  # Log fetch time

        if response.status_code == 200:
            podcast_data = response.json()
            print(f'Response size: {len(podcast_data)} bytes')  # Log response size
            self.cache[url] = {'data': podcast_data, 'timestamp': current_time.isoformat()}
            self.save_cache()
            return podcast_data
        else:
            raise Exception(f'Failed to fetch podcast: {response.status_code}')

    def get_podcast(self, url):
        try:
            return self.fetch_podcast(url)
        except Exception as e:
            print(e)
            return None

# Example usage:
# cache = PodcastCache()
# podcast = cache.get_podcast('https://example.com/podcast')
