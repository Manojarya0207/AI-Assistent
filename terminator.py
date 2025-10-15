# terminator_merged.py
import os
import sys
import time
import queue
import threading
import subprocess
import datetime
import webbrowser
import urllib.parse
import tkinter as tk
from tkinter import scrolledtext
from dotenv import load_dotenv
from PIL import Image, ImageTk, ImageGrab, ImageDraw
import numpy as np

# Added imports for new features
import spacy
import dateparser
try:
    import pyautogui
except ImportError:
    pyautogui = None
import requests

# New import for image generation
try:
    import replicate
except ImportError:
    replicate = None
# New import for email sending
import smtplib
from email.message import EmailMessage

# audio & speech
try:
    import pyaudio
except ImportError:
    pyaudio = None
try:
    import pvporcupine
except ImportError:
    pvporcupine = None
import speech_recognition as sr
import pyttsx3
try:
    import pygame
except ImportError:
    pygame = None

# optional utilities
try:
    import psutil
except ImportError:
    psutil = None

try:
    import requests
except ImportError:
    requests = None

try:
    import wikipedia
except ImportError:
    wikipedia = None

try:
    import pyperclip
except ImportError:
    pyperclip = None

# optional Windows volume control via pycaw
_pycaw_ok = False
try:
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    import comtypes
    _pycaw_ok = True
except ImportError:
    _pycaw_ok = False

# -------------------------
# Configuration
# -------------------------
load_dotenv()
PICOVOICE_ACCESS_KEY = os.getenv("PICOVOICE_ACCESS_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
WAKE_KEYWORDS = ["terminator"]

# Email Configuration
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")

MUSIC_DIR = os.getenv("MUSIC_DIR") or os.path.expanduser(r"~\\Music")
AUDIO_EXTS = (".mp3", ".wav", ".ogg")

LOGO_FILENAMES = ["terminator-logoo.png", "C:/Users/jeeva/OneDrive/Desktop/terminator/terminator-logoo.png"]

NOTES_FILE = os.path.expanduser("~/terminator_notes.txt")
SCREENSHOT_DIR = os.path.join(os.path.expanduser("~"), "Desktop")
if not os.path.exists(SCREENSHOT_DIR):
    SCREENSHOT_DIR = os.path.expanduser("~")

# -------------------------
# Global State and Memory
# -------------------------
user_data = {"name": "sir", "last_command_context": None}
reminders_queue = queue.Queue()

# -------------------------
# NLP Initialization
# -------------------------
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    print("SpaCy model 'en_core_web_sm' not found. Downloading...")
    subprocess.run([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])
    nlp = spacy.load("en_core_web_sm")

# -------------------------
# GUI
# -------------------------
class terminatorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("T.E.R.M.I.N.A.T.O.R")
        self.root.geometry("720x760")
        self.root.configure(bg='#071226')

        logo_loaded = False
        for fname in LOGO_FILENAMES:
            try:
                if os.path.exists(fname):
                    img = Image.open(fname)
                    img = img.resize((120, 120), Image.LANCZOS)
                    self.logo_img = ImageTk.PhotoImage(img)
                    tk.Label(root, image=self.logo_img, bg='#071226').pack(pady=8)
                    logo_loaded = True
                    break
            except Exception:
                continue
        if not logo_loaded:
            fallback = Image.new("RGB", (120, 120), (7, 18, 38))
            draw = ImageDraw.Draw(fallback)
            draw.text((36, 44), "J", fill=(0, 255, 255))
            self.logo_img = ImageTk.PhotoImage(fallback)
            tk.Label(root, image=self.logo_img, bg='#071226').pack(pady=8)

        self.status_label = tk.Label(root, text="Status: Initializing...", fg="cyan", bg="#071226", font=("Segoe UI", 12))

        self.status_label.pack(pady=6)

        self.log_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, bg="#0b1a24", fg="#e6f1f5", font=("Consolas", 11), height=36, width=92)

        self.log_area.pack(padx=8, pady=8, fill=tk.BOTH, expand=True)

    def update_status(self, text):
        try:
            self.status_label.config(text=f"Status: {text}")
            self.root.update_idletasks()
        except Exception:
            pass

    def log(self, message, sender="SYSTEM"):
        try:
            t = datetime.datetime.now().strftime("%H:%M:%S")
            line = f"[{t}] {sender}: {message}\n"
            self.log_area.insert(tk.END, line)
            self.log_area.see(tk.END)
            self.root.update_idletasks()
        except Exception:
            print(f"{sender}: {message}")

# -------------------------
# TTS
# -------------------------
engine = pyttsx3.init()
engine.setProperty("rate", 170)
engine.setProperty("volume", 1.0)
_speaking_lock = threading.Lock()

