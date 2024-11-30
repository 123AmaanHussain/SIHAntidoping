# Flask and Extensions
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from flask_cors import CORS

# Database
from pymongo import MongoClient
from bson import ObjectId

# File Handling
from werkzeug.utils import secure_filename
import mutagen
from mutagen.mp3 import MP3
from fpdf import FPDF

# External APIs
from newsapi import NewsApiClient
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from googleapiclient.discovery import build
import google.generativeai as genai

# Web3 and Blockchain
from blockchain_service import BlockchainService
from web3 import Web3

# Data Processing
from bs4 import BeautifulSoup
import feedparser
import xml.etree.ElementTree as ET
import html
from collections import deque

# Standard Library
import os
import json
import time
import random
import logging
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get API key from environment variable
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
print(f"API Key loaded: {'[MASKED]' if GOOGLE_API_KEY else 'None'}")

app = Flask(__name__, static_folder="static")
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-here')
CORS(app)

# Initialize MongoDB connection with error handling
try:
    client = MongoClient(os.getenv('MONGO_URI', 'mongodb://localhost:27017/'), serverSelectionTimeoutMS=5000)
    client.server_info()  # This will raise an exception if MongoDB is not running
    db = client['gamified_quizzes']
    logging.info("Successfully connected to MongoDB")
except Exception as e:
    logging.error(f"Failed to connect to MongoDB: {str(e)}")
    # Create an in-memory quiz storage as fallback
    class InMemoryQuizDB:
        def __init__(self):
            self.quizzes = {}
            self.quiz_results = {}
        
        def find_one(self, query, projection=None):
            quiz_id = query.get('quiz_id')
            return self.quizzes.get(quiz_id)
        
        def insert_one(self, document):
            if 'quiz_id' in document:
                self.quizzes[document['quiz_id']] = document
            return type('obj', (object,), {'inserted_id': 1})
        
        def drop(self):
            self.quizzes.clear()
    
    db = type('obj', (object,), {
        'quizzes': InMemoryQuizDB(),
        'quiz_results': {},
        'podcasts': {}
    })
    logging.warning("Using in-memory storage as fallback")

nutrition_plans = db.nutrition_plans

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('antidoping.log'),
        logging.StreamHandler()
    ]
)

# Initialize News API
newsapi = NewsApiClient(api_key=os.getenv('NEWS_API_KEY'))

# Initialize blockchain service
try:
    blockchain_service = BlockchainService()
    logging.info("Blockchain service initialized")
except Exception as e:
    logging.warning(f"Failed to initialize blockchain service: {str(e)}")
    blockchain_service = None

# Configure Gemini
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-pro')

# Create certificates directory if it doesn't exist
os.makedirs('certificates', exist_ok=True)

# Configure upload folder for podcasts
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'podcasts')
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'ogg'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Podcast categories
PODCAST_CATEGORIES = [
    'Anti-Doping Rules',
    'Athlete Stories',
    'News & Updates',
    'Training & Education',
    'Clean Sport',
    'Health & Wellness'
]

# Sample podcast data
SAMPLE_PODCASTS = [
    {
        'title': 'Understanding Anti-Doping Rules',
        'description': 'A comprehensive guide to anti-doping regulations and their importance in sports.',
        'category': 'Anti-Doping Rules',
        'author': 'Dr. Sarah Johnson',
        'duration': 1800,  # 30 minutes
        'filename': 'understanding_antidoping.mp3',
        'upload_date': datetime.utcnow()
    },
    {
        'title': 'Athlete Stories: Clean Sport Champions',
        'description': 'Listen to inspiring stories from athletes who compete clean and promote fair play.',
        'category': 'Athlete Stories',
        'author': 'Michael Chen',
        'duration': 1200,  # 20 minutes
        'filename': 'clean_sport_champions.mp3',
        'upload_date': datetime.utcnow()
    },
    {
        'title': 'Latest Updates in Anti-Doping Policies',
        'description': 'Stay informed about the latest developments and changes in anti-doping policies.',
        'category': 'News & Updates',
        'author': 'Emma Williams',
        'duration': 900,  # 15 minutes
        'filename': 'policy_updates.mp3',
        'upload_date': datetime.utcnow()
    }
]

def init_sample_podcasts():
    try:
        # Check if podcasts collection exists and is empty
        if 'podcasts' not in db.list_collection_names() or db.podcasts.count_documents({}) == 0:
            # Insert sample podcasts
            db.podcasts.insert_many(SAMPLE_PODCASTS)
            logging.info("Initialized sample podcast data")
    except Exception as e:
        logging.error(f"Error initializing sample podcasts: {str(e)}")

# Initialize sample podcasts when app starts
init_sample_podcasts()

# News cache
news_cache = {
    'last_update': None,
    'data': []
}

# Routes
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/podcasts")
def podcasts():
    return render_template("podcasts.html")

@app.route("/digitaltwin")
def digitaltwin():
    return render_template("digitaltwin.html")

@app.route("/smartlabels")
def smartlabels():
    return render_template("smartlabels.html")

