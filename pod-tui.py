#!/usr/bin/env python3
import requests
import sys
import subprocess
import time
import threading
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text
from rich.align import Align
import json
import socket
import select
import tty
import termios
import os
import logging
import re
from datetime import datetime
import unicodedata
import feedparser

# Configure logging
LOG_DIR = os.path.expanduser("~/.cache/pod-tui")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "pod-tui-debug.log"),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
MPV_LOG = os.path.join(LOG_DIR, "mpv.log")

# Colors
POD_BLUE = "#1D8AB9"
LIGHT_TEXT = "#FFFFFF"
GRAY_TEXT = "#B3B3B3"
ERROR_RED = "#FF5555"

MPV_SOCKET_PATH = f"/tmp/pod-tui-mpv-{os.getuid()}.sock"
SUB_FILE = os.path.expanduser("~/.config/pod-tui/subscriptions.json")
HISTORY_FILE = os.path.expanduser("~/.config/pod-tui/history.json")

# ASCII Block Font (5 lines)
BIG_FONT = {
    'A': ["▄█▄", "█▄█", "█ █", "█ █", "█ █"],
    'B': ["█▀▄ ", "█ █ ", "█▀▀▄", "█  █", "▀▀▀ "],
    'C': ["▄▀▀", "█  ", "█  ", "█  ", "▀▄▄"],
    'D': ["█▀▄ ", "█  █", "█  █", "█  █", "█▄▀ "],
    'E': ["█▀▀", "█  ", "█▀ ", "█  ", "█▄▄"],
    'F': ["█▀▀", "█  ", "█▀ ", "█  ", "█  "],
    'G': ["▄▀▀ ", "█   ", "█ ▀█", "█  █", "▀▄▄▀"],
    'H': ["█ █", "█ █", "█▀█", "█ █", "█ █"],
    'I': ["█", "█", "█", "█", "█"],
    'J': ["  █", "  █", "  █", "█ █", "▀▄▀"],
    'K': ["█ █", "█▀ ", "█▄ ", "█ █", "█ █"],
    'L': ["█  ", "█  ", "█  ", "█  ", "█▄▄"],
    'M': ["█   █", "██ ██", "█ █ █", "█   █", "█   █"],
    'N': ["█   █", "██  █", "█ █ █", "█  ██", "█   █"],
    'O': ["▄█▄", "█ █", "█ █", "█ █", "▀█▀"],
    'P': ["█▀▄", "█ █", "█▀ ", "█  ", "█  "],
    'Q': [" █  ", "█ █ ", "█ █ ", "█ ▄█", " ▀▀▀"],
    'R': ["█▀▄", "█ █", "█▀▄", "█ █", "█ █"],
    'S': ["▄▀▀", "█  ", "▀▀▄", "  █", "▄▄▀"],
    'T': ["▀█▀", " █ ", " █ ", " █ ", " █ "],
    'U': ["█ █", "█ █", "█ █", "█ █", "▀▄▀"],
    'V': ["█ █", "█ █", "█ █", "▀▄▀", " ▀ "],
    'W': ["█   █", "█   █", "█ █ █", "██ ██", "█   █"],
    'X': ["█ █", "▀▄▀", " █ ", "▄▀▄", "█ █"],
    'Y': ["█ █", "█ █", "▀▄▀", " █ ", " █ "],
    'Z': ["▀▀█", "  █", " █ ", "█  ", "▀▀▀"],
    'Å': [" ▄ ", " █ ", "█▀█", "█ █", "█ █"],
    'Ä': ["▄ ▄", " █ ", "█▀█", "█ █", "█ █"],
    'Ö': ["▄ ▄", " █ ", "█ █", "█ █", " █ "],
    '0': ["▄▀▄", "█ █", "█ █", "█ █", "▀▄▀"],
    '1': [" █ ", "██ ", " █ ", " █ ", "▄█▄"],
    '2': ["▀▀▄", "  █", " ▄▀", "█  ", "▀▀▀"],
    '3': ["▀▀▄", "  █", " ▀▄", "  █", "▀▀▄"],
    '4': ["█ █", "█ █", "▀▀█", "  █", "  █"],
    '5': ["█▀▀", "█▀▄", "  █", "▄▄▀", "▀▀ "],
    '6': [" ▄▀", "█▀▄", "█ █", "█ █", "▀▄▀"],
    '7': ["▀▀█", "  █", " █ ", " █ ", " █ "],
    '8': ["▄▀▄", "█ █", "█▀█", "█ █", "▀▄▀"],
    '9': ["▄▀▄", "█▄█", " ▀█", "▄▄▀", " ▀ "],
    ' ': ["  ", "  ", "  ", "  ", "  "],
    ':': [" "," ", "▄", " ", " ", "▄"],
    '-': ["    ", "    ", "▀▀▀▀", "    ", "    "],
    '.': [" "," ", " ", " ", " ", "▄"],
}