def speak(text):
    with _speaking_lock:
        try:
            gui.update_status("Speaking...")
        except Exception:
            pass
        try:
            gui.log(text, "terminator")
        except Exception:
            pass
        try:
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            try:
                gui.log(f"TTS error: {e}", "ERROR")
            except Exception:
                print("TTS error:", e)
        finally:
            time.sleep(0.35)
            try:
                gui.update_status("Idle")
            except Exception:
                pass

# -------------------------
# App scanning & opening
# -------------------------
installed_apps = {}

def normalize_name(name: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else " " for ch in name).strip()

def scan_installed_apps():
    installed_apps.clear()
    try:
        gui.log("Scanning installed apps...", "SYSTEM")
    except NameError:
        print("Scanning installed apps...")
        
    paths = []
    progdata = os.environ.get("PROGRAMDATA")
    appdata = os.environ.get("APPDATA")
    if progdata:
        paths.append(os.path.join(progdata, r"Microsoft\\Windows\\Start Menu\\Programs"))
    if appdata:
        paths.append(os.path.join(appdata, r"Microsoft\\Windows\\Start Menu\\Programs"))
    pf = os.environ.get("ProgramFiles")
    pf_x86 = os.environ.get("ProgramFiles(x86)")
    if pf:
        paths.append(pf)
    if pf_x86:
        paths.append(pf_x86)
    special = [
        os.path.expanduser(r"~\\AppData\\Local\\Programs"),
        os.path.expanduser(r"~\\AppData\\Local\\Microsoft\\WindowsApps")
    ]
    paths.extend([p for p in special if p and os.path.exists(p)])
    visited = set()
    for base in paths:
        if not base or not os.path.exists(base):
            continue
        for root_dir, dirs, files in os.walk(base):
            for file in files:
                if file.lower().endswith((".lnk", ".exe")):
                    full = os.path.join(root_dir, file)
                    key = normalize_name(os.path.splitext(file)[0])
                    if key not in visited:
                        installed_apps[key] = full
                        visited.add(key)
    try:
        gui.log(f"App scan complete. Found {len(installed_apps)} apps.", "SYSTEM")
    except NameError:
        print(f"App scan complete. Found {len(installed_apps)} apps.")

def find_best_app_match(query: str):
    q = normalize_name(query)
    if not q:
        return None
    for name, path in installed_apps.items():
        if q == name or q in name or name in q:
            return path
    q_tokens = set(q.split())
    best = (None, 0)
    for name, path in installed_apps.items():
        name_tokens = set(name.split())
        score = len(q_tokens & name_tokens)
        if score > best[1]:
            best = (path, score)
    if best[1] > 0:
        return best[0]
    return None

def open_application_by_name(app_query: str) -> bool:
    path = find_best_app_match(app_query)
    if path:
        try:
            gui.log(f"Opening: {path}", "SYSTEM")
            try:
                os.startfile(path)
                return True
            except Exception:
                subprocess.Popen([path], shell=False)
                return True
        except Exception as e:
            gui.log(f"Failed to open app: {e}", "ERROR")
            return False
    return False

def close_application_by_name(app_query: str) -> bool:
    """
    Finds and closes a process by its name using taskkill on Windows.
    This works better than a keyboard shortcut.
    """
    normalized_query = normalize_name(app_query)
    found_match = False
    try:
        if psutil is None:
            gui.log("psutil is not installed. Cannot close application by name.", "ERROR")
            return False
        for proc in psutil.process_iter(['name']):
            if normalized_query in normalize_name(proc.info['name']):
                gui.log(f"Found process to kill: {proc.info['name']}", "SYSTEM")
                subprocess.run(['taskkill', '/f', '/im', proc.info['name']], check=True)
                gui.log(f"Closed {proc.info['name']}", "SYSTEM")
                found_match = True
                break
        if not found_match:
            gui.log(f"No running process found for '{app_query}'", "SYSTEM")
            return False
        return True
    except Exception as e:
        gui.log(f"Failed to close application: {e}", "ERROR")
        return False
        
# -------------------------
# Local music with pygame
# -------------------------
if pygame:
    try:
        pygame.mixer.init()
    except Exception:
        pass
else:
    print("Pygame is not installed. Local music playback will be unavailable.")

current_music_path = None
music_paused = False
local_music_index = {}