@app.route('/antidopingwiki')
def antidopingwiki():
    global news_cache
    current_time = datetime.utcnow()
    
    # Check if we have cached news that's less than 30 minutes old
    if (news_cache['last_update'] and 
        (current_time - news_cache['last_update']).total_seconds() < 1800):
        return render_template('antidopingwiki.html', news=news_cache['data'])
    
    try:
        # Fetch news about doping in sports
        doping_response = newsapi.get_everything(
            q='doping sports athletics',
            language='en',
            sort_by='publishedAt',
            from_param=(datetime.utcnow() - timedelta(days=30)).strftime('%Y-%m-%d'),
            page_size=10
        )
        
        # Fetch general sports news
        sports_response = newsapi.get_top_headlines(
            category='sports',
            language='en',
            page_size=10
        )
        
        all_news = []
        
        # Process doping news
        if doping_response.get('status') == 'ok' and doping_response.get('articles'):
            for article in doping_response['articles']:
                if article.get('title') and article.get('description'):
                    all_news.append({
                        'title': article.get('title', ''),
                        'description': article.get('description', ''),
                        'url': article.get('url', '#'),
                        'image': article.get('urlToImage', None),
                        'publishedAt': datetime.strptime(article.get('publishedAt', datetime.utcnow().isoformat()), 
                                                       '%Y-%m-%dT%H:%M:%SZ').strftime('%B %d, %Y'),
                        'source': article.get('source', {}).get('name', 'Unknown Source'),
                        'category': 'Doping News'
                    })
            
        # Process sports news
        if sports_response.get('status') == 'ok' and sports_response.get('articles'):
            for article in sports_response['articles']:
                if article.get('title') and article.get('description'):
                    all_news.append({
                        'title': article.get('title', ''),
                        'description': article.get('description', ''),
                        'url': article.get('url', '#'),
                        'image': article.get('urlToImage', None),
                        'publishedAt': datetime.strptime(article.get('publishedAt', datetime.utcnow().isoformat()),
                                                       '%Y-%m-%dT%H:%M:%SZ').strftime('%B %d, %Y'),
                        'source': article.get('source', {}).get('name', 'Unknown Source'),
                        'category': 'Sports News'
                    })
        
        if all_news:
            # Update cache if we got news successfully
            news_cache['last_update'] = current_time
            news_cache['data'] = all_news
            
    except Exception as e:
        logging.error(f"Error fetching news: {str(e)}")
        import traceback
        logging.error(f"Full error traceback: {traceback.format_exc()}")
        
        # Use cached data if available, otherwise use sample news
        if news_cache['data']:
            all_news = news_cache['data']
        else:
            all_news = [
                {
                    'title': 'Sample Sports News',
                    'description': 'This is a sample sports news article. The news API might be temporarily unavailable.',
                    'url': '#',
                    'image': None,
                    'publishedAt': datetime.utcnow().strftime('%B %d, %Y'),
                    'source': 'Sample Source',
                    'category': 'Sports News'
                },
                {
                    'title': 'Sample Doping News',
                    'description': 'This is a sample doping news article. The news API might be temporarily unavailable.',
                    'url': '#',
                    'image': None,
                    'publishedAt': datetime.utcnow().strftime('%B %d, %Y'),
                    'source': 'Sample Source',
                    'category': 'Doping News'
                }
            ]
    
    return render_template('antidopingwiki.html', news=all_news)

@app.route("/caloriescalculator")
def caloriescalculator():
    return render_template("caloriescalculator.html")

@app.route("/ai-coach-page")
def ai_coach_page():
    return render_template("ai_coach.html")

@app.route("/games")
def games():
    return render_template("games.html")