class PodcastPlayer:
    def __init__(self):
        self.podcasts = []; self.episodes = []; self.subscriptions = []; self.discovery = []
        self.selected_podcast_index = 0; self.selected_episode_index = 0; self.active_pane = 'podcasts'
        self.playing_episode = None; self.mpv_process = None; self.running = True
        self.search_mode = False; self.search_buffer = ""
        self.current_position = 0.0; self.total_duration = 0.0
        self.console = Console(); self.load_subscriptions()
        self.is_fetching_episodes = False; self.loading_status = ""; self.last_index_for_fetch = -1; self.error_message = ""
        self.playback_history = self.load_history()
        self.last_save_time = time.time()
        self.fetch_discovery(); self.update_podcast_list()
        
        if os.path.exists(MPV_SOCKET_PATH):
            try: os.remove(MPV_SOCKET_PATH)
            except: pass

    def load_subscriptions(self):
        if os.path.exists(SUB_FILE):
            try:
                with open(SUB_FILE, 'r') as f: self.subscriptions = json.load(f)
            except: pass
        else: os.makedirs(os.path.dirname(SUB_FILE), exist_ok=True)

    def save_subscriptions(self):
        try:
            with open(SUB_FILE, 'w') as f: json.dump(self.subscriptions, f)
        except: pass

    def load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r') as f: return json.load(f)
            except: pass
        else: os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        return {}

    def save_history(self):
        try:
            with open(HISTORY_FILE, 'w') as f: json.dump(self.playback_history, f)
        except: pass


    def fetch_discovery(self):
        try:
            url = "https://rss.applemarketingtools.com/api/v2/us/podcasts/top/50/podcasts.json"
            resp = requests.get(url, timeout=5); data = resp.json().get('feed', {}).get('results', [])
            self.discovery = [{'name': r.get('name'), 'artist': r.get('artistName'), 'feed_url': "", 'itunes_id': r.get('id'), 'description': r.get('genres', [{}])[0].get('name', 'Podcast'), 'full_description': ""} for r in data]
        except: pass

    def update_podcast_list(self):
        new_list = []
        # Special entry for global feed
        if self.subscriptions:
            new_list.append({'type': 'global', 'name': '--- NEW EPISODES ---'})
            new_list.append({'type': 'header', 'name': '--- SUBSCRIPTIONS ---'})
            sorted_subs = sorted(self.subscriptions, key=lambda x: x.get('latest_date', ''), reverse=True)
            new_list.extend(sorted_subs)
        
        new_list.append({'type': 'header', 'name': '--- DISCOVERY ---'})
        new_list.extend(self.discovery)
        self.podcasts = new_list
        if self.podcasts and self.podcasts[self.selected_podcast_index].get('type') == 'header':
            self.selected_podcast_index = min(len(self.podcasts)-1, self.selected_podcast_index + 1)

    def resolve_podd_feed(self, podcast):
        if podcast.get('feed_url'): return podcast['feed_url']
        itunes_id = podcast.get('itunes_id')
        try:
            url = f"https://itunes.apple.com/lookup?id={itunes_id}" if itunes_id else f"https://itunes.apple.com/search?term={requests.utils.quote(podcast['name'])}&entity=podcast&limit=1"
            resp = requests.get(url, timeout=5); results = resp.json().get('results', [])
            if results:
                podcast['feed_url'] = results[0].get('feedUrl'); podcast['full_description'] = results[0].get('description')
                return podcast['feed_url']
        except: pass
        return None

    def fetch_single_feed(self, pod, limit=10):
        feed_url = self.resolve_podd_feed(pod)
        if not feed_url: return []
        try:
            feed = feedparser.parse(feed_url); eps = []
            for entry in feed.entries[:limit]:
                audio_url = ""; candidates = []
                if 'enclosures' in entry: candidates.extend([e.get('href') for e in entry.enclosures if e.get('href')])
                if 'links' in entry: candidates.extend([l.get('href') for l in entry.links if 'audio' in str(l.get('type', '')).lower() or l.get('rel') == 'enclosure'])
                if 'media_content' in entry: candidates.extend([m.get('url') for m in entry.media_content if m.get('url')])
                if 'links' in entry: candidates.extend([l.get('href') for l in entry.links if any(ext in str(l.get('href')).lower() for ext in ['.mp3', '.m4a', '.aac', '.wav', '.ogg'])])
                for c in candidates:
                    if c and any(ext in c.lower() for ext in ['.mp3', '.m4a', '.aac', '.wav', '.ogg', 'podcast', 'audio', 'redirect']):
                        audio_url = c; break
                if not audio_url and candidates: audio_url = candidates[0]
                if not audio_url: continue
                date_str = time.strftime('%Y-%m-%d %H:%M', entry.published_parsed) if 'published_parsed' in entry else entry.get('published', '')[:16]
                desc = re.sub('<[^<]+?>', '', entry.get('summary', entry.get('description', '')))
                eps.append({'title': entry.get('title', 'Unknown'), 'description': desc, 'url': audio_url, 'date': date_str, 'duration': entry.get('itunes_duration', '0'), 'podcast_name': pod['name']})
            return eps
        except: return []

    def async_fetch_episodes(self, podcast):
        if podcast.get('type') == 'header': return
        self.is_fetching_episodes = True; self.loading_status = "Loading..."
        
        if podcast.get('type') == 'global':
            self.loading_status = "Refreshing all subscriptions..."
            all_eps = []
            threads = []
            def worker(p): all_eps.extend(self.fetch_single_feed(p, limit=8))
            for s in self.subscriptions:
                t = threading.Thread(target=worker, args=(s,)); t.start(); threads.append(t)
            for t in threads: t.join()
            self.episodes = sorted(all_eps, key=lambda x: x['date'], reverse=True)
            self.loading_status = ""
        else:
            self.loading_status = "Fetching episodes..."
            self.episodes = self.fetch_single_feed(podcast, limit=100)
            if self.episodes:
                latest = self.episodes[0]['date']
                if podcast.get('latest_date') != latest:
                    podcast['latest_date'] = latest
                    if any(s['name'] == podcast['name'] for s in self.subscriptions): self.save_subscriptions()
            self.loading_status = ""
        self.is_fetching_episodes = False

    def render_big_text(self, text, color=POD_BLUE, max_width=None):
        raw_text = unicodedata.normalize('NFC', text).upper()
        if not max_width: max_width = self.console.size.width // 2
        sanitized = "".join(c if c in BIG_FONT else " " for c in raw_text)
        if len(sanitized) * 7 > max_width: sanitized = sanitized[:max_width // 7 - 2] + "."
        if len(sanitized) < 4: return Text("")
        lines = ["", "", "", "", ""]
        for char in sanitized:
            char_lines = BIG_FONT.get(char, BIG_FONT.get('?', ["   "]*5))
            for i in range(5): lines[i] += char_lines[i] + "  "
        result = Text()
        for i, line in enumerate(lines): result.append(line.rstrip() + ("\n" if i < 4 else ""), style=color)
        return result

    def format_time(self, seconds):
        if not seconds or seconds < 0: return "00:00"
        m, s = divmod(int(seconds), 60); h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

    def send_mpv_command(self, cmd_list):
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sock.settimeout(0.05); sock.connect(MPV_SOCKET_PATH)
            cmd = json.dumps({"command": cmd_list}) + "\n"; sock.send(cmd.encode()); sock.close()
        except: pass

    def get_mpv_property(self, prop):
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sock.settimeout(0.02); sock.connect(MPV_SOCKET_PATH)
            cmd = json.dumps({"command": ["get_property", prop]}) + "\n"; sock.send(cmd.encode())
            data = json.loads(sock.recv(4096).decode()); sock.close()
            if 'data' in data: return data['data']
        except: pass
        return None

    def play_episode(self, ep):
        if not ep or not ep.get('url'): self.error_message = "Error: No URL found."; return
        self.playing_episode = ep; self.error_message = ""
        if self.mpv_process:
            try: self.mpv_process.terminate()
            except: pass
        
        start_pos = self.playback_history.get(ep['url'], 0)
        cmd = ["mpv", "--no-video", "--no-terminal", f"--input-ipc-server={MPV_SOCKET_PATH}", "--user-agent=Mozilla/5.0", "--demuxer-max-bytes=50M", "--network-timeout=30", "--ytdl=no"]
        if start_pos > 10: # Only resume if more than 10s in
            cmd.append(f"--start={int(start_pos)}")
            self.error_message = f"Resuming from {self.format_time(start_pos)}..."
        cmd.append(ep['url'])
        
        try:
            log_f = open(MPV_LOG, "a")
            self.mpv_process = subprocess.Popen(cmd, stdout=log_f, stderr=log_f)
        except Exception as e: self.error_message = f"MPV Error: {str(e)}"

    def toggle_subscription(self):
        pod = self.podcasts[self.selected_podcast_index]
        if pod.get('type') in ['header', 'global']: return
        exists = next((i for i, s in enumerate(self.subscriptions) if s['name'] == pod['name']), None)
        if exists is not None: self.subscriptions.pop(exists)
        else:
            sub_pod = pod.copy()
            if 'latest_date' not in sub_pod: sub_pod['latest_date'] = datetime.now().strftime('%Y-%m-%d %H:%M')
            self.subscriptions.append(sub_pod)
        self.save_subscriptions(); self.update_podcast_list()

    def create_layout(self):
        layout = Layout(); layout.split_column(Layout(name="header", size=3), Layout(name="main"), Layout(name="footer", size=1))
        layout["main"].split_row(Layout(name="podcasts", ratio=10), Layout(name="episodes", ratio=12), Layout(name="now_playing", ratio=20))
        return layout

    def update_layout(self, layout):
        header_text = Text.assemble(("POD-TUI", f"bold {POD_BLUE}"), (" - Podcast Explorer ", LIGHT_TEXT), (f"[{datetime.now().strftime('%H:%M:%S')}]", GRAY_TEXT))
        layout["header"].update(Panel(Align.center(header_text, vertical="middle"), border_style=POD_BLUE))
        
        if self.selected_podcast_index != self.last_index_for_fetch:
            self.last_index_for_fetch = self.selected_podcast_index; self.episodes = []
            pod = self.podcasts[self.selected_podcast_index]
            if pod.get('type') != 'header':
                threading.Thread(target=self.async_fetch_episodes, args=(pod,), daemon=True).start()
            
        p_table = Table(show_header=False, box=None, expand=True); p_table.add_column("N")
        h = self.console.size.height - 8; p_start = max(0, self.selected_podcast_index - h // 2)
        for i, p in enumerate(self.podcasts[p_start:p_start+h]):
            if p.get('type') == 'header':
                p_table.add_row(Text(f"\n{p['name']}", style=GRAY_TEXT))
                continue
            marker = "  "
            if p.get('type') == 'global': marker = ""
            elif any(s['name'] == p['name'] for s in self.subscriptions): marker = "★ "
            style = f"bold {POD_BLUE}" if (p_start+i == self.selected_podcast_index and self.active_pane == 'podcasts') else ""
            p_table.add_row(Text(f"{marker}{p['name']}", style=style))
        layout["podcasts"].update(Panel(p_table, title="Podcasts", border_style=POD_BLUE if self.active_pane == 'podcasts' else GRAY_TEXT))
        
        e_table = Table(show_header=False, box=None, expand=True); e_table.add_column("T")
        if self.is_fetching_episodes: e_table.add_row(Text(f"  {self.loading_status}", style=GRAY_TEXT))
        elif not self.episodes: e_table.add_row(Text("  No episodes found.", style=GRAY_TEXT))
        else:
            e_start = max(0, self.selected_episode_index - h // 2)
            cur_pod = self.podcasts[self.selected_podcast_index]
            for i, e in enumerate(self.episodes[e_start:e_start+h]):
                is_sel = (e_start+i == self.selected_episode_index and self.active_pane == 'episodes'); prefix = "▶ " if (self.playing_episode and e['url'] == self.playing_episode['url']) else "  "
                title_line = f"{prefix}{e['date']} - {e['title']}"
                if cur_pod.get('type') == 'global': title_line = f"{prefix}{e['date']} - [{e['podcast_name']}] {e['title']}"
                e_table.add_row(Text(title_line, style=f"bold {POD_BLUE}" if is_sel else "", overflow="ellipsis"))
        layout["episodes"].update(Panel(e_table, title="Episodes", border_style=POD_BLUE if self.active_pane == 'episodes' else GRAY_TEXT))
        
        inner = []; pane_w = self.console.size.width * 2 // 4; target_ep = self.playing_episode; is_playing_cur = False
        if not target_ep:
            if self.active_pane in ['episodes', 'now_playing'] and self.episodes: target_ep = self.episodes[self.selected_episode_index]
            elif self.active_pane == 'podcasts' and self.podcasts: 
                p = self.podcasts[self.selected_podcast_index]
                if p.get('type') not in ['header', 'global']:
                    bt = self.render_big_text(p['name'], max_width=pane_w)
                    if bt: inner.append(bt); inner.append(Text("\n"))
                    inner.append(Text(p['name'], style=f"bold {LIGHT_TEXT} underline")); inner.append(Text(p['artist'] + "\n\n" + (p.get('full_description') or p.get('description','')), style=LIGHT_TEXT))
                elif p.get('type') == 'global':
                    inner.append(self.render_big_text("NEW EPISODES", max_width=pane_w))
                    inner.append(Text("Latest episodes from your subscriptions.", style=LIGHT_TEXT))
        else: is_playing_cur = True
        
        if target_ep and 'title' in target_ep:
            bt = self.render_big_text(target_ep['title'], max_width=pane_w)
            if bt: inner.append(bt); inner.append(Text("\n"))
            inner.append(Text(target_ep['title'], style=f"bold {LIGHT_TEXT} underline")); inner.append(Text(f"{target_ep.get('date','')} [{target_ep.get('duration','')}]", style=GRAY_TEXT)); inner.append(Text(""))
            pos = self.get_mpv_property("time-pos") or (self.current_position if is_playing_cur else 0.0)
            dur = self.get_mpv_property("duration") or (self.total_duration if is_playing_cur else 0.0)
            if is_playing_cur:
                 self.current_position, self.total_duration = pos, dur
                 status = "▶ PLAYING" if (self.get_mpv_property("pause") == False) else "⏸ PAUSED"
                 # Save history periodically
                 if time.time() - self.last_save_time > 5:
                     if pos > 0:
                         self.playback_history[target_ep['url']] = pos
                         self.save_history()
                     self.last_save_time = time.time()
            else: status = "○ READY"
            bar_len = 30
            if dur and dur > 0:
                 perc = min(1.0, max(0.0, pos / dur)); filled = int(perc * bar_len); bar = "━" * filled + "─" * (bar_len - filled); time_str = f"{self.format_time(pos)} / {self.format_time(dur)}"
                 inner.append(Text.assemble((bar, POD_BLUE), (f" {time_str}", GRAY_TEXT)))
            else: inner.append(Text(f"{'─' * bar_len} 00:00 / --:--", style=GRAY_TEXT))
            if self.error_message: inner.append(Text(self.error_message, style=ERROR_RED))
            else: inner.append(Text(status, style=f"bold {POD_BLUE}"))
            inner.append(Text("\n" + target_ep.get('description',''), style=LIGHT_TEXT))
        
        layout["now_playing"].update(Panel(Align.center(Text("\n").join(inner), vertical="middle"), title="Info / Now Playing", border_style=POD_BLUE if self.active_pane == 'now_playing' else GRAY_TEXT))
        footer = Text("↑/↓: Nav | Ent: Play | /: Search (or URL) | s: Sub | Tab: Pane | ←/→: Seek/Pane | q: Quit", style=GRAY_TEXT)
        if self.search_mode: footer = Text(f"🔍 {self.search_buffer}█", style=LIGHT_TEXT)
        layout["footer"].update(Align.center(footer))

    def handle_input(self):
        fd = sys.stdin.fileno(); old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while self.running:
                if select.select([sys.stdin], [], [], 0.05)[0]:
                    char = sys.stdin.read(1)
                    if self.search_mode:
                        if char in ['\r', '\n']:
                            if self.search_buffer.startswith('http'):
                                # Direct RSS feed support
                                pod = {'name': 'Custom Feed', 'artist': 'RSS', 'feed_url': self.search_buffer, 'itunes_id': None, 'description': 'Custom RSS Feed'}
                                self.subscriptions.append(pod); self.save_subscriptions()
                                self.update_podcast_list(); self.active_pane = 'podcasts'
                            else:
                                try:
                                    resp = requests.get(f"https://itunes.apple.com/search?term={requests.utils.quote(self.search_buffer)}&entity=podcast").json()
                                    self.discovery = [{'name': r.get('collectionName', 'Unknown'), 'artist': r.get('artistName', 'Unknown'), 'itunes_id': r.get('collectionId'), 'feed_url': r.get('feedUrl', ''), 'description': r.get('primaryGenreName', 'Podcast')} for r in resp.get('results', [])]
                                    self.selected_podcast_index = 0; self.active_pane = 'podcasts'; self.update_podcast_list()
                                except: pass
                            self.search_mode = False
                        elif char == '\x1b': self.search_mode = False
                        elif ord(char) == 127: self.search_buffer = self.search_buffer[:-1]
                        else: self.search_buffer += char
                    else:
                        if char == 'q': self.running = False
                        elif char == '/':
                             if self.active_pane == 'podcasts': self.search_mode = True; self.search_buffer = ""
                        elif char == 's': self.toggle_subscription()
                        elif ord(char) == 9: # Tab cycle
                             cycle = ['podcasts', 'episodes', 'now_playing']
                             self.active_pane = cycle[(cycle.index(self.active_pane) + 1) % len(cycle)]
                        elif char == 'h': self.active_pane = 'podcasts'
                        elif char == 'l': self.active_pane = 'episodes'
                        elif char == ' ': self.send_mpv_command(["cycle", "pause"])
                        elif char in ['\r', '\n']:
                            pod = self.podcasts[self.selected_podcast_index]
                            if self.active_pane == 'podcasts' and pod.get('type') != 'header':
                                self.active_pane = 'episodes'; self.selected_episode_index = 0
                            elif self.active_pane == 'episodes' and self.episodes: self.play_episode(self.episodes[self.selected_episode_index])
                        elif char == '\x1b':
                            seq = sys.stdin.read(2)
                            if seq == '[A': # Up
                                self.selected_podcast_index = max(0, self.selected_podcast_index - 1) if self.active_pane == 'podcasts' else max(0, self.selected_episode_index - 1)
                                if self.active_pane == 'podcasts' and self.podcasts[self.selected_podcast_index].get('type') == 'header':
                                    self.selected_podcast_index = max(0, self.selected_podcast_index - 1)
                            elif seq == '[B': # Down
                                if self.active_pane == 'podcasts':
                                    self.selected_podcast_index = min(len(self.podcasts) - 1, self.selected_podcast_index + 1)
                                    if self.podcasts[self.selected_podcast_index].get('type') == 'header':
                                        self.selected_podcast_index = min(len(self.podcasts)-1, self.selected_podcast_index + 1)
                                else: self.selected_episode_index = min(len(self.episodes) - 1, self.selected_episode_index + 1)
                            elif seq == '[D': # Left
                                if self.active_pane == 'now_playing': self.send_mpv_command(["seek", -10])
                                elif self.active_pane == 'episodes': self.active_pane = 'podcasts'
                            elif seq == '[C': # Right
                                if self.active_pane == 'now_playing': self.send_mpv_command(["seek", 10])
                                elif self.active_pane == 'podcasts': self.active_pane = 'episodes'
                                elif self.active_pane == 'episodes': self.active_pane = 'now_playing'
        finally: termios.tcsetattr(fd, termios.TCSADRAIN, old)

    def run(self):
        threading.Thread(target=self.handle_input, daemon=True).start()
        with Live(self.create_layout(), refresh_per_second=4, screen=True) as live:
            while self.running:
                layout = self.create_layout(); self.update_layout(layout); live.update(layout); time.sleep(0.1)
        if self.mpv_process: self.mpv_process.terminate()

if __name__ == "__main__": 
    if sys.stdin.isatty(): PodcastPlayer().run()