def index_local_music(root_dir=MUSIC_DIR):
    music_index = {}
    if not os.path.exists(root_dir):
        gui.log(f"Music folder not found: {root_dir}", "SYSTEM")
        return music_index
    for root_dir, _, files in os.walk(root_dir):
        for f in files:
            if f.lower().endswith(AUDIO_EXTS):
                key = normalize_name(os.path.splitext(f)[0])
                if key not in music_index:
                    music_index[key] = os.path.join(root_dir, f)
    gui.log(f"Indexed {len(music_index)} local tracks.", "SYSTEM")
    return music_index

def find_local_track(query: str):
    q = normalize_name(query)
    if not q:
        return None
    for name, path in local_music_index.items():
        if q == name or q in name or name in q:
            return path
    q_tokens = set(q.split())
    best = (None, 0)
    for name, path in local_music_index.items():
        name_tokens = set(name.split())
        score = len(q_tokens & name_tokens)
        if score > best[1]:
            best = (path, score)
    if best[1] > 0:
        return best[0]
    return None

def play_local_music(path: str):
    if pygame is None:
        speak("Pygame is not installed. I cannot play local music.")
        return False
    global current_music_path, music_paused
    try:
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
    except Exception:
        pass
    try:
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        current_music_path = path
        music_paused = False
        gui.log(f"Playing local track: {path}", "SYSTEM")
        speak(f"Playing {os.path.basename(path)} from local music.")
        return True
    except Exception as e:
        gui.log(f"Playback error: {e}", "ERROR")
        speak("I couldn't play that local file.")
        return False

def stop_music():
    if pygame is None:
        return
    global current_music_path, music_paused
    try:
        pygame.mixer.music.stop()
        current_music_path = None
        music_paused = False
        gui.log("Music stopped.", "SYSTEM")
        speak("Stopped music.")
    except Exception as e:
        gui.log(f"Stop error: {e}", "ERROR")

def pause_music():
    if pygame is None:
        return
    global music_paused
    try:
        pygame.mixer.music.pause()
        music_paused = True
        gui.log("Music paused.", "SYSTEM")
        speak("Paused.")
    except Exception as e:
        gui.log(f"Pause error: {e}", "ERROR")

def resume_music():
    if pygame is None:
        return
    global music_paused
    try:
        pygame.mixer.music.unpause()
        music_paused = False
        gui.log("Music resumed.", "SYSTEM")
        speak("Resuming music.")
    except Exception as e:
        gui.log(f"Resume error: {e}", "ERROR")

# -------------------------
# Speech recognition (commands)
# -------------------------
recognizer = sr.Recognizer()

def listen_for_command(timeout=6, phrase_time_limit=8):
    if _speaking_lock.locked():
        time.sleep(0.1)
    with sr.Microphone() as source:
        gui.update_status("Listening for command...")
        gui.log("Listening for command...", "SYSTEM")
        recognizer.adjust_for_ambient_noise(source, duration=0.4)
        try:
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            text = recognizer.recognize_google(audio)
            gui.log(text, "You")
            return text.lower()
        except sr.WaitTimeoutError:
            gui.log("No speech detected (timeout).", "SYSTEM")
            return None
        except sr.UnknownValueError:
            gui.log("Couldn't understand audio.", "SYSTEM")
            speak("I didn't understand. Please say that again.")
            return None
        except sr.RequestError as e:
            gui.log(f"Speech service error: {e}", "ERROR")
            speak("I couldn't reach the speech service.")
            return None

# -------------------------
# Porcupine wake-word thread
# -------------------------
wake_queue = queue.Queue()

def porcupine_worker():
    if pvporcupine is None or pyaudio is None:
        gui.log("Porcupine or PyAudio not installed; wake-word disabled.", "SYSTEM")
        return
    try:
        if PICOVOICE_ACCESS_KEY:
            pv = pvporcupine.create(access_key=PICOVOICE_ACCESS_KEY, keywords=WAKE_KEYWORDS)
        else:
            pv = pvporcupine.create(keywords=WAKE_KEYWORDS)
    except Exception as e:
        gui.log(f"Porcupine init error: {e}", "ERROR")
        speak("Wake word engine failed. Wake word disabled.")
        return

    pa = pyaudio.PyAudio()
    try:
        stream = pa.open(
            rate=pv.sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=pv.frame_length
        )
    except Exception as e:
        gui.log(f"Microphone open error: {e}", "ERROR")
        speak("Could not open microphone for wake word detection.")
        pv.delete()
        return

    gui.log("Wake-word listener started.", "SYSTEM")
    gui.update_status("Listening for wake word 'terminator'...")
    while True:
        try:
            pcm = stream.read(pv.frame_length, exception_on_overflow=False)
            pcm = np.frombuffer(pcm, dtype=np.int16)
            keyword_index = pv.process(pcm)
            if keyword_index >= 0:
                if _speaking_lock.locked():
                    time.sleep(0.4)
                wake_queue.put(True)
        except Exception as e:
            gui.log(f"Porcupine loop error: {e}", "ERROR")
            time.sleep(0.5)