@app.route('/get_quiz/<quiz_id>')
def get_quiz(quiz_id):
    try:
        logging.info(f"Fetching quiz with ID: {quiz_id}")
        quiz = db.quizzes.find_one({"quiz_id": quiz_id}, {"_id": 0})
        logging.info(f"Found quiz: {quiz}")
        
        if not quiz:
            # Try to initialize quiz data
            if init_quiz_data():
                quiz = db.quizzes.find_one({"quiz_id": quiz_id}, {"_id": 0})
        
        if quiz:
            return jsonify({
                "success": True,
                "quiz": quiz
            })
        
        return jsonify({
            "success": False,
            "error": "Quiz not found"
        }), 404
        
    except Exception as e:
        logging.error(f"Error getting quiz: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

class PodcastFetcher:
    def __init__(self):
        """Initialize the podcast fetcher with API clients"""
        # Initialize Spotify client
        self.spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials())
        
        # Initialize YouTube client
        self.youtube = build('youtube', 'v3', developerKey=os.environ.get('YOUTUBE_API_KEY'))
        
        # Anti-doping related keywords for content filtering
        self.antidoping_keywords = [
            'anti-doping', 'antidoping', 'doping', 'wada', 'usada', 'clean sport',
            'drug testing', 'prohibited substances', 'banned substances', 'athlete integrity',
            'sports integrity', 'fair play', 'clean athlete', 'performance enhancing',
            'drug free sport', 'anti doping violation', 'therapeutic use exemption', 'tue',
            'whereabouts', 'testing pool', 'biological passport', 'prohibited list',
            'anti-doping rule', 'sample collection', 'doping control', 'adams',
            'world anti-doping', 'national anti-doping', 'doping test'
        ]
        
        # Search queries for finding relevant content
        self.search_queries = [
            'anti-doping podcast',
            'clean sport podcast',
            'doping in sports podcast',
            'sports integrity podcast',
            'wada podcast',
            'usada podcast'
        ]
        
        # YouTube channel IDs
        self.youtube_channels = [
            'UCQxkGRRkhVeOQpwR9WEsV3A',  # World Anti-Doping Agency (WADA)
            'UCuJcLm5uNXtXUVHHLs2W_-Q',  # U.S. Anti-Doping Agency (USADA)
            'UC5nU0k_KnOXAwK_6cLvjfDQ'   # UK Anti-Doping (UKAD)
        ]
        
        # Rate limiting attributes
        self.spotify_calls = deque(maxlen=30)  # Track last 30 Spotify API calls
        self.youtube_quota = {
            'daily_limit': 10000,
            'used': 0,
            'reset_time': datetime.now()
        }
        
        # Add iTunes search URL
        self.itunes_search_url = "https://itunes.apple.com/search"
        
    def is_antidoping_content(self, title, description):
        """Check if content is related to sports or anti-doping based on title and description"""
        # Make the filter more lenient by always returning True to get all content
        return True

    def _check_spotify_rate_limit(self):
        """Implement Spotify rate limiting - 30 requests per second"""
        now = time.time()
        # Remove calls older than 1 second
        while self.spotify_calls and self.spotify_calls[0] < now - 1:
            self.spotify_calls.popleft()
        
        if len(self.spotify_calls) >= 30:
            sleep_time = 1 - (now - self.spotify_calls[0])
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        self.spotify_calls.append(now)

    def _check_youtube_quota(self, cost=1):
        """Check YouTube API quota"""
        now = datetime.now()
        
        # Reset quota if it's a new day
        if now.date() > self.youtube_quota['reset_time'].date():
            self.youtube_quota['used'] = 0
            self.youtube_quota['reset_time'] = now
        
        # Check if we have enough quota
        if self.youtube_quota['used'] + cost > self.youtube_quota['daily_limit']:
            raise Exception("YouTube API daily quota exceeded")
        
        self.youtube_quota['used'] += cost

    def fetch_spotify_podcasts(self):
        """Fetch sports and anti-doping related episodes from Spotify using search"""
        podcasts = []
        try:
            logging.info("Starting Spotify podcast search")
            
            # Broader search queries
            search_terms = ['sports', 'athlete', 'olympic', 'fitness', 'training', 'health']
            
            # Search for podcasts using our queries
            for query in search_terms:
                try:
                    self._check_spotify_rate_limit()
                    results = self.spotify.search(q=query, type='show', market='US', limit=10)
                    
                    if not results or 'shows' not in results or 'items' not in results['shows']:
                        continue
                    
                    for show in results['shows']['items']:
                        try:
                            show_id = show['id']
                            show_name = show['name']
                            publisher = show['publisher']
                            
                            episodes = self.spotify.show_episodes(show_id, limit=5, market='US')
                            
                            if not episodes or 'items' not in episodes:
                                continue
                            
                            for episode in episodes['items']:
                                try:
                                    podcast = {
                                        'title': episode['name'],
                                        'description': episode.get('description', '')[:500],
                                        'author': publisher,
                                        'published_date': episode.get('release_date', ''),
                                        'image_url': episode['images'][0]['url'] if episode.get('images') and episode['images'] else None,
                                        'source_url': episode['external_urls']['spotify'] if episode.get('external_urls') else '',
                                        'source_type': 'spotify',
                                        'category': self._categorize_content(episode['name'], episode.get('description', '')),
                                        'language': episode.get('language', 'en'),
                                        'duration_ms': episode.get('duration_ms', 0)
                                    }
                                    
                                    if not any(p['source_url'] == podcast['source_url'] for p in podcasts):
                                        podcasts.append(podcast)
                                        
                                except Exception as episode_error:
                                    continue
                                    
                        except Exception:
                            continue
                            
                except Exception as search_error:
                    if "429" in str(search_error):
                        time.sleep(5)
                    continue
                    
        except Exception as e:
            logging.error(f"Error in fetch_spotify_podcasts: {str(e)}")
        
        return podcasts

    def fetch_youtube_videos(self):
        """Fetch sports and fitness related videos from YouTube"""
        videos = []
        try:
            logging.info("Starting YouTube video fetch")
            
            # Broader search terms
            search_terms = ['sports', 'athlete', 'fitness', 'training', 'olympics']
            
            for term in search_terms:
                try:
                    self._check_youtube_quota(cost=1)
                    
                    search_request = self.youtube.search().list(
                        part="snippet",
                        q=term,
                        maxResults=10,
                        order="date",
                        type="video"
                    ).execute()
                    
                    if not search_request.get('items'):
                        continue
                    
                    for item in search_request['items']:
                        try:
                            snippet = item['snippet']
                            
                            video = {
                                'title': snippet['title'],
                                'description': snippet.get('description', '')[:500],
                                'author': snippet['channelTitle'],
                                'published_date': snippet['publishedAt'],
                                'image_url': snippet.get('thumbnails', {}).get('high', {}).get('url'),
                                'source_url': f"https://www.youtube.com/watch?v={item['id']['videoId']}",
                                'source_type': 'youtube',
                                'category': self._categorize_content(snippet['title'], snippet.get('description', '')),
                                'language': 'en'
                            }
                            
                            if not any(v['source_url'] == video['source_url'] for v in videos):
                                videos.append(video)
                                
                        except Exception:
                            continue
                            
                except Exception as search_error:
                    if "quotaExceeded" in str(search_error):
                        break
                    elif "429" in str(search_error):
                        time.sleep(60)
                    continue
                    
        except Exception as e:
            logging.error(f"Error in fetch_youtube_videos: {str(e)}")
        
        return videos

    def fetch_itunes_podcasts(self):
        """Fetch sports and fitness related podcasts from iTunes"""
        podcasts = []
        try:
            logging.info("Starting iTunes podcast search")
            
            # Broader search terms
            search_terms = ['sports', 'athlete', 'fitness', 'training', 'olympics']
            
            for query in search_terms:
                try:
                    params = {
                        'term': query,
                        'entity': 'podcast',
                        'limit': 20,
                        'media': 'podcast'
                    }
                    
                    response = requests.get(self.itunes_search_url, params=params)
                    if response.status_code == 200:
                        results = response.json()
                        
                        for item in results.get('results', []):
                            try:
                                podcast = {
                                    'title': item.get('collectionName', ''),
                                    'description': item.get('description', '')[:500],
                                    'author': item.get('artistName', ''),
                                    'published_date': datetime.now().strftime('%Y-%m-%d'),
                                    'image_url': item.get('artworkUrl600', ''),
                                    'source_url': item.get('collectionViewUrl', ''),
                                    'source_type': 'itunes',
                                    'category': self._categorize_content(
                                        item.get('collectionName', ''),
                                        item.get('description', '')
                                    ),
                                    'language': 'en'
                                }
                                
                                if not any(p['source_url'] == podcast['source_url'] for p in podcasts):
                                    podcasts.append(podcast)
                                    
                            except Exception:
                                continue
                                
                    time.sleep(1)
                    
                except Exception:
                    continue
                    
        except Exception as e:
            logging.error(f"Error in fetch_itunes_podcasts: {str(e)}")
            
        return podcasts

    def fetch_all_podcasts(self):
        """Fetch podcasts from all available sources"""
        all_podcasts = []
        
        # Try iTunes first as it's more reliable
        itunes_podcasts = self.fetch_itunes_podcasts()
        all_podcasts.extend(itunes_podcasts)
        
        try:
            # Try Spotify if iTunes doesn't return enough results
            if len(all_podcasts) < 20:
                spotify_podcasts = self.fetch_spotify_podcasts()
                all_podcasts.extend(spotify_podcasts)
        except Exception as spotify_error:
            logging.warning(f"Spotify fetch failed, continuing with iTunes results: {str(spotify_error)}")
        
        try:
            # Add YouTube videos as supplementary content
            youtube_videos = self.fetch_youtube_videos()
            all_podcasts.extend(youtube_videos)
        except Exception as youtube_error:
            logging.warning(f"YouTube fetch failed, continuing with podcast results: {str(youtube_error)}")
        
        return all_podcasts

    def _categorize_content(self, title, description):
        """Categorize content based on title and description"""
        title_lower = title.lower()
        description_lower = description.lower()
        
        # Define category keywords
        categories = {
            'Rules & Compliance': ['rule', 'compliance', 'violation', 'sanction', 'regulation', 'policy'],
            'Testing & Science': ['test', 'sample', 'laboratory', 'biological passport', 'analysis'],
            'Education': ['education', 'learn', 'guide', 'understand', 'awareness'],
            'Athlete Stories': ['story', 'interview', 'experience', 'journey', 'athlete'],
            'Updates & News': ['update', 'news', 'announcement', 'latest', 'change'],
            'Clean Sport': ['clean sport', 'integrity', 'fair play', 'values']
        }
        
        # Check each category
        for category, keywords in categories.items():
            for keyword in keywords:
                if keyword in title_lower or keyword in description_lower:
                    return category
        
        return 'General Anti-Doping'

