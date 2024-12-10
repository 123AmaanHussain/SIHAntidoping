# Anti-Doping Education Platform

A comprehensive web platform for anti-doping education, featuring real-time athlete monitoring, educational resources, and interactive tools.

## Features

### 1. Digital Twin Athlete Monitoring
- Real-time heart rate monitoring with graphical visualization
- Activity tracking (steps, sleep, etc.)
- Health metrics monitoring (HRV, stress levels, recovery score)
- Risk alerts and notifications
- Hydration level tracking

### 2. Educational Resources
- Anti-Doping Wiki with categorized information
- Interactive podcasts on anti-doping topics
- AI-powered coach for personalized guidance
- Smart label scanning for supplement verification

### 3. Interactive Tools
- Calories calculator for athletes
- Gamified quizzes for learning
- Certificate generation for completed courses
- Real-time chat with AI coach

## Technology Stack

### Backend
- Python 3.8+
- Flask web framework
- Flask-SocketIO for real-time communication
- SQLAlchemy for database management
- MongoDB for quiz and podcast storage

### Frontend
- HTML5, CSS3, JavaScript
- Chart.js for real-time data visualization
- Bootstrap 5 for responsive design
- Socket.IO client for real-time updates

### APIs and Services
- News API for latest anti-doping news
- Spotify API for podcast integration
- YouTube API for educational content
- Google's Generative AI for AI coach

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/antidoping-platform.git
cd antidoping-platform
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
Create a `.env` file with the following:
```env
FLASK_SECRET_KEY=your_secret_key
MONGO_URI=your_mongodb_uri
GOOGLE_API_KEY=your_google_api_key
YOUTUBE_API_KEY=your_youtube_api_key
NEWS_API_KEY=your_news_api_key
```

5. Initialize the database:
```bash
python
>>> from app import db
>>> db.create_all()
>>> exit()
```

6. Run the application:
```bash
python app.py
```

The application will be available at `http://localhost:5000`

## Project Structure

```
antidoping-platform/
├── app.py                 # Main Flask application
├── simulator.py           # Digital twin simulator
├── requirements.txt       # Python dependencies
├── static/               # Static files (CSS, JS, images)
├── templates/            # HTML templates
├── .env                  # Environment variables
└── README.md            # Project documentation
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- World Anti-Doping Agency (WADA) for anti-doping guidelines
- Various open-source libraries and frameworks used in this project
- Contributors and maintainers