# -------------------------
# New Feature Workers
# -------------------------
def reminder_worker():
    """Worker thread to handle reminders and alarms."""
    while True:
        try:
            timestamp, message = reminders_queue.get(timeout=1)
            now = datetime.datetime.now()
            if now >= timestamp:
                speak(f"Reminder: {message}")
                gui.log(f"REMINDER: {message}", "REMINDER")
            else:
                reminders_queue.put((timestamp, message))
                time.sleep(1)
        except queue.Empty:
            time.sleep(1)
        except Exception as e:
            gui.log(f"Reminder worker error: {e}", "ERROR")
            time.sleep(1)

# -------------------------
# New image generation feature
# -------------------------
def generate_image(prompt: str):
    if replicate is None:
        speak("Image generation is not available. Please install the 'replicate' library.")
        gui.log("Image generation library 'replicate' not found.", "ERROR")
        return
    if not REPLICATE_API_TOKEN:
        speak("Image generation is not configured. Please add your Replicate API token.")
        return
    
    gui.log(f"Generating image for prompt: {prompt}", "SYSTEM")
    speak(f"Generating an image of {prompt}. This may take a moment.")
    
    try:
        model = "stability-ai/sdxl"
        output = replicate.run(
            model,
            input={"prompt": prompt}
        )
        if output and output[0]:
            image_url = output[0]
            gui.log(f"Generated image URL: {image_url}", "SYSTEM")
            webbrowser.open(image_url)
            speak("I have generated and opened the image for you.")
        else:
            speak("I couldn't generate an image with that prompt.")
    except Exception as e:
        gui.log(f"Image generation error: {e}", "ERROR")
        speak("I encountered an error while trying to generate the image.")

# -------------------------
# New email feature
# -------------------------
def send_email_task(recipient, subject, body):
    if not EMAIL_ADDRESS or not EMAIL_APP_PASSWORD:
        speak("Email feature is not configured. Please set up your email address and app password in the environment variables.")
        gui.log("Email not configured. Check environment variables.", "ERROR")
        return False
    
    try:
        msg = EmailMessage()
        msg.set_content(body)
        msg['Subject'] = subject
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = recipient

        gui.log("Attempting to send email...", "SYSTEM")
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
            smtp.send_message(msg)
        
        gui.log(f"Email sent successfully to {recipient}.", "SYSTEM")
        speak(f"Email sent successfully to {recipient}.")
        return True
    except Exception as e:
        gui.log(f"Failed to send email: {e}", "ERROR")
        speak("I encountered an error while trying to send the email.")
        return False

# -------------------------
# WhatsApp features (Desktop App Automation)
# -------------------------
def send_whatsapp_message_desktop(contact_name: str, message: str):
    """
    Automates sending a WhatsApp message via the desktop application.
    This function relies on screen coordinates and UI elements.
    It may fail if the WhatsApp app UI or screen resolution changes.
    """
    if pyautogui is None:
        speak("WhatsApp automation is not available. Please install the 'pyautogui' library.")
        gui.log("PyAutoGUI not found.", "ERROR")
        return
    
    try:
        gui.log("Starting WhatsApp automation...", "SYSTEM")
        speak(f"I will try to send a message to {contact_name}.")
        
        # Open the WhatsApp desktop app
        subprocess.Popen(['C:\\Program Files\\WhatsApp\\WhatsApp.exe']) # Adjust path if needed
        time.sleep(5)  # Wait for the app to open

        # Locate and click the search bar (top-left corner)
        # This is a generic approach. A more robust way would be to use image recognition.
        pyautogui.click(x=150, y=100) # Example coordinates for a search bar

        # Type the contact name and press Enter
        pyautogui.write(contact_name)
        time.sleep(2)
        pyautogui.press('enter')
        time.sleep(2)

        # Locate and click the message input field (bottom)
        pyautogui.click(x=500, y=950) # Example coordinates for message box

        # Type the message and press Enter to send
        pyautogui.write(message)
        pyautogui.press('enter')
        
        gui.log("WhatsApp message sent.", "SYSTEM")
        speak("I have sent the WhatsApp message.")

    except Exception as e:
        gui.log(f"WhatsApp automation failed: {e}", "ERROR")
        speak("I couldn't send the WhatsApp message. Please check if the app is open and the coordinates are correct.")