@app.route('/api/podcasts')
def get_podcasts():
    """API endpoint to get sports and anti-doping podcasts from various sources"""
    try:
        # Initialize podcast fetcher if not already initialized
        if not hasattr(app, 'podcast_fetcher'):
            try:
                app.podcast_fetcher = PodcastFetcher()
            except Exception as init_error:
                logging.error(f"Failed to initialize podcast fetcher: {str(init_error)}")
                return jsonify({
                    'success': False,
                    'error': f"Failed to initialize podcast fetcher: {str(init_error)}"
                }), 500

        # Sample podcasts as fallback
        sample_podcasts = [
            {
                'title': 'Clean Sport Insights',
                'description': 'A podcast about maintaining integrity in sports and understanding anti-doping measures.',
                'author': 'Sports Integrity Unit',
                'published_date': datetime.now().strftime('%Y-%m-%d'),
                'image_url': '/static/images/podcast-placeholder.jpg',
                'source_url': '#',
                'source_type': 'sample',
                'category': 'Education & Prevention',
                'language': 'en'
            },
            {
                'title': 'The Athlete\'s Corner',
                'description': 'Weekly discussions about sports, training, and athlete well-being.',
                'author': 'Sports Network',
                'published_date': datetime.now().strftime('%Y-%m-%d'),
                'image_url': '/static/images/podcast-placeholder.jpg',
                'source_url': '#',
                'source_type': 'sample',
                'category': 'Athlete Stories',
                'language': 'en'
            },
            {
                'title': 'Sports Science Today',
                'description': 'Exploring the latest developments in sports science and performance.',
                'author': 'Science in Sports',
                'published_date': datetime.now().strftime('%Y-%m-%d'),
                'image_url': '/static/images/podcast-placeholder.jpg',
                'source_url': '#',
                'source_type': 'sample',
                'category': 'Testing & Science',
                'language': 'en'
            }
        ]

        all_podcasts = []

        # Try to fetch from each source independently
        try:
            itunes_podcasts = app.podcast_fetcher.fetch_itunes_podcasts()
            if itunes_podcasts:
                all_podcasts.extend(itunes_podcasts)
        except Exception as itunes_error:
            logging.error(f"iTunes fetch failed: {str(itunes_error)}")

        try:
            spotify_podcasts = app.podcast_fetcher.fetch_spotify_podcasts()
            if spotify_podcasts:
                all_podcasts.extend(spotify_podcasts)
        except Exception as spotify_error:
            logging.error(f"Spotify fetch failed: {str(spotify_error)}")

        try:
            youtube_videos = app.podcast_fetcher.fetch_youtube_videos()
            if youtube_videos:
                all_podcasts.extend(youtube_videos)
        except Exception as youtube_error:
            logging.error(f"YouTube fetch failed: {str(youtube_error)}")

        # If no podcasts were found from any source, use sample podcasts
        if not all_podcasts:
            logging.info("No podcasts found from external sources, using sample podcasts")
            all_podcasts = sample_podcasts

        # Return all found podcasts
        return jsonify({
            'success': True,
            'data': all_podcasts
        })

    except Exception as e:
        logging.error(f"Error in get_podcasts: {str(e)}")
        # Return sample podcasts on error
        return jsonify({
            'success': True,
            'data': sample_podcasts
        })

