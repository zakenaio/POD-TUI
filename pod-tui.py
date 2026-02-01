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
from rich.padding import Padding
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
        self.is_fetching_episodes = False; self.loading_status = ""; self.last_index_for_fetch = -1; self.error_message = ""; self.error_time = 0
        self.current_fetch_id = 0; self.is_showing_search = False
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

    def set_error(self, msg):
        self.error_message = msg; self.error_time = time.time()


    def fetch_discovery(self):
        try:
            self.set_error("Updating discovery charts..."); self.is_showing_search = False
            url = "https://rss.applemarketingtools.com/api/v2/us/podcasts/top/50/podcasts.json"
            resp = requests.get(url, timeout=5); data = resp.json().get('feed', {}).get('results', [])
            self.discovery = [{'name': r.get('name'), 'artist': r.get('artistName'), 'feed_url': "", 'itunes_id': r.get('id'), 'description': r.get('genres', [{}])[0].get('name', 'Podcast'), 'full_description': ""} for r in data]
            self.set_error("")
        except Exception as e:
            self.set_error(f"Discovery error: {str(e)}")

    def get_visible_podcasts(self):
        if self.search_mode and self.search_buffer:
            q = self.search_buffer.lower()
            return [p for p in self.podcasts if q in p.get('name', '').lower() or q in p.get('artist', '').lower() or p.get('type') == 'header']
        return self.podcasts

    def get_visible_episodes(self):
        if self.search_mode and self.search_buffer:
            q = self.search_buffer.lower()
            return [e for e in self.episodes if q in e.get('title', '').lower() or q in e.get('description', '').lower()]
        return self.episodes

    def update_podcast_list(self):
        new_list = []
        # Special entry for global feed
        if self.subscriptions:
            new_list.append({'type': 'global', 'name': '--- NEW EPISODES ---'})
            new_list.append({'type': 'header', 'name': '--- SUBSCRIPTIONS ---'})
            sorted_subs = sorted(self.subscriptions, key=lambda x: x.get('latest_date', ''), reverse=True)
            new_list.extend(sorted_subs)
        
        discovery_label = "--- SEARCH RESULTS ---" if self.is_showing_search else "--- DISCOVERY ---"
        new_list.append({'type': 'header', 'name': discovery_label})
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

    def async_fetch_episodes(self, podcast, fetch_id):
        if podcast.get('type') == 'header' or fetch_id != self.current_fetch_id: return
        self.is_fetching_episodes = True; self.loading_status = "Loading..."
        
        if podcast.get('type') == 'global':
            self.loading_status = "Refreshing all subscriptions..."
            all_eps = []
            threads = []
            def worker(p): all_eps.extend(self.fetch_single_feed(p, limit=8))
            for s in self.subscriptions:
                t = threading.Thread(target=worker, args=(s,)); t.start(); threads.append(t)
            for t in threads: t.join()
            if fetch_id == self.current_fetch_id:
                self.episodes = sorted(all_eps, key=lambda x: x['date'], reverse=True)
                self.loading_status = ""
        else:
            self.loading_status = "Fetching episodes..."
            eps = self.fetch_single_feed(podcast, limit=100)
            if fetch_id == self.current_fetch_id:
                self.episodes = eps
                if self.episodes:
                    latest = self.episodes[0]['date']
                    if podcast.get('latest_date') != latest:
                        podcast['latest_date'] = latest
                        if any(s['name'] == podcast['name'] for s in self.subscriptions): self.save_subscriptions()
                self.loading_status = ""
        
        if fetch_id == self.current_fetch_id:
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
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sock.settimeout(0.1); sock.connect(MPV_SOCKET_PATH)
            cmd = json.dumps({"command": ["get_property", prop]}) + "\n"; sock.send(cmd.encode())
            data = json.loads(sock.recv(4096).decode()); sock.close()
            if 'data' in data: return data['data']
        except: pass
        return None

    def play_episode(self, ep):
        if not ep or not ep.get('url'): self.set_error("Error: No URL found."); return
        self.playing_episode = ep; self.set_error("")
        if self.mpv_process:
            try: self.mpv_process.terminate()
            except: pass
        
        start_pos = self.playback_history.get(ep['url'], 0)
        cmd = ["mpv", "--no-video", "--no-terminal", f"--input-ipc-server={MPV_SOCKET_PATH}", "--user-agent=Mozilla/5.0", "--demuxer-max-bytes=50M", "--network-timeout=30", "--ytdl=no"]
        if start_pos > 10: # Only resume if more than 10s in
            cmd.append(f"--start={int(start_pos)}")
            self.set_error(f"Resuming from {self.format_time(start_pos)}...")
        cmd.append(ep['url'])
        
        try:
            log_f = open(MPV_LOG, "a")
            self.mpv_process = subprocess.Popen(cmd, stdout=log_f, stderr=log_f)
        except Exception as e: self.set_error(f"MPV Error: {str(e)}")

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
        if self.error_message and time.time() - self.error_time > 5: self.error_message = ""
        header_text = Text.assemble(("POD-TUI", f"bold {POD_BLUE}"), (" - Podcast Explorer ", LIGHT_TEXT), (f"[{datetime.now().strftime('%H:%M:%S')}]", GRAY_TEXT))
        layout["header"].update(Panel(Align.center(header_text, vertical="middle"), border_style=POD_BLUE))
        
        visible_pods = self.get_visible_podcasts()
        self.selected_podcast_index = max(0, min(self.selected_podcast_index, len(visible_pods)-1)) if visible_pods else 0
        
        # Determine if we need to fetch new episodes
        selection_key = f"{visible_pods[self.selected_podcast_index].get('name')}-{self.active_pane}" if visible_pods else ""
        if selection_key != self.last_index_for_fetch:
            self.last_index_for_fetch = selection_key
            self.episodes = []; self.is_fetching_episodes = False
            if visible_pods:
                pod = visible_pods[self.selected_podcast_index]
                if pod.get('type') != 'header':
                    self.current_fetch_id += 1
                    threading.Thread(target=self.async_fetch_episodes, args=(pod, self.current_fetch_id), daemon=True).start()
        p_start = max(0, self.selected_podcast_index - h // 2)
        
        for i, p in enumerate(visible_pods[p_start:p_start+h]):
            if p.get('type') == 'header':
                p_table.add_row(Text(f"\n{p['name']}", style=GRAY_TEXT))
                continue
            marker = "  "
            if p.get('type') == 'global': marker = ""
            elif any(s['name'] == p['name'] for s in self.subscriptions): marker = "★ "
            style = f"bold {POD_BLUE}" if (p_start+i == self.selected_podcast_index and self.active_pane == 'podcasts') else ""
            p_table.add_row(Text(f"{marker}{p['name']}", style=style))
        
        if self.search_mode and self.search_buffer and not [p for p in visible_pods if p.get('type') not in ['header', 'global']]:
            p_table.add_row(Text("\n[Enter] to search iTunes", style=GRAY_TEXT))
            
        layout["podcasts"].update(Panel(Padding(p_table, (1, 2)), title="Podcasts", border_style=POD_BLUE if self.active_pane == 'podcasts' else GRAY_TEXT))
        
        e_table = Table(show_header=False, box=None, expand=True); e_table.add_column("T")
        visible_eps = self.get_visible_episodes()
        self.selected_episode_index = max(0, min(self.selected_episode_index, len(visible_eps)-1)) if visible_eps else 0
        
        if self.is_fetching_episodes: e_table.add_row(Text(f"  {self.loading_status}", style=GRAY_TEXT))
        elif not visible_eps: e_table.add_row(Text("  No episodes found.", style=GRAY_TEXT))
        else:
            e_start = max(0, self.selected_episode_index - h // 2)
            cur_pod = self.podcasts[self.selected_podcast_index] if self.podcasts else {}
            for i, e in enumerate(visible_eps[e_start:e_start+h]):
                is_sel = (e_start+i == self.selected_episode_index and self.active_pane == 'episodes'); prefix = "▶ " if (self.playing_episode and e['url'] == self.playing_episode['url']) else "  "
                title_line = f"{prefix}{e['date']} - {e['title']}"
                if cur_pod.get('type') == 'global': title_line = f"{prefix}{e['date']} - [{e['podcast_name']}] {e['title']}"
                e_table.add_row(Text(title_line, style=f"bold {POD_BLUE}" if is_sel else "", overflow="ellipsis"))
        
        if self.search_mode and self.search_buffer and not visible_eps:
             e_table.add_row(Text("\n[Enter] to search iTunes", style=GRAY_TEXT))
             
        layout["episodes"].update(Panel(Padding(e_table, (1, 2)), title="Episodes", border_style=POD_BLUE if self.active_pane == 'episodes' else GRAY_TEXT))
        
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
            if self.error_message: inner.append(Text(f"\n{self.error_message}", style=ERROR_RED))
            else: inner.append(Text(f"\n{status}", style=f"bold {POD_BLUE}"))
            
            # Dynamic Truncation based on window area
            area = self.console.size.width * self.console.size.height
            limit = max(200, area // 10)
            desc = target_ep.get('description','')
            if len(desc) > limit: desc = desc[:limit] + "..."
            inner.append(Text("\n" + desc, style=LIGHT_TEXT))
        
        layout["now_playing"].update(Panel(Padding(Align.center(Text("\n").join(inner), vertical="middle"), (1, 3)), title="Info / Now Playing", border_style=POD_BLUE if self.active_pane == 'now_playing' else GRAY_TEXT))
        footer = Text("↑/↓: Nav | Ent: Play | /: Filter | c: Reset | s: Sub | Tab: Pane | q: Quit", style=GRAY_TEXT)
        if self.search_mode:
            context = "Filter / Search iTunes: "
            footer = Text.assemble((context, GRAY_TEXT), (self.search_buffer, LIGHT_TEXT), ("█", POD_BLUE))
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
                            self.search_mode = False; q = self.search_buffer; self.search_buffer = ""
                            if not q.strip():
                                self.fetch_discovery(); self.update_podcast_list(); continue
                                
                            if q.startswith('http') and self.active_pane == 'podcasts':
                                pod = {'name': 'Custom Feed', 'artist': 'RSS', 'feed_url': q, 'itunes_id': None, 'description': 'Custom RSS Feed'}
                                self.subscriptions.append(pod); self.save_subscriptions()
                                self.update_podcast_list(); self.active_pane = 'podcasts'; self.selected_podcast_index = 0
                            else:
                                try:
                                    self.set_error(f"Searching iTunes for '{q}'...")
                                    entity = "podcast" if self.active_pane == 'podcasts' else "podcastEpisode"
                                    resp = requests.get(f"https://itunes.apple.com/search?term={requests.utils.quote(q)}&entity={entity}&limit=50").json()
                                    results = resp.get('results', [])
                                    if results:
                                        if self.active_pane == 'podcasts':
                                            self.is_showing_search = True
                                            self.discovery = [{'name': r.get('collectionName', 'Unknown'), 'artist': r.get('artistName', 'Unknown'), 'itunes_id': r.get('collectionId'), 'feed_url': r.get('feedUrl', ''), 'description': r.get('primaryGenreName', 'Podcast')} for r in results]
                                            self.update_podcast_list()
                                            for idx, p in enumerate(self.podcasts):
                                                if p.get('type') == 'header' and 'DISCOVERY' in p.get('name', ''):
                                                    self.selected_podcast_index = idx + 1; break
                                        else:
                                            self.episodes = []
                                            for r in results:
                                                date_str = r.get('releaseDate', '')[:16].replace('T', ' ')
                                                self.episodes.append({'title': r.get('trackName', 'Unknown'), 'description': r.get('description', ''), 'url': r.get('episodeUrl', ''), 'date': date_str, 'duration': str(r.get('trackTimeMillis', 0) // 1000), 'podcast_name': r.get('collectionName', 'Unknown')})
                                            self.selected_episode_index = 0
                                        self.set_error("")
                                    else:
                                        self.set_error("No results found.")
                                except Exception as e: 
                                    self.set_error(f"Search error: {str(e)}")
                        elif char == '\x1b':
                            if select.select([sys.stdin], [], [], 0.01)[0]:
                                sys.stdin.read(2)
                            else:
                                self.search_mode = False; self.search_buffer = ""
                        elif ord(char) in [8, 127]: self.search_buffer = self.search_buffer[:-1]
                        else: self.search_buffer += char
                    else:
                        if char == 'q': self.running = False
                        elif char == 'c': self.fetch_discovery(); self.update_podcast_list()
                        elif char == '/':
                             self.search_mode = True; self.search_buffer = ""
                        elif char == 's': self.toggle_subscription()
                        elif ord(char) == 9: # Tab cycle
                             cycle = ['podcasts', 'episodes', 'now_playing']
                             self.active_pane = cycle[(cycle.index(self.active_pane) + 1) % len(cycle)]
                             if self.search_mode: self.search_buffer = ""; self.search_mode = False # Reset on tab
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
                                visible_pods = self.get_visible_podcasts()
                                visible_eps = self.get_visible_episodes()
                                if self.active_pane == 'podcasts':
                                    self.selected_podcast_index = max(0, self.selected_podcast_index - 1)
                                    if self.selected_podcast_index < len(visible_pods) and visible_pods[self.selected_podcast_index].get('type') == 'header':
                                        self.selected_podcast_index = max(0, self.selected_podcast_index - 1)
                                else:
                                    self.selected_episode_index = max(0, self.selected_episode_index - 1)
                            elif seq == '[B': # Down
                                visible_pods = self.get_visible_podcasts()
                                visible_eps = self.get_visible_episodes()
                                if self.active_pane == 'podcasts':
                                    self.selected_podcast_index = min(len(visible_pods) - 1, self.selected_podcast_index + 1)
                                    if self.selected_podcast_index < len(visible_pods) and visible_pods[self.selected_podcast_index].get('type') == 'header':
                                        self.selected_podcast_index = min(len(visible_pods)-1, self.selected_podcast_index + 1)
                                else:
                                    self.selected_episode_index = min(len(visible_eps) - 1, self.selected_episode_index + 1)
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