# -------------------------
# Helper features
# -------------------------
JOKES = [
    "Why did the programmer quit his job? Because he didn't get arrays.",
    "Why do programmers prefer dark mode? Because light attracts bugs!",
    "I told my computer I needed a break, and it said: 'No problem — I'll go to sleep.'"
]

def tell_joke():
    import random
    joke = random.choice(JOKES)
    speak(joke)

def save_note(text):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(NOTES_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {text}\n")
        gui.log("Note saved.", "SYSTEM")
        speak("Note saved.")
    except Exception as e:
        gui.log(f"Failed to save note: {e}", "ERROR")
        speak("I couldn't save the note.")

def take_screenshot():
    try:
        filename = f"Screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        path = os.path.join(SCREENSHOT_DIR, filename)
        img = ImageGrab.grab()
        img.save(path)
        gui.log(f"Screenshot saved: {path}", "SYSTEM")
        speak(f"I saved the screenshot to your desktop as {filename}.")
    except Exception as e:
        gui.log(f"Screenshot error: {e}", "ERROR")
        speak("I couldn't take a screenshot.")

def read_clipboard():
    if pyperclip is None:
        speak("Clipboard support is not available. Install the pyperclip package.")
        return
    try:
        text = pyperclip.paste()
        if not text:
            speak("Your clipboard is empty.")
            return
        gui.log("Clipboard content read.", "SYSTEM")
        speak(f"Clipboard says: {text}")
    except Exception as e:
        gui.log(f"Clipboard error: {e}", "ERROR")
        speak("I couldn't read the clipboard.")

def open_website_shortcut(name):
    name = name.lower().strip()
    mapping = {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "facebook": "https://www.facebook.com",
        "twitter": "https://twitter.com",
        "github": "https://github.com",
        "gmail": "https://mail.google.com",
        "photos": "https://photos.google.com",
        "gpt": "https://www.chatgpt.com"
    }
    url = mapping.get(name) or (name if name.startswith("http") else f"https://{name}.com")
    gui.log(f"Opening website: {url}", "SYSTEM")
    webbrowser.open(url)
    speak(f"Opening {name}")

def get_system_info():
    if psutil is None:
        speak("System info library is not available. Install psutil.")
        return
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    mem_percent = mem.percent
    speak(f"CPU usage is {int(cpu)} percent. Memory usage is {int(mem_percent)} percent.")
    try:
        battery = psutil.sensors_battery()
        if battery:
            plugged = "charging" if battery.power_plugged else "not charging"
            speak(f"Battery at {int(battery.percent)} percent and {plugged}.")
        else:
            gui.log("No battery info available.", "SYSTEM")
    except Exception:
        pass

def get_cpu_usage():
    if psutil is None:
        speak("Install psutil for CPU info.")
        return
    cpu = psutil.cpu_percent(interval=1)
    speak(f"CPU usage is {int(cpu)} percent.")

def get_ram_usage():
    if psutil is None:
        speak("Install psutil for RAM info.")
        return
    mem = psutil.virtual_memory()
    speak(f"Memory usage is {int(mem.percent)} percent.")

def get_battery_status():
    if psutil is None:
        speak("Install psutil for battery info.")
        return
    try:
        battery = psutil.sensors_battery()
        if battery:
            plugged = "charging" if battery.power_plugged else "not charging"
            speak(f"Battery at {int(battery.percent)} percent and {plugged}.")
        else:
            gui.log("No battery info available.", "SYSTEM")
            speak("I couldn't get the battery information.")
    except Exception as e:
        gui.log(f"Battery status error: {e}", "ERROR")
        speak("I couldn't get the battery information.")

def get_news_headlines():
    if not NEWS_API_KEY:
        speak("News feature is not configured. Please add your News API key.")
        return
    if requests is None:
        speak("Please install the requests package for news queries.")
        return
    url = f"https://newsapi.org/v2/top-headlines?country=us&apiKey={NEWS_API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        articles = data.get("articles", [])
        if articles:
            speak("Here are the top headlines.")
            for article in articles[:3]:
                speak(article["title"])
        else:
            speak("I couldn't fetch the news right now.")
    except Exception as e:
        gui.log(f"News API error: {e}", "ERROR")
        speak("I had trouble fetching the news.")

def get_weather_for(city: str):
    if not OPENWEATHER_API_KEY:
        speak("Weather feature is not configured. Set the OpenWeather API key in the environment.")
        return
    if requests is None:
        speak("Please install the requests package for weather queries.")
        return
    city_q = urllib.parse.quote_plus(city)
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city_q}&appid={OPENWEATHER_API_KEY}&units=metric"
    try:
        r = requests.get(url, timeout=8)
        if r.status_code != 200:
            speak("I couldn't fetch weather for that location.")
            return
        data = r.json()
        desc = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        hum = data["main"]["humidity"]
        speak(f"The weather in {city} is {desc} with temperature {int(temp)} degrees Celsius and humidity {hum} percent.")
    except Exception as e:
        gui.log(f"Weather error: {e}", "ERROR")
        speak("I couldn't get the weather right now.")