@app.route('/submit_quiz', methods=['POST'])
def submit_quiz():
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['user_id', 'quiz_id', 'answers']
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        user_id = data['user_id']
        quiz_id = data['quiz_id']
        answers = data['answers']
        email = data.get('email', '')  # Optional email for blockchain certificate

        # Get quiz data
        quiz = db.quizzes.find_one({"quiz_id": quiz_id}, {"_id": 0})
        if not quiz:
            raise ValueError("Invalid quiz ID")

        # Calculate score
        correct_answers = [q['correct_answer'] for q in quiz['questions']]
        if len(answers) != len(correct_answers):
            raise ValueError("Number of answers does not match number of questions")

        score = calculate_score(answers, correct_answers)
        timestamp = datetime.utcnow()

        # Store quiz result
        quiz_result = {
            'user_id': user_id,
            'quiz_id': quiz_id,
            'score': score,
            'answers': answers,
            'email': email,
            'timestamp': timestamp
        }
        
        # Generate certificate data if passing score
        certificate_data = None
        if score >= 70:
            try:
                token_id = None
                # Attempt to mint blockchain certificate only if email is provided
                if email and blockchain_service:
                    try:
                        token_id = blockchain_service.mint_certificate(
                            recipient_email=email,
                            quiz_title=quiz['title'],
                            score=int(score)
                        )
                    except Exception as e:
                        app.logger.error(f"Error minting blockchain certificate: {str(e)}")
                
                # Generate PDF certificate with token_id if available
                pdf_path = generate_pdf_certificate(user_id, quiz_id, score, timestamp, token_id)
                
                # Store certificate path
                quiz_result['pdf_certificate'] = os.path.basename(pdf_path)
                
                # Generate certificate metadata
                metadata = {
                    'user_id': user_id,
                    'quiz_id': quiz_id,
                    'score': score,
                    'timestamp': timestamp.isoformat(),
                    'token_id': token_id
                }
                
                certificate_data = {
                    'token_id': token_id,
                    'metadata': metadata,
                    'pdf_path': os.path.basename(pdf_path)
                }
                
                quiz_result['certificate'] = certificate_data
                
            except Exception as e:
                app.logger.error(f"Error generating certificate: {str(e)}")
                certificate_data = {'error': str(e)}
        
        # Store result in database
        db.quiz_results.insert_one(quiz_result)

        return jsonify({
            'success': True,
            'score': score,
            'certificate': certificate_data
        })

    except Exception as e:
        app.logger.error(f"Error submitting quiz: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/download_certificate/<user_id>/<filename>')
def download_certificate(user_id, filename):
    try:
        # Security check: ensure filename belongs to the user
        if not filename.startswith(f"{user_id}_"):
            raise ValueError("Invalid certificate access")
            
        certificate_dir = os.path.join(os.path.dirname(__file__), 'certificates')
        return send_from_directory(
            certificate_dir, 
            filename,
            as_attachment=True,
            download_name=f"antidoping_certificate_{user_id}.pdf"
        )
    except Exception as e:
        app.logger.error(f"Error downloading certificate: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route("/get_progress/<user_id>")
def get_progress(user_id):
    try:
        scores = list(db.scores.find({"user_id": user_id}, {"_id": 0}))
        return jsonify(scores), 200
    except Exception as e:
        logging.error(f"Error getting progress: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/anti_doping")
def anti_doping_page():
    return render_template('anti_doping.html')

@app.route('/ai-nutrition-planner')
def ai_nutrition_planner():
    return render_template('ai_nutrition_planner.html')

@app.route('/generate-nutrition-plan', methods=['POST'])
def generate_nutrition_plan():
    try:
        data = request.json
        # Construct the prompt for the model
        prompt = f"""As a professional sports nutritionist, create a detailed weekly nutrition plan for an athlete with the following details:
        Sport: {data['sport']}
        Age: {data['age']}
        Weight: {data['weight']} kg
        Height: {data['height']} cm
        Gender: {data['gender']}
        Training Phase: {data['trainingPhase']}
        Dietary Restrictions: {data['dietaryRestrictions']}
        Goals: {data['goals']}
        
        Please provide a comprehensive nutrition plan including:
        1. Daily caloric needs
        2. Macronutrient distribution
        3. Meal timing around training
        4. Specific food recommendations
        5. Pre and post-workout nutrition
        6. Hydration guidelines
        7. Supplement recommendations (if necessary)
        
        Format the response in a clear, structured way with sections and bullet points."""

        # Generate response using Gemini
        response = model.generate_content(prompt)
        
        # Get the generated text
        nutrition_plan = response.text
        return jsonify({"plan": nutrition_plan})
    except Exception as e:
        print(f"Error in generate_nutrition_plan: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/save-nutrition-plan', methods=['POST'])
def save_nutrition_plan():
    try:
        data = request.json
        # Add timestamp and generate unique ID
        data['created_at'] = datetime.utcnow()
        data['_id'] = str(ObjectId())
        
        # Save to MongoDB
        nutrition_plans.insert_one(data)
        return jsonify({'success': True, 'message': 'Nutrition plan saved successfully', 'plan_id': data['_id']})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/get-saved-plans', methods=['GET'])
def get_saved_plans():
    try:
        # Retrieve all saved plans, sorted by creation date
        saved_plans = list(nutrition_plans.find().sort('created_at', -1))
        # Convert ObjectId to string for JSON serialization
        for plan in saved_plans:
            plan['_id'] = str(plan['_id'])
            plan['created_at'] = plan['created_at'].isoformat()
        return jsonify({'success': True, 'plans': saved_plans})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/delete-nutrition-plan/<plan_id>', methods=['DELETE'])
def delete_nutrition_plan(plan_id):
    try:
        # Delete the plan from MongoDB
        result = nutrition_plans.delete_one({'_id': plan_id})
        if result.deleted_count > 0:
            return jsonify({'success': True, 'message': 'Plan deleted successfully'})
        else:
            return jsonify({'success': False, 'message': 'Plan not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# AI Coach configuration
AI_COACH_PROMPT = """You are an expert AI Sports Coach and Anti-Doping Assistant. Your role is to provide personalized guidance for athletes.

Current language: {language}
Previous conversation:
{context}

User's message: {message}

Please provide a response that:
1. Is clear, concise, and actionable
2. Uses appropriate language and tone for {language}
3. Includes specific training or anti-doping advice when relevant
4. Maintains a supportive and motivating tone
5. References scientific/medical facts when appropriate
6. Emphasizes safety and compliance with anti-doping regulations

Response:"""

@app.route('/chat')
def chat():
    """Render the chat interface"""
    return render_template('chat.html')

@app.route('/ai-coach', methods=['POST'])
def ai_coach_api():
    """Handle AI coach API requests with improved context and error handling"""
    try:
        # Validate request data
        if not request.is_json:
            return jsonify({
                'error': 'Request must be JSON',
                'success': False
            }), 400

        data = request.json
        user_message = data.get('message', '').strip()
        language = data.get('language', 'en')
        context = data.get('context', [])

        # Validate input
        if not user_message:
            return jsonify({
                'error': 'Message cannot be empty',
                'success': False
            }), 400

        # Process conversation context
        context_summary = ""
        if context:
            # Take last 3 interactions for context
            recent_context = context[-6:]  # Last 3 exchanges (user + coach)
            context_summary = "\n".join([
                f"{'User' if item['role'] == 'user' else 'Coach'}: {item['content']}"
                for item in recent_context
            ])

        # Map language codes to full names for better context
        language_names = {
            'en': 'English',
            'es': 'Spanish',
            'fr': 'French',
            'de': 'German',
            'it': 'Italian',
            'pt': 'Portuguese',
            'hi': 'Hindi',
            'zh': 'Chinese'
        }

        # Format the prompt
        formatted_prompt = AI_COACH_PROMPT.format(
            language=language_names.get(language, 'English'),
            context=context_summary,
            message=user_message
        )

        try:
            # Generate response using Gemini
            response = model.generate_content(formatted_prompt)
            coach_response = response.text

            # Translate if needed
            if language != 'en':
                translation_prompt = f"""Translate this sports coaching response to {language_names.get(language, 'English')}.
                Maintain the professional and supportive tone.
                Preserve technical terms, numbers, and proper names.
                
                Original text: {coach_response}
                
                Translation:"""
                
                translation = model.generate_content(translation_prompt)
                coach_response = translation.text

            return jsonify({
                'response': coach_response,
                'success': True
            })

        except Exception as e:
            logging.error(f"Gemini API error: {str(e)}")
            return jsonify({
                'error': 'An error occurred while generating the response. Please try again.',
                'success': False
            }), 500

    except Exception as e:
        logging.error(f"AI coach error: {str(e)}")
        return jsonify({
            'error': 'An unexpected error occurred. Please try again.',
            'success': False
        }), 500

def generate_pdf_certificate(user_id, quiz_id, score, timestamp, token_id=None):
    """Generate a PDF certificate for quiz completion"""
    try:
        # Create certificates directory if it doesn't exist
        certificate_dir = os.path.join(os.path.dirname(__file__), 'certificates')
        os.makedirs(certificate_dir, exist_ok=True)
        
        # Initialize PDF
        pdf = FPDF()
        pdf.add_page()
        
        # Set margins
        pdf.set_margins(20, 20, 20)
        
        # Add certificate styling
        pdf.set_font("Arial", "B", 24)
        pdf.set_text_color(44, 62, 80)  # Dark blue color
        pdf.cell(0, 30, "Certificate of Achievement", ln=True, align='C')
        
        # Add decorative line
        pdf.set_draw_color(41, 128, 185)  # Light blue
        pdf.set_line_width(1)
        pdf.line(30, 45, 180, 45)
        
        # Certificate content
        pdf.set_font("Arial", "", 16)
        pdf.set_text_color(52, 73, 94)  # Dark gray
        pdf.cell(0, 30, "This is to certify that", ln=True, align='C')
        
        # User ID
        pdf.set_font("Arial", "B", 20)
        pdf.cell(0, 15, user_id, ln=True, align='C')
        
        # Achievement text
        pdf.set_font("Arial", "", 16)
        pdf.cell(0, 15, "has successfully completed the", ln=True, align='C')
        pdf.set_font("Arial", "B", 18)
        pdf.cell(0, 15, "Anti-Doping Awareness Quiz", ln=True, align='C')
        
        # Score
        pdf.set_font("Arial", "", 16)
        pdf.cell(0, 15, f"with a score of", ln=True, align='C')
        pdf.set_font("Arial", "B", 20)
        pdf.set_text_color(41, 128, 185)  # Light blue
        pdf.cell(0, 15, f"{score}%", ln=True, align='C')
        
        # Date
        pdf.set_font("Arial", "", 12)
        pdf.set_text_color(52, 73, 94)  # Dark gray
        date_str = timestamp.strftime("%B %d, %Y")
        pdf.cell(0, 15, f"Date: {date_str}", ln=True, align='C')
        
        # Add blockchain verification code if available
        if token_id:
            try:
                # Add verification section
                pdf.ln(10)
                pdf.set_font("Arial", "", 10)
                pdf.set_text_color(128, 128, 128)  # Gray color
                pdf.cell(0, 10, "Certificate Verification", ln=True, align='C')
                
                # Create verification string
                verification_string = f"0x{token_id:016x}"
                
                # Generate QR code
                import qrcode
                from PIL import Image
                import io
                
                # Create QR code
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10,
                    border=4,
                )
                qr.add_data(verification_string)
                qr.make(fit=True)
                
                # Create QR code image
                qr_img = qr.make_image(fill_color="black", back_color="white")
                
                # Save QR code to bytes
                img_byte_arr = io.BytesIO()
                qr_img.save(img_byte_arr, format='PNG')
                img_byte_arr = img_byte_arr.getvalue()
                
                # Save temporary image file
                temp_qr_path = os.path.join(certificate_dir, f'temp_qr_{user_id}.png')
                with open(temp_qr_path, 'wb') as f:
                    f.write(img_byte_arr)
                
                # Add QR code to PDF
                pdf.image(temp_qr_path, x=85, y=pdf.get_y(), w=40, h=40)
                
                # Remove temporary file
                os.remove(temp_qr_path)
                
                # Add some space after QR code
                pdf.ln(45)
                
                # Add verification code
                pdf.set_font("Courier", "", 8)
                pdf.cell(0, 5, "Blockchain Verification Code:", ln=True, align='C')
                pdf.cell(0, 5, verification_string, ln=True, align='C')
                
            except Exception as e:
                logging.error(f"Error adding QR code: {str(e)}")
                # Still add verification code even if QR fails
                pdf.ln(10)
                pdf.set_font("Courier", "", 8)
                pdf.cell(0, 5, "Blockchain Verification Code:", ln=True, align='C')
                pdf.cell(0, 5, f"0x{token_id:016x}", ln=True, align='C')
        
        # Generate unique filename
        filename = f"certificate_{user_id}_{quiz_id}_{int(timestamp.timestamp())}.pdf"
        filepath = os.path.join(certificate_dir, filename)
        
        # Save the PDF
        pdf.output(filepath)
        return filepath
        
    except Exception as e:
        logging.error(f"Error generating certificate: {str(e)}")
        raise

@app.route('/api/podcasts/upload', methods=['POST'])
def upload_podcast():
    try:
        if 'audio_file' not in request.files:
            return jsonify({'success': False, 'error': 'No audio file provided'}), 400
            
        file = request.files['audio_file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No selected file'}), 400
            
        if not file.filename.endswith('.mp3'):
            return jsonify({'success': False, 'error': 'Only MP3 files are supported'}), 400
        
        # Secure the filename
        filename = secure_filename(file.filename)
        
        # Create uploads directory if it doesn't exist
        upload_dir = os.path.join(app.root_path, 'static', 'podcasts')
        os.makedirs(upload_dir, exist_ok=True)
        
        # Save the file
        file_path = os.path.join(upload_dir, filename)
        file.save(file_path)
        
        # Get audio duration using mutagen
        try:
            audio = MP3(file_path)
            duration = int(audio.info.length)
        except Exception as e:
            duration = 0
            logging.error(f"Error getting audio duration: {str(e)}")
        
        # Create podcast document
        podcast = {
            'title': request.form.get('title', 'Untitled Podcast'),
            'description': request.form.get('description', ''),
            'category': request.form.get('category', 'Training & Education'),
            'author': request.form.get('author', 'Anonymous'),
            'filename': filename,
            'duration': duration,
            'upload_date': datetime.utcnow(),
            'language': request.form.get('language', 'en'),
            'tags': request.form.get('tags', '').split(',') if request.form.get('tags') else []
        }
        
        # Save to MongoDB
        result = db.podcasts.insert_one(podcast)
        podcast['_id'] = str(result.inserted_id)
        
        return jsonify({
            'success': True,
            'message': 'Podcast uploaded successfully',
            'podcast': podcast
        })
        
    except Exception as e:
        logging.error(f"Error uploading podcast: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/podcasts/<podcast_id>', methods=['DELETE'])
def delete_podcast(podcast_id):
    try:
        # Find the podcast
        podcast = db.podcasts.find_one({'_id': ObjectId(podcast_id)})
        if not podcast:
            return jsonify({'success': False, 'error': 'Podcast not found'}), 404
            
        # Delete the audio file
        file_path = os.path.join(app.root_path, 'static', 'podcasts', podcast['filename'])
        if os.path.exists(file_path):
            os.remove(file_path)
            
        # Delete from MongoDB
        db.podcasts.delete_one({'_id': ObjectId(podcast_id)})
        
        return jsonify({'success': True, 'message': 'Podcast deleted successfully'})
        
    except Exception as e:
        logging.error(f"Error deleting podcast: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/podcasts/<podcast_id>', methods=['PUT'])
def update_podcast(podcast_id):
    try:
        # Get the podcast
        podcast = db.podcasts.find_one({'_id': ObjectId(podcast_id)})
        if not podcast:
            return jsonify({'success': False, 'error': 'Podcast not found'}), 404
            
        # Update fields
        update_data = {
            'title': request.form.get('title', podcast['title']),
            'description': request.form.get('description', podcast['description']),
            'category': request.form.get('category', podcast['category']),
            'author': request.form.get('author', podcast['author']),
            'language': request.form.get('language', podcast.get('language', 'en')),
            'tags': request.form.get('tags', '').split(',') if request.form.get('tags') else podcast.get('tags', [])
        }
        
        # Update audio file if provided
        if 'audio_file' in request.files:
            file = request.files['audio_file']
            if file.filename != '' and file.filename.endswith('.mp3'):
                # Delete old file
                old_file_path = os.path.join(app.root_path, 'static', 'podcasts', podcast['filename'])
                if os.path.exists(old_file_path):
                    os.remove(old_file_path)
                
                # Save new file
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.root_path, 'static', 'podcasts', filename)
                file.save(file_path)
                
                # Update duration
                try:
                    audio = MP3(file_path)
                    update_data['duration'] = int(audio.info.length)
                except Exception as e:
                    logging.error(f"Error getting audio duration: {str(e)}")
                
                update_data['filename'] = filename
        
        # Update in MongoDB
        db.podcasts.update_one(
            {'_id': ObjectId(podcast_id)},
            {'$set': update_data}
        )
        
        return jsonify({
            'success': True,
            'message': 'Podcast updated successfully',
            'podcast': {**podcast, **update_data, '_id': str(podcast['_id'])}
        })
        
    except Exception as e:
        logging.error(f"Error updating podcast: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

def calculate_score(user_answers, correct_answers):
    """Calculate the percentage score for a quiz"""
    if len(user_answers) != len(correct_answers):
        raise ValueError("Answer length mismatch")
    
    correct_count = sum(1 for user_ans, correct_ans in zip(user_answers, correct_answers) if user_ans == correct_ans)
    return (correct_count / len(correct_answers)) * 100

def fetch_sports_podcasts():
    """Fetch sports and anti-doping related podcasts from multiple sources"""
    all_podcasts = []
    
    # List of RSS feeds for sports and anti-doping content
    rss_feeds = [
        {
            'url': 'https://feeds.megaphone.fm/EMPOW3391357123',  # Sports Integrity Podcast
            'category': 'Sports Integrity'
        },
        {
            'url': 'https://anchor.fm/s/1f8af31c/podcast/rss',  # Play True Podcast
            'category': 'Anti-Doping'
        },
        {
            'url': 'https://feeds.buzzsprout.com/1052198.rss',  # Clean Sport Collective
            'category': 'Clean Sport'
        },
        {
            'url': 'https://feeds.soundcloud.com/users/soundcloud:users:307223250/sounds.rss',  # UKAD Podcast
            'category': 'Anti-Doping'
        },
        {
            'url': 'https://www.listennotes.com/c/r/37a1c7f7e0e246d8a8696a95c7c93d62',  # The Doping Podcast
            'category': 'Anti-Doping Education'
        }
    ]
    
    # YouTube channels and playlists for anti-doping content
    youtube_sources = [
        'https://www.youtube.com/user/wadamovies/videos',  # WADA's YouTube channel
        'https://www.youtube.com/user/cleansport/videos',  # Clean Sport
        'https://www.youtube.com/c/antidoping/videos'  # Anti-Doping Channel
    ]
    
    try:
        # Fetch from RSS feeds
        for feed_info in rss_feeds:
            try:
                feed = feedparser.parse(feed_info['url'])
                for entry in feed.entries[:5]:  # Get latest 5 episodes
                    try:
                        # Extract audio URL from enclosures or content
                        audio_url = ''
                        if hasattr(entry, 'enclosures') and entry.enclosures:
                            audio_url = next((e['href'] for e in entry.enclosures 
                                            if e.get('type', '').startswith('audio/')), '')
                        
                        # Get the largest image from media content or thumbnail
                        image_url = ''
                        if hasattr(entry, 'media_content'):
                            images = [m['url'] for m in entry.media_content 
                                    if m.get('type', '').startswith('image/')]
                            if images:
                                image_url = max(images, key=lambda x: int(x.get('width', 0)))
                        elif hasattr(entry, 'media_thumbnail'):
                            image_url = entry.media_thumbnail[0]['url']
                        
                        podcast = {
                            'title': entry.get('title', 'Untitled Episode'),
                            'description': BeautifulSoup(entry.get('description', ''), 'html.parser').get_text()[:500],
                            'published_date': entry.get('published', ''),
                            'duration': entry.get('itunes_duration', ''),
                            'audio_url': audio_url,
                            'image_url': image_url,
                            'source_url': entry.get('link', ''),
                            'author': entry.get('author', feed.feed.get('title', 'Unknown')),
                            'category': feed_info['category'],
                            'language': entry.get('language', 'en'),
                            'source_type': 'rss'
                        }
                        all_podcasts.append(podcast)
                        logging.info(f"Added podcast: {podcast['title']} from {feed_info['url']}")
                    except Exception as entry_error:
                        logging.error(f"Error processing entry from {feed_info['url']}: {str(entry_error)}")
                        continue
            except Exception as feed_error:
                logging.error(f"Error fetching feed {feed_info['url']}: {str(feed_error)}")
                continue
        
        # Fetch from YouTube (if API key is available)
        youtube_api_key = os.getenv('YOUTUBE_API_KEY')
        if youtube_api_key:
            for source in youtube_sources:
                try:
                    channel_id = source.split('/')[-2]
                    url = f"https://www.googleapis.com/youtube/v3/search"
                    params = {
                        'key': youtube_api_key,
                        'channelId': channel_id,
                        'part': 'snippet',
                        'order': 'date',
                        'maxResults': 5,
                        'type': 'video'
                    }
                    response = requests.get(url, params=params)
                    if response.status_code == 200:
                        data = response.json()
                        for item in data.get('items', []):
                            video = {
                                'title': item['snippet']['title'],
                                'description': item['snippet']['description'][:500],
                                'published_date': item['snippet']['publishedAt'],
                                'image_url': item['snippet']['thumbnails']['high']['url'],
                                'source_url': f"https://www.youtube.com/watch?v={item['id']['videoId']}",
                                'author': item['snippet']['channelTitle'],
                                'category': 'Anti-Doping Education',
                                'language': 'en',
                                'source_type': 'youtube'
                            }
                            all_podcasts.append(video)
                except Exception as yt_error:
                    logging.error(f"Error fetching YouTube content from {source}: {str(yt_error)}")
                    continue
        
        # Sort all podcasts by published date
        all_podcasts.sort(key=lambda x: x.get('published_date', ''), reverse=True)
        return all_podcasts
        
    except Exception as e:
        logging.error(f"Error in fetch_sports_podcasts: {str(e)}")
        return []

if __name__ == "__main__":
    app.run(debug=True)