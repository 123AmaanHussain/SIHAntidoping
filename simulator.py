import random
import time
from datetime import datetime, timedelta, timezone
import threading
from flask_socketio import SocketIO

class FitnessSimulator:
    def __init__(self, socketio: SocketIO):
        self.socketio = socketio
        self.running = False
        self.thread = None
        self.athlete_data = {}  # Store simulated data for each athlete
        
        # Define activity patterns
        self.activity_patterns = {
            'resting': {'hr_range': (60, 75), 'steps_per_min': (0, 5)},
            'walking': {'hr_range': (75, 100), 'steps_per_min': (85, 110)},
            'running': {'hr_range': (140, 180), 'steps_per_min': (150, 180)},
            'workout': {'hr_range': (120, 160), 'steps_per_min': (30, 60)}
        }
        
        # Define risk scenarios
        self.risk_scenarios = [
            {
                'name': 'High Intensity Training',
                'condition': lambda hr, hrv: hr > 170 and hrv < 50,
                'message': 'Extended high-intensity activity detected. Monitor recovery.',
                'level': 'medium'
            },
            {
                'name': 'Overtraining Risk',
                'condition': lambda hr, hrv: hr > 150 and hrv < 40,
                'message': 'Potential overtraining detected. Rest recommended.',
                'level': 'high'
            },
            {
                'name': 'Poor Recovery',
                'condition': lambda hr, hrv: hr > 80 and hrv < 30,
                'message': 'Poor recovery indicators. Consider rest day.',
                'level': 'high'
            }
        ]
        
    def start_simulation(self, athlete_id):
        """Start simulation for a specific athlete"""
        if athlete_id not in self.athlete_data:
            self.athlete_data[athlete_id] = {
                'heart_rate': 70,
                'steps': 0,
                'sleep_hours': 0,
                'hrv': 65,
                'last_update': datetime.now(timezone.utc),
                'sleep_start': None,
                'is_sleeping': False,
                'current_activity': 'resting',
                'activity_duration': 0,
                'daily_workout_done': False,
                'calories_burned': 0,
                'stress_level': 50,  # 0-100 scale
                'recovery_score': 85,  # 0-100 scale
                'hydration_level': 100,  # 0-100 scale
                'last_meal_time': datetime.now(timezone.utc) - timedelta(hours=2),
                'supplements_taken': []
            }
        
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._simulation_loop)
            self.thread.daemon = True
            self.thread.start()
            print(f"Started simulation for athlete {athlete_id}")
    
    def _simulate_activity_change(self, data):
        """Simulate random activity pattern changes"""
        # Random activity changes for demo
        if random.random() < 0.1:  # 10% chance to change activity
            activities = list(self.activity_patterns.keys())
            return random.choice(activities)
        return data['current_activity']

    def _simulate_heart_rate(self, current_hr, activity, stress_level):
        """Simulate heart rate with random spikes"""
        hr_range = self.activity_patterns[activity]['hr_range']
        target_hr = random.uniform(*hr_range)
        
        # Random spikes for demo
        if random.random() < 0.05:  # 5% chance of spike
            target_hr += random.uniform(20, 40)
        
        # Add stress influence
        stress_factor = stress_level / 100 * 20
        target_hr += stress_factor
        
        # Gradual change towards target
        hr_change = (target_hr - current_hr) * 0.2  # Faster changes for demo
        hr_change += random.uniform(-5, 5)  # More variation
        
        new_hr = current_hr + hr_change
        return max(min(new_hr, 200), 45)

    def _simulate_steps(self, current_steps, activity, duration):
        """Simulate step count based on activity"""
        steps_range = self.activity_patterns[activity]['steps_per_min']
        steps_per_min = random.uniform(*steps_range)
        new_steps = int(steps_per_min * (duration / 60))
        return current_steps + new_steps

    def _simulate_sleep(self, data):
        """Simulate realistic sleep patterns"""
        current_time = datetime.now(timezone.utc)
        hour = current_time.hour

        if not data['is_sleeping']:
            # Chance to start sleeping during night hours (22:00 - 06:00)
            if hour >= 22 or hour < 6:
                if random.random() < 0.3:  # 30% chance to fall asleep
                    data['is_sleeping'] = True
                    data['sleep_start'] = current_time
                    print(f"Started sleeping at {current_time}")
        else:
            # Higher chance to wake up during day hours
            if 6 <= hour < 22:
                if random.random() < 0.4:  # 40% chance to wake up
                    data['is_sleeping'] = False
                    if data['sleep_start']:
                        sleep_duration = (current_time - data['sleep_start']).total_seconds() / 3600
                        if sleep_duration >= 0.5:  # Only count sleep if it was at least 30 minutes
                            data['sleep_hours'] = round(sleep_duration, 1)
                        data['sleep_start'] = None
                        print(f"Woke up after {sleep_duration:.1f} hours")
            else:
                if random.random() < 0.05:  # Small chance to wake during night
                    data['is_sleeping'] = False
                    if data['sleep_start']:
                        sleep_duration = (current_time - data['sleep_start']).total_seconds() / 3600
                        if sleep_duration >= 0.5:
                            data['sleep_hours'] = round(sleep_duration, 1)
                        data['sleep_start'] = None
                        print(f"Woke up during night after {sleep_duration:.1f} hours")

        return data['is_sleeping']

    def _simulate_stress_and_recovery(self, data, activity):
        """Simulate more dynamic stress and recovery patterns"""
        # Random stress events
        if random.random() < 0.1:  # 10% chance of stress event
            data['stress_level'] = min(data['stress_level'] + random.uniform(10, 30), 100)
            data['recovery_score'] = max(data['recovery_score'] - random.uniform(5, 15), 0)
        else:
            # Normal stress/recovery simulation
            if activity in ['running', 'workout']:
                data['stress_level'] = min(data['stress_level'] + random.uniform(1, 5), 100)
                data['recovery_score'] = max(data['recovery_score'] - random.uniform(0.5, 2), 0)
            else:
                data['stress_level'] = max(data['stress_level'] - random.uniform(0.5, 2), 0)
                data['recovery_score'] = min(data['recovery_score'] + random.uniform(0.3, 1), 100)

    def _simulate_hydration(self, data):
        """Simulate hydration levels"""
        # Decrease hydration over time
        data['hydration_level'] = max(data['hydration_level'] - random.uniform(0.1, 0.3), 0)
        
        # Automatic hydration during meals
        current_time = datetime.now(timezone.utc)
        time_since_meal = (current_time - data['last_meal_time']).total_seconds() / 3600
        
        if time_since_meal > 3:  # Simulate meal/drink every 3 hours
            data['hydration_level'] = min(data['hydration_level'] + random.uniform(20, 40), 100)
            data['last_meal_time'] = current_time

    def _simulate_hrv(self, current_hrv, is_sleeping, stress_level, recovery_score):
        """Simulate Heart Rate Variability based on multiple factors"""
        if is_sleeping:
            target_hrv = 75 * (recovery_score / 100)  # Higher during sleep, influenced by recovery
        else:
            target_hrv = 65 * ((100 - stress_level) / 100)  # Lower when stressed
        
        # Gradual change towards target
        change = (target_hrv - current_hrv) * 0.1
        change += random.uniform(-2, 2)  # Add some random variation
        
        new_hrv = current_hrv + change
        return max(min(new_hrv, 100), 20)

    def _check_risk_scenarios(self, data):
        """Generate random risk alerts for demo"""
        # Check defined risk scenarios
        for scenario in self.risk_scenarios:
            if scenario['condition'](data['heart_rate'], data['hrv']):
                self.socketio.emit('risk_alert', {
                    'type': scenario['name'],
                    'message': scenario['message'],
                    'level': scenario['level'],
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })

        # Random additional risk events
        if random.random() < 0.05:  # 5% chance of additional risk event
            risk_type = random.choice([
                {
                    'name': 'Sudden HR Spike',
                    'message': 'Unusual heart rate pattern detected.',
                    'level': 'high'
                },
                {
                    'name': 'Extended High Intensity',
                    'message': 'Prolonged high-intensity activity detected.',
                    'level': 'medium'
                },
                {
                    'name': 'Recovery Warning',
                    'message': 'Poor recovery indicators detected.',
                    'level': 'high'
                },
                {
                    'name': 'Dehydration Risk',
                    'message': 'Low hydration levels detected.',
                    'level': 'medium'
                },
                {
                    'name': 'Stress Alert',
                    'message': 'High stress levels detected.',
                    'level': 'high'
                }
            ])
            
            self.socketio.emit('risk_alert', {
                'type': risk_type['name'],
                'message': risk_type['message'],
                'level': risk_type['level'],
                'timestamp': datetime.now(timezone.utc).isoformat()
            })

    def _simulation_loop(self):
        """Main simulation loop with random events"""
        print("Starting simulation loop")
        while self.running:
            for athlete_id in list(self.athlete_data.keys()):
                data = self.athlete_data[athlete_id]

                current_time = datetime.now(timezone.utc)
                time_diff = (current_time - data['last_update']).total_seconds()
                data['last_update'] = current_time

                # Update activity
                data['current_activity'] = self._simulate_activity_change(data)
                data['activity_duration'] += time_diff

                # Update metrics
                data['heart_rate'] = self._simulate_heart_rate(data['heart_rate'], data['current_activity'], data['stress_level'])
                data['steps'] = self._simulate_steps(data['steps'], data['current_activity'], time_diff)
                data['is_sleeping'] = self._simulate_sleep(data)
                
                # Update advanced metrics
                self._simulate_stress_and_recovery(data, data['current_activity'])
                self._simulate_hydration(data)
                data['hrv'] = self._simulate_hrv(data['hrv'], data['is_sleeping'], data['stress_level'], data['recovery_score'])

                # Check for risks
                self._check_risk_scenarios(data)

                # Emit updated data
                self.socketio.emit('metrics_update', {
                    'heart_rate': round(data['heart_rate'], 1),
                    'steps': data['steps'],
                    'sleep_hours': data['sleep_hours'],
                    'hrv': round(data['hrv'], 1),
                    'activity': data['current_activity'],
                    'stress_level': round(data['stress_level'], 1),
                    'recovery_score': round(data['recovery_score'], 1),
                    'hydration_level': round(data['hydration_level'], 1),
                    'is_sleeping': data['is_sleeping'],
                    'timestamp': current_time.isoformat()
                })

            time.sleep(1)  # Update every second

    def get_current_metrics(self, athlete_id):
        """Get current metrics for an athlete"""
        if athlete_id in self.athlete_data:
            data = self.athlete_data[athlete_id]
            return {
                'heart_rate': round(data['heart_rate'], 1),
                'steps': data['steps'],
                'sleep_hours': data['sleep_hours'],
                'hrv': round(data['hrv'], 1),
                'activity': data['current_activity'],
                'stress_level': round(data['stress_level'], 1),
                'recovery_score': round(data['recovery_score'], 1),
                'hydration_level': round(data['hydration_level'], 1),
                'is_sleeping': data['is_sleeping'],
                'timestamp': data['last_update'].isoformat()
            }
        return None