# -------------------------
# Wikipedia search
# -------------------------
def wiki_summary(query: str):
    if wikipedia is None:
        speak("Wikipedia support not available. Install the wikipedia package.")
        return
    try:
        summary = wikipedia.summary(query, sentences=2, auto_suggest=True, redirect=True)
        speak(summary)
    except wikipedia.exceptions.DisambiguationError as e:
        speak("There are multiple results. Please be more specific.")
    except Exception as e:
        gui.log(f"Wikipedia error: {e}", "ERROR")
        speak("I couldn't find that on Wikipedia.")

# -------------------------
# Volume control (pycaw on Windows) with fallbacks
# -------------------------
def _get_default_volume_interface():
    if not _pycaw_ok:
        return None
    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    volume = comtypes.cast(interface, comtypes.POINTER(IAudioEndpointVolume))
    return volume

_volume_interface = None
if _pycaw_ok:
    try:
        _volume_interface = _get_default_volume_interface()
    except Exception:
        _volume_interface = None

def volume_up():
    if _volume_interface is None:
        speak("Volume control is not available on this system.")
        return
    try:
        current = _volume_interface.GetMasterVolumeLevelScalar()
        new = min(1.0, current + 0.05)
        _volume_interface.SetMasterVolumeLevelScalar(new, None)
        speak("Volume increased.")
    except Exception as e:
        gui.log(f"Volume up error: {e}", "ERROR")
        speak("Couldn't change volume.")

def volume_down():
    if _volume_interface is None:
        speak("Volume control is not available on this system.")
        return
    try:
        current = _volume_interface.GetMasterVolumeLevelScalar()
        new = max(0.0, current - 0.05)
        _volume_interface.SetMasterVolumeLevelScalar(new, None)
        speak("Volume decreased.")
    except Exception as e:
        gui.log(f"Volume down error: {e}", "ERROR")
        speak("Couldn't change volume.")

def mute_toggle():
    if _volume_interface is None:
        speak("Volume control is not available on this system.")
        return
    try:
        muted = _volume_interface.GetMute()
        _volume_interface.SetMute(not muted, None)
        speak("Muted." if not muted else "Unmuted.")
    except Exception as e:
        gui.log(f"Mute error: {e}", "ERROR")
        speak("Couldn't toggle mute.")

# -------------------------
# Command processing
# -------------------------
def open_Youtube(query: str):
    qs = urllib.parse.quote_plus(query)
    url = f"https://www.youtube.com/results?search_query={qs}"
    gui.log(f"Opening Youtube for: {query}", "SYSTEM")
    webbrowser.open(url)

def search_online(query: str):
    qs = urllib.parse.quote_plus(query)
    url = f"https://www.google.com/search?q={qs}"
    gui.log(f"Searching online: {query}", "SYSTEM")
    webbrowser.open(url)

def process_command(command_text: str):
    cmd = command_text.lower().strip()
    doc = nlp(cmd)
    
    # Check for intents using a combination of keywords and spaCy
    
    # Weather command fix
    if "weather in" in cmd:
        city = cmd.split("weather in", 1)[-1].strip()
        if city:
            get_weather_for(city)
        else:
            speak("Which city would you like the weather for?")
        return True
    
    # Open application command fix
    if cmd.startswith("open ") or cmd.startswith("launch ") or cmd.startswith("start "):
        app_name = None
        if cmd.startswith("open "):
            app_name = cmd[len("open "):].strip()
        elif cmd.startswith("launch "):
            app_name = cmd[len("launch "):].strip()
        elif cmd.startswith("start "):
            app_name = cmd[len("start "):].strip()

        if app_name:
            gui.log(f"Open request: {app_name}", "SYSTEM")
            if open_application_by_name(app_name):
                speak(f"Opening {app_name}.")
            else:
                speak(f"I couldn't find {app_name} locally. I'll search online.")
                search_online(app_name)
        else:
            speak("Which application would you like me to open?")
        return True

    # New image generation command
    if "generate an image of" in cmd or "create an image of" in cmd:
        prompt = None
        if "generate an image of" in cmd:
            prompt = cmd.split("generate an image of", 1)[-1].strip()
        elif "create an image of" in cmd:
            prompt = cmd.split("create an image of", 1)[-1].strip()
        
        if prompt:
            # Run image generation in a separate thread to avoid blocking the main loop
            threading.Thread(target=generate_image, args=(prompt,), daemon=True).start()
        else:
            speak("What image would you like me to generate?")
        return True

    # New email command
    if "send an email" in cmd or "email" in cmd:
        speak("Who is the recipient?")
        recipient = listen_for_command(timeout=10)
        if not recipient:
            speak("I didn't get that. Canceling email.")
            return True
        speak(f"The recipient is {recipient}. What is the subject?")
        subject = listen_for_command(timeout=10)
        if not subject:
            speak("I didn't get that. Canceling email.")
            return True
        speak(f"The subject is {subject}. What is the body of the email?")
        body = listen_for_command(timeout=15)
        if not body:
            speak("I didn't get that. Canceling email.")
            return True

        speak("I am preparing to send the email now.")
        threading.Thread(target=send_email_task, args=(recipient, subject, body), daemon=True).start()
        return True

    # New WhatsApp message feature
    if "send a whatsapp message" in cmd or "send a message" in cmd:
        speak("Who is the recipient?")
        contact_name = listen_for_command(timeout=10)
        if not contact_name:
            speak("I didn't get the recipient's name. Canceling message.")
            return True
        speak("What is the message?")
        message_body = listen_for_command(timeout=15)
        if not message_body:
            speak("I didn't get the message. Canceling message.")
            return True

        threading.Thread(target=send_whatsapp_message_desktop, args=(contact_name, message_body), daemon=True).start()
        return True

    # Check for other intents using spaCy
    for token in doc:
        # Reminders intent
        if token.lemma_ in ["remind", "set"] and "reminder" in cmd:
            parsed_date_time = dateparser.parse(cmd, settings={'PREFER_DATES_FROM': 'future'})
            if parsed_date_time:
                reminders_queue.put((parsed_date_time, cmd))
                speak(f"Reminder set for {parsed_date_time.strftime('%I:%M %p on %A, %B %d')}.")
            else:
                speak("I couldn't understand the time for the reminder.")
            return True
            
        # Wikipedia intent
        if token.lemma_ in ["tell", "who", "what"] and "about" in cmd:
            topic = cmd.split("about", 1)[-1].strip()
            wiki_summary(topic)
            return True

        # Window management
        if token.lemma_ in ["minimize", "maximize", "close"]:
            if pyautogui is None:
                speak("Window management is not available. Please install the 'pyautogui' library.")
                return True
            if "minimize" in cmd:
                try:
                    pyautogui.hotkey('win', 'down')
                    speak("Window minimized.")
                except Exception:
                    speak("I couldn't minimize the window.")
            elif "maximize" in cmd:
                try:
                    pyautogui.hotkey('win', 'up')
                    speak("Window maximized.")
                except Exception:
                    speak("I couldn't maximize the window.")
            elif "close" in cmd:
                app_to_close = cmd.split("close", 1)[-1].strip()
                if app_to_close:
                    if close_application_by_name(app_to_close):
                        speak(f"Closing {app_to_close}.")
                    else:
                        speak(f"I couldn't find a running application named {app_to_close}.")
                else:
                    # Fallback to the original ALT+F4 for closing the active window
                    try:
                        pyautogui.hotkey('alt', 'f4')
                        speak("Active window closed.")
                    except Exception:
                        speak("I couldn't close the active window.")
            return True

    # Your existing command logic (for commands that don't need NLP)
    if cmd in ("exit", "quit", "goodbye", "shutdown assistant"):
        speak("Goodbye.")
        return False
    if cmd in ("shut down", "shutdown", "power off", "turn off"):
        speak("Shutting down the system.")
        try:
            os.system("shutdown /s /t 0")
        except Exception:
            speak("I couldn't shut down the system.")
        return False
    if cmd in ("restart", "reboot"):
        speak("Restarting the system.")
        try:
            os.system("shutdown /r /t 0")
        except Exception:  
            speak("I couldn't restart the system.")
        return False
    if cmd in ("log off", "logout", "sign out"):
        speak("Logging off now.")
        try:
            os.system("shutdown /l")
        except Exception:
            speak("I couldn't log off.")
        return False
    if cmd.startswith("play "):
        target = cmd[len("play "):].strip()
        path = find_local_track(target)
        if path:
            play_local_music(path)
        else:
            speak(f"I couldn't find {target} locally. I'll search YouTube.")
            open_Youtube(target)
        return True
    if cmd in ("pause", "pause music"):
        pause_music()
        return True
    if cmd in ("resume", "resume music"):
        resume_music()
        return True
    if cmd in ("stop", "stop music"):
        stop_music()
        return True
    
    # New code for battery status
    if "battery" in cmd or "battery status" in cmd:
        if psutil:
            try:
                batt = psutil.sensors_battery()
                if batt:
                    speak(f"Battery is at {int(batt.percent)} percent.")
                else:
                    speak("No battery information available.")
            except Exception:
                speak("I couldn't read the battery information.")
        else:
            speak("Install psutil for battery status.")
        return True
    
    # New code for CPU and RAM usage
    if "cpu" in cmd and ("usage" in cmd or "percent" in cmd):
        get_cpu_usage()
        return True
    if "ram" in cmd or "memory" in cmd:
        get_ram_usage()
        return True
    if "system info" in cmd or ("system" in cmd and "info" in cmd):
        get_system_info()
        return True
    
    # New code for screenshots, jokes, notes, clipboard, news, time, and date
    if "screenshot" in cmd or "take screenshot" in cmd:
        take_screenshot()
        return True
    if "joke" in cmd:
        tell_joke()
        return True
    if cmd.startswith("note "):
        note_text = command_text[len("note "):].strip()
        if note_text:
            save_note(note_text)
        else:
            speak("What would you like me to note?")
        return True
    if "take a note" in cmd or "take note" in cmd or "write note" in cmd:
        speak("What should I write?")
        note_text = listen_for_command(timeout=10, phrase_time_limit=20)
        if note_text:
            save_note(note_text)
        return True
    if "read clipboard" in cmd or "clipboard" in cmd:
        read_clipboard()
        return True
    if "volume up" in cmd or "increase volume" in cmd:
        volume_up()
        return True
    if "volume down" in cmd or "decrease volume" in cmd:
        volume_down()
        return True
    if "mute" in cmd or "unmute" in cmd:
        mute_toggle()
        return True
    if "latest news" in cmd or "what's the news" in cmd:
        get_news_headlines()
        return True
    if ("time" in cmd) and (("what" in cmd) or cmd == "time" or "time" in cmd):
        speak(f"The time is {datetime.datetime.now().strftime('%I:%M %p')}")
        return True
    if "date" in cmd:
        speak(f"Today is {datetime.datetime.now().strftime('%A, %B %d, %Y')}")
        return True

    # Final fallback if no other command is matched
    speak(f"Searching the web for {cmd}")
    search_online(cmd)
    return True

# -------------------------
# Main assistant loop
# -------------------------
def auto_greeting():
    h = datetime.datetime.now().hour
    if h < 12:
        greet = "Good morning"
    elif h < 18:
        greet = "Good afternoon"
    else:
        greet = "Good evening"
    speak(f"{greet}, {user_data['name']}. terminator at your service. Say 'terminator' to activate.")

def main_logic():
    root = tk.Tk()
    global gui
    gui = terminatorGUI(root)
    
    # After GUI is initialized, call functions that use it
    speak("Scanning for installed applications.")
    scan_installed_apps()
    global local_music_index
    speak("Indexing local music files.")
    local_music_index = index_local_music(MUSIC_DIR)

    auto_greeting()
    gui.update_status("Idle")

    if pvporcupine is not None and pyaudio is not None:
        speak("Wake-word listener is now active. Please say 'terminator' to begin.")
        t = threading.Thread(target=porcupine_worker, daemon=True)
        t.start()
    else:
        gui.log("Wake-word listener is disabled due to missing dependencies. Use the GUI or a keyboard shortcut to activate.", "SYSTEM")
        speak("Wake-word is disabled. Please use the GUI or a keyboard shortcut to activate me.")

    # Start new feature threads
    reminder_thread = threading.Thread(target=reminder_worker, daemon=True)
    reminder_thread.start()
    speak("Reminder system activated.")

    try:
        while True:
            # Main logic loop for handling wake-word and commands
            if pvporcupine is not None:
                if wake_queue.empty():
                    gui.root.update_idletasks()
                    gui.root.update()
                    time.sleep(0.1)
                    continue

                wake_queue.get()
                speak(f"Yes, {user_data['name']}.")
            
            command = listen_for_command()
            if command:
                if not process_command(command):
                    break
    except KeyboardInterrupt:
        gui.log("Shutting down...", "SYSTEM")
        speak("Shutting down now. Goodbye.")
    except Exception as e:
        gui.log(f"An unexpected error occurred: {e}", "ERROR")
        speak("An unexpected error occurred. I'm shutting down.")
    finally:
        root.quit()

if __name__ == "__main__":
    try:
        main_logic()
    except Exception as e:
        print(f"Failed to start the application: {e}")
        speak("I have failed to start the application.